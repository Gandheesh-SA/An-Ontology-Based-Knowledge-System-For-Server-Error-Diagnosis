"""Run the saved SPARQL competency questions against the included knowledge graph."""

import argparse
from pathlib import Path

from rdflib import Graph


HERE = Path(__file__).resolve().parent
DEFAULT_GRAPH = HERE.parents[1] / "Knowledge Graph" / "knowledge_graph.ttl"


def query_files(number=None):
    files = sorted(HERE.glob("CQ[0-9][0-9]_*.rq"))
    if len(files) != 12:
        raise SystemExit(f"Expected 12 CQ files in {HERE}; found {len(files)}.")
    if number is None:
        return files
    matches = [path for path in files if path.name.startswith(f"CQ{number:02}_")]
    if len(matches) != 1:
        raise SystemExit(f"Could not find exactly one file for CQ{number:02}.")
    return matches


def format_cell(value, width):
    text = str(value).replace("\n", " ") if value is not None else ""
    return text if len(text) <= width else text[: width - 1] + "…"


def run_one(graph, path, limit, width):
    source = path.read_text(encoding="utf-8")
    title = next((line.removeprefix("# ").strip() for line in source.splitlines()
                  if line.startswith("# ")), path.stem)
    result = graph.query(source)
    print(f"\n{title}")
    print(" | ".join(str(name) for name in result.vars))
    count = 0
    for count, row in enumerate(result, start=1):
        if count <= limit:
            print(" | ".join(format_cell(value, width) for value in row))
    print(f"Showing {min(count, limit)} of {count:,} result rows.")
    return count


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    choice = parser.add_mutually_exclusive_group(required=True)
    choice.add_argument("--number", type=int, choices=range(1, 13), metavar="1-12",
                        help="Run one competency question")
    choice.add_argument("--all", action="store_true", help="Run all 12 questions")
    parser.add_argument("--graph", type=Path, default=DEFAULT_GRAPH,
                        help="Turtle knowledge graph (default: repository graph)")
    parser.add_argument("--limit", type=int, default=10,
                        help="Maximum displayed rows per question (default: 10)")
    parser.add_argument("--width", type=int, default=240,
                        help="Maximum displayed characters per cell (default: 240)")
    args = parser.parse_args()
    if args.limit < 0 or args.width < 2:
        parser.error("--limit must be non-negative and --width must be at least 2")
    if not args.graph.is_file():
        parser.error(f"Graph file not found: {args.graph}")

    files = query_files(None if args.all else args.number)
    graph = Graph().parse(args.graph, format="turtle")
    print(f"Loaded {len(graph):,} triples from {args.graph}")
    for path in files:
        run_one(graph, path, args.limit, args.width)


if __name__ == "__main__":
    main()
