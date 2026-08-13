## Context

The repository already has canonical source inventory, normalized telemetry, detections, incidents, audit records, source-health aggregation, approvals, playbook executions, append-only SOAR outcomes, synthetic-data policy, RBAC decorators, and bounded export patterns. Those records can support selected NIST SP 800-171 Rev. 3 requirements, but they cannot determine the legal CUI boundary or overall requirement satisfaction.

The implementation is Mac-owned source work. Production migration and runtime verification remain a separately authorized VM handoff.

## Goals / Non-Goals

**Goals:**

- Provide exactly 12 immutable v1 mappings and bounded deterministic collectors.
- Persist user-declared assessment scope, reproducible runs, per-requirement results, source-health snapshots, and canonical record references.
- Keep mapping strength, evidence status, and collection confidence separate.
- Preserve occurrence, ingestion, detection, outcome, and verification timestamps.
- Reuse canonical source, RBAC, audit, synthetic-data, and SOAR semantics.
- Expose bounded read/write APIs and deterministic JSON/CSV exports.

**Non-Goals:**

- Determining the legal CUI boundary or requirement satisfaction.
- Producing an overall score, pass/fail result, certification, or compliance claim.
- Admin-editable mappings, UI, Anakin, prompts, provider calls, deployment, or production mutation.

## Decisions

### Version-controlled catalog and runtime PostgreSQL records

Code owns framework identity, official names, mapping strength, required evidence categories, source dependencies, limitations, collector versions, and catalog hash. PostgreSQL owns boundaries, runs, results, source-health snapshots, and evidence references. This hybrid avoids mutable control semantics while retaining reproducibility. A database-editable catalog was rejected because v1 mappings require reviewable source control.

### Declared boundary as input

Boundaries store selected canonical source IDs/types, optional environments, and a bounded default window. They explicitly state that scope is declared, not discovered. Source aliases are normalized through the canonical inventory adapter before persistence; aliases never become mapping authority.

### Synchronous bounded run

Starting a run validates a maximum 168-hour window, snapshots source health, executes small collector queries with per-category reference limits, evaluates all 12 mappings, and persists the result transactionally. A new queue/worker was rejected for this bounded foundation; it can be introduced later only if measured runtime requires it.

### Category bundles and pure status engine

Collectors return category bundles containing total count, bounded references, omitted count, health dependencies, completion state, and limitations. A pure status engine emits `evidence_available`, `partial_evidence`, `no_evidence_found`, or `not_assessable_by_siem`, independently from `healthy`, `degraded`, or `unknown` confidence. Zero records can become `no_evidence_found` only with completed collectors, Healthy dependencies, and a meaningful window.

### Reference-only provenance

Evidence rows retain canonical table/entity IDs, timestamps, sanitized metadata/query hash, execution classification, versions, and short redacted summaries. They do not copy `raw_payload`, prompts, secrets, hidden reasoning, or unrestricted record bodies. Truncation is explicit.

### Conservative operational classification

Explicit provenance and the existing synthetic policy identify demo/test records; documentation ranges and confirmed fixture IDs are defense-in-depth. Synthetic-only evidence cannot establish operational availability. SOAR external execution requires real mode, succeeded state, and `external_executed=true`; approvals and other states retain their actual meaning.

### Existing authorization model

Analysts and super-admins may read runs, results, evidence, and exports. Only super-admins may create/update boundaries or initiate runs. Writes and exports use the existing audit helper and record only IDs, counts, and safe metadata. Viewer access remains denied because existing sensitive evidence routes use analyst-or-super-admin authorization.

## Risks / Trade-offs

- [Source health lacks a checkpoint or is stale] → emit Unknown/Degraded confidence and never a negative evidence conclusion.
- [Legacy aliases differ from canonical inventory] → normalize at the boundary and collector filter edge; test persisted IDs.
- [Occurrence timestamps are absent] → preserve ingestion time separately, mark the reference limitation, and keep timestamp evidence partial.
- [Collectors over-query large tables] → require bounded windows, indexed filters, count separately, and cap stored references.
- [Evidence is mistaken for satisfaction] → prohibited vocabulary, no overall percentage, explicit limitation fields, and separate mapping/status/confidence types.
- [Synthetic heuristics misclassify data] → prefer explicit provenance; label exclusions and keep heuristics conservative and testable.
- [Synchronous run latency grows] → keep v1 queries bounded and defer queue architecture until measurement justifies it.

## Migration Plan

1. Apply additive migration `0036` after an authorized clean deployment.
2. Deploy backend source and verify schema snapshot/version, RBAC, bounded run creation, exports, and audit rows.
3. Rollback application code without deleting evidence tables; the additive tables are inert when routes are absent.

## Open Questions

None for v1. UI and Anakin explanation require separate OpenSpecs after production evidence collection is verified.
