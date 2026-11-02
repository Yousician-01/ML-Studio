# Projects and data

A Project owns a mutable working recipe and immutable history. Create it with a name, meaningful problem statement, optional description and one task: binary classification, regression or multiclass classification. Task is fixed at creation; metadata edits cannot convert old Runs into another task. Use a separate Project for another objective.

## Managed CSV sources

Upload one CSV through Data. Backend validates a bounded temporary upload, then retains an immutable managed source under a generated Dataset ID. SHA-256 identifies exact source bytes; filenames are metadata, not identity or storage paths. Default maximum source size is **50 MiB** (`MLSTUDIO_MAX_CSV_UPLOAD_BYTES=52428800`). Parsing/profiling memory can be substantially larger.

Parsing is deliberately narrow: conventional comma-separated UTF-8 CSV, optionally a BOM. Empty/unusable, malformed-width, invalid-header, unparseable or non-finite numeric content is rejected. Ordinary missing values (including pandas' internal NaN representation) remain missing; positive/negative infinity is invalid. No encoding/delimiter discovery, Excel/Parquet, URL/database import, joins or separate train/test upload is provided.

Data shows filename, rows/columns, missingness, fingerprint, schema and a read-only source preview of up to 20 rows. It does not send the entire Dataset to the browser. Semantic edits and preparation never modify source bytes.

## Semantics and roles

Physical dtype is an observation; semantic type describes intended meaning. Vocabulary: `continuous`, `categorical`, `binary`, `datetime`, `identifier`, `text`, `unknown`. Deterministic inference remains visible after an override. Effective type is override if present, otherwise inference. **Use inferred** resets it.

Roles are feature, target or excluded. Identifier inference does not silently decide feature intent: explicitly exclude identifiers before training. Only one target is selected. After changing targets, review the former target's role and explicitly include it only if appropriate; do not assume it is a safe feature.

| Task | Target requirement |
| --- | --- |
| Binary | Exactly two distinct non-null observed values, not necessarily 0/1. Missing target rows excluded later. Prepare requires explicit typed positive class. |
| Regression | Finite numeric non-Boolean values with continuous semantics; integer conversion must be lossless in float64. Missing targets excluded, never imputed. Constant/two-valued targets valid. |
| Multiclass | 3-50 homogeneous supported string/integer labels, no missing targets. Integer labels need categorical semantics. Every class must survive the deterministic split. |

Typed labels preserve values such as numeric `1` versus string `"1"`. Validation never silently drops a third class to make a binary task fit. Overrides do not convert source values.

## Replacement, persistence and deletion

Replacement is explicit and creates a new Dataset ID, artifact, fingerprint and schema. Old sources/metadata remain for history; failed ingestion leaves the active source intact. The working pipeline can become stale and needs review. Past Runs are never rebuilt from the replacement source.

SQLite and managed files are authoritative, not browser state or Git branches. Changing workspace/database can reveal different Projects; see [Troubleshooting](../troubleshooting.md).

Project deletion is permanent and blocked by active execution. Secondary MLflow copies may remain; deletion is not secure erasure. No automatic source garbage collection is provided. Stop all writers and back up the complete workspace before migration/recovery; see [CLI storage](../cli.md).
