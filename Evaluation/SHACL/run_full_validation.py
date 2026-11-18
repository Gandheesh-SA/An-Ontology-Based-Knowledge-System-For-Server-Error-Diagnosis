"""Validate the full Dell instance graph and record shape coverage."""
from collections import Counter
from pathlib import Path
import json
import time

from pyshacl import validate
from rdflib import Graph, Namespace, OWL, RDF, SH


ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
DATA_FILE = ROOT / "knowledge graph/knowledge_graph.ttl"
SHAPES_FILE = ROOT / "knowledge graph/shapes.ttl"
ONTOLOGY_FILE = ROOT / "ontology/ontology.ttl"
D = Namespace("https://example.org/dell-troubleshooting#")


def audit_graph(graph):
    errors = Counter()
    codes = set()
    for event in graph.subjects(RDF.type, D.EventDefinition):
        code = graph.value(event, D.eventCode)
        if code in codes:
            errors["duplicate_event_codes"] += 1
        codes.add(code)

    owners = {step: procedure for procedure, step in graph.subject_objects(D.containsInstruction)}
    for procedure in graph.subjects(RDF.type, D.RecoveryProcedure):
        orders = set()
        for step in graph.objects(procedure, D.containsInstruction):
            order = graph.value(step, D.instructionOrder)
            if order in orders:
                errors["duplicate_instruction_orders_within_procedure"] += 1
            orders.add(order)

    for earlier, later in graph.subject_objects(D.appearsBefore):
        a = graph.value(earlier, D.instructionOrder)
        b = graph.value(later, D.instructionOrder)
        if owners.get(earlier) != owners.get(later) or a is None or b is None or int(a) >= int(b):
            errors["instruction_order_or_owner_errors"] += 1
    for whole, part in graph.subject_objects(D.hasDocumentedPartType):
        if whole == part:
            errors["self_part_links"] += 1
    for first, second in graph.subject_objects(D.similarEvent):
        a = graph.value(first, D.procedureText)
        b = graph.value(second, D.procedureText)
        if a is None or b is None or " ".join(str(a).split()) != " ".join(str(b).split()):
            errors["similar_response_signature_errors"] += 1
    axioms = list(graph.subjects(RDF.type, OWL.Axiom))
    for axiom in axioms:
        triple = (graph.value(axiom, OWL.annotatedSource),
                  graph.value(axiom, OWL.annotatedProperty),
                  graph.value(axiom, OWL.annotatedTarget))
        if triple not in graph:
            errors["evidence_annotations_without_asserted_triple"] += 1
    return {
        "event_codes_checked": len(codes),
        "instruction_owners_checked": len(owners),
        "evidence_axioms_checked": len(axioms),
        **{name: errors[name] for name in (
            "duplicate_event_codes",
            "duplicate_instruction_orders_within_procedure",
            "instruction_order_or_owner_errors",
            "self_part_links",
            "similar_response_signature_errors",
            "evidence_annotations_without_asserted_triple",
        )},
    }


def main():
    start = time.monotonic()
    graph = Graph().parse(DATA_FILE, format="turtle")
    shapes = Graph().parse(SHAPES_FILE, format="turtle")
    ontology = Graph().parse(ONTOLOGY_FILE, format="turtle")
    shape_triples = len(shapes)
    object_properties = set(ontology.subjects(RDF.type, OWL.ObjectProperty))
    shape_paths = set(shapes.objects(None, SH.path))
    local_classes = set(ontology.subjects(RDF.type, OWL.Class))
    local_classes = {cls for cls in local_classes if str(cls).startswith(str(D))}
    targeted_classes = set(shapes.objects(None, SH.targetClass))
    used_local_predicates = {
        predicate for _, predicate, _ in graph
        if str(predicate).startswith(str(D))
    }

    conforms, report, _ = validate(
        graph, shacl_graph=shapes, inference="none",
        meta_shacl=True, abort_on_first=False,
    )
    results = list(report.subjects(RDF.type, SH.ValidationResult))
    report.serialize(OUT / "shacl_validation_report.ttl", format="turtle")
    report.serialize(OUT.parent / "shacl_validation_report.ttl", format="turtle")
    summary = {
        "validator": "pySHACL",
        "knowledge_graph": str(DATA_FILE),
        "shapes_graph": str(SHAPES_FILE),
        "inference": "none",
        "meta_shacl": True,
        "conforms": bool(conforms),
        "validation_results": len(results),
        "data_triples": len(graph),
        "shapes_triples": shape_triples,
        "elapsed_seconds": round(time.monotonic() - start, 2),
        "result_examples": [
            {
                "focus_node": str(report.value(result, SH.focusNode) or ""),
                "source_constraint": str(report.value(result, SH.sourceConstraintComponent) or ""),
                "result_path": str(report.value(result, SH.resultPath) or ""),
                "message": str(report.value(result, SH.resultMessage) or ""),
            }
            for result in results[:20]
        ],
        "coverage": {
            "node_shapes": len(set(shapes.subjects(RDF.type, SH.NodeShape))),
            "property_shapes": len(set(shapes.objects(None, SH.property))),
            "local_ontology_classes_targeted": len(local_classes & targeted_classes),
            "local_ontology_classes_total": len(local_classes),
            "evidence_annotation_class_targeted": OWL.Axiom in targeted_classes,
            "defined_object_properties_covered": len(object_properties & shape_paths),
            "defined_object_properties_total": len(object_properties),
            "instance_predicates_without_shape_path": len(used_local_predicates - shape_paths),
        },
        "independent_integrity_audit": audit_graph(graph),
        "scope_note": "SHACL checks declared structure and values; the independent audit checks cross-record integrity. Neither proves correct troubleshooting interpretation or repair success.",
    }
    (OUT / "shacl_validation_results.json").write_text(json.dumps(summary, indent=2) + "\n")
    print(json.dumps(summary, indent=2))
    if not conforms or any(summary["independent_integrity_audit"][key] for key in summary["independent_integrity_audit"] if key.endswith("errors") or key.startswith("duplicate_") or key == "self_part_links" or key == "evidence_annotations_without_asserted_triple"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
