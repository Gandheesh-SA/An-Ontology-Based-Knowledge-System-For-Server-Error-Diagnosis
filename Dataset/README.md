# Dell PowerEdge Critical and Warning Event Dataset

## Overview

This dataset contains **6,152 Dell PowerEdge event definitions** extracted from the *PowerEdge Servers Error and Event Messages Reference Guide*. It includes **2,476 Critical** and **3,676 Warning** entries. Informational entries are outside this release.

Each entry describes a message Dell may report and its documented response. These are **reference definitions**, not observed server incidents or evidence that a repair succeeded.

The main file is [`events.json`](events.json). It contains the original extracted fields and an added `knowledge` section for building and evaluating a troubleshooting knowledge graph.

## Source and scope

- **Document:** Dell, *PowerEdge Servers Error and Event Messages Reference Guide*, July 2026, Rev. A00.
- **Official PDF:** https://dl.dell.com/content/manual64973867-poweredge-servers-error-and-event-messages-reference-guide.pdf?language=en-us
- **PDF length:** 3,849 pages.
- **Source SHA-256:** `8a68b6f765d4d1265cc198686198fdee7906ab8a09f7dc48fca9865b3bceec98`.
- **Selection:** All entries marked Critical or Warning. No additional hardware-only filter was applied. Configuration, Audit, Updates and other categories are therefore present alongside hardware events.

The complete original message, explanation and response remain in the JSON. `source_pages` and `source_text` support checking an entry against the PDF.

## Record structure

| Field | Meaning |
| --- | --- |
| `record_id`, `event_code` | Dataset ID and Dell's event code. |
| `event_group`, `category`, `severity` | Dell's grouping, category and original severity. |
| `message`, `arguments` | Reported message and documented placeholder meanings. |
| `explanation` | Dell's detailed description, including any possible causes it states. |
| `recommended_action` | Dell's full recommended response, in its original order. |
| `notes`, `additional_fields` | Other source information, such as LCD messages and alert channels. |
| `source_pages`, `source_text` | PDF page references and extracted source passage. |
| `knowledge` | Structured, source-backed **extraction candidates** described below. |

An absent optional source field is represented by `null` or an empty list. The guide sometimes says `No detailed description available.`; that literal text is retained and is not treated as an explanation of a cause.

## Structured knowledge

The `knowledge` section is derived from the record's `message`, `explanation` and `recommended_action`. It has these fields:

| Field | How it was obtained | Interpretation |
| --- | --- | --- |
| `reported_condition_text` | Exact copy of `message`. | The condition **reported by the message**, not a confirmed incident diagnosis. |
| `component_type_candidates` | Exact component phrases found in the message. | Candidate component concepts. An empty list does not prove that no component is involved. |
| `technical_property_candidates` | Exact property phrases found in the message, such as RPM or voltage. | Candidate property concepts. |
| `possible_explanations` | Sentences in `explanation` containing causal or possibility wording. | Source-grounded **candidate explanations**. A sentence may contain multiple alternatives; it has not been split into confirmed root causes. |
| `response_segmentation`, `response_items` | Numbered steps where a `1, 2, ...` sequence is clear; otherwise sentence segments. | Preserves order. `numbered_instruction` is an explicitly numbered source segment; `sentence_candidate`, `preamble_candidate` and `context_sentence` need interpretation before being used as atomic instructions. |
| `operation_type_candidates`, `target_component_candidates`, `artifact_type_candidates` | Exact phrases found within each response item. | Possible operation, target and artifact concepts; mentions alone do not establish a complete relationship. |
| `explanation_links` | Empty pending review. | Do **not** infer that an instruction investigates or corrects a particular explanation merely because both occur in the same entry. |

`source_start` and `source_end` are character offsets into the original source field. Every candidate text and phrase can therefore be checked against the retained source wording. The status `automated_source_grounded_candidates_not_expert_validated` applies to the added candidate layer.

### Example: BAT0009

The source message says the storage battery is absent. Dell's explanation says that a disconnect or a thermal exception **may** make it appear absent. The response contains three numbered instructions: verify installation, reseat or reconnect the battery and cables, and check thermal logs. The dataset separates those three source instructions, while leaving the instruction-to-explanation links empty until they are checked. It does not claim that either possible explanation was the actual cause or that a repair succeeded.

## How to use the dataset

1. Open `events.json` and read the `events` array. Each object is one Dell event definition. Find an entry by `event_code`, or filter by `severity` and `category`.
2. Compare an incoming server message with `message`. The `arguments` field explains placeholders such as `arg1`. Read `explanation` for Dell's description and `recommended_action` for the complete documented response.
3. Use `knowledge.reported_condition_text` and `knowledge.response_items` when building a graph or displaying the response as an ordered list. The original text remains available in the main fields.
4. Use `knowledge.possible_explanations`, component, property, operation and artifact candidates as **review prompts**. Check their context and `source_pages` against the guide before asserting a cause, an instruction target or an instruction-to-explanation link in the KG.

For example, from this directory:

```python
import json
from pathlib import Path

events = json.loads(Path("events.json").read_text(encoding="utf-8"))["events"]
event = next(item for item in events if item["event_code"] == "BAT0009")

print(event["message"])
print(event["recommended_action"])
for item in event["knowledge"]["response_items"]:
    print(item["order"], item["text"])
```

For KG construction, an entry can directly supply an `EventDefinition`, its reported message and its documented `RecoveryProcedure`. Review the extracted candidates before creating stronger links such as an instruction **investigating** or **attempting to correct** a particular explanation. An empty candidate list means the extraction did not identify one; it is not evidence that the concept is absent from the guide.

