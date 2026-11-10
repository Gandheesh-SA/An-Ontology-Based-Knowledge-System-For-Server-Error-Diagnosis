# Dataset split

The main dataset is ../events.json. Main, TRAIN and TEST use schema 2.1.0.
Each event contains exactly these thirteen fields:

record_id, vendor, event_code, error_class, event_names, messages, arguments,
severity, explanation, category, cause, recommended_action, source.

There are no nested troubleshooting/solution groups, step lists, component-type
labels, section fields or embedded review histories in these event records.
The cause field is one string containing the documented alternatives and any
explicit Cisco Cause classification. recommended_action preserves the complete
source instruction text. Where several solutions exist, their original headings
remain in both text fields so the alternatives can be distinguished.

| Partition | Records |
|---|---:|
| TRAIN | 2,904 |
| TEST | 323 |
| Total | 3,227 |

This folder keeps four JSON files:

| File | Purpose |
|---|---|
| train.json | Records used to build the training knowledge graph. |
| test.json | Held-out records, including their documented recommendations. |
| test_queries.json | Message-only evaluation inputs, without expected recommendations. |
| ground_truth.json | Evaluator-only expected recommendations and existing relevance judgments. |

The unused local selection_audit.json, split_manifest.json and verification.json
reports were removed after checking partition integrity and query/answer mappings.
Original split-generation records under VERSION-1 were not changed. The PDF-source
verification record is kept with its consumer at
output/combined_record_concepts/source_verification.json, relative to the repository
root; it is not an additional dataset partition.

The original record IDs, included events and TRAIN/TEST assignments are retained.
The 323 TEST records map to 316 existing query inputs. test_queries.json and
ground_truth.json are unchanged because their messages and source recommendations
are preserved. Existing relevance judgments have not been expanded or rescored.

Main, TRAIN and TEST contain schema_version, sources and records. The source index
stores document titles, editions, filenames and URLs once. Every event retains its
document identifier and physical PDF page references.

All four local vendor PDFs were re-read for the schema conversion. category now
stores one primary technical topic, such as Memory, Storage, Power or Thermal.
Dell message groups are mapped to common topic names. For entries without a useful
topic heading, deterministic rules use the event name, message, explanation or
documented cause. Recommendations do not determine the category. These labels are
dataset indexing classifications, not necessarily fields printed by the vendor or
expert-confirmed diagnoses. Severity preserves the explicitly printed source value;
missing severity remains null. Arguments are kept only where documented.

The source and split checks are automated, not expert validation of every cause or
proof that a recommendation repairs an actual incident. Historical ontology/KG files
and retrieval results were not rebuilt for this dataset schema. Their consumers
require a schema migration before they can use these files correctly.
