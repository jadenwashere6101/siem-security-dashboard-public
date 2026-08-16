## Why

The production-verified NIST SP 800-171 Rev. 3 evidence foundation has deterministic runs, requirement results, provenance, and exports, but analysts do not yet have a cohesive UI for using them. Anakin can add useful explanation only if persisted NIST facts remain authoritative and the optional model path cannot select, alter, or overstate evidence.

## What Changes

- Add an analyst-facing NIST Evidence Workspace for selecting declared boundaries and persisted runs, reviewing the 12 stored results, drilling into bounded provenance, exporting results, and explicitly starting assessments when authorized.
- Add a bounded persisted run-history API and fail-closed ownership validation for requirement evidence reads.
- Add an isolated asynchronous `nist_evidence_explanation` workflow that accepts immutable identifiers only, revalidates all bindings in the worker, loads a capped persisted context, and uses the existing local `fast_triage` profile.
- Add strict output-schema, citation, identity, deterministic-state, truncation, confidence, operational-classification, and compliance-overclaim validation. Any failure discards all model prose.
- Preserve existing Analyst+/super-admin RBAC, owner-bound workflow polling, safe audit metadata, deterministic exports, and frontend design/navigation conventions.
- Keep the workspace fully usable when AI is unavailable. Evidence availability remains assessment support and does not determine requirement satisfaction, compliance, certification, or CMMC status.
- Intentionally exclude planner, Deep Investigate, session memory, SOC tools, source-health changes, NIST collector/mapping changes, provider-routing changes, raw evidence dumps, automatic assessments, scores, and AI result overrides.

## Capabilities

### New Capabilities

- `nist-analyst-workspace-grounded-explanation`: Bounded NIST workspace reads and controls plus isolated, asynchronous, non-authoritative explanations grounded only in persisted NIST result and evidence identifiers.

### Modified Capabilities

None.

## Impact

- Backend: NIST routes/store helpers, one isolated explanation service, and narrow async worker dispatch.
- Database: one additive migration extending the existing workflow constraint; no new table or index.
- Frontend: one SOC navigation entry, NIST service, workspace/detail surfaces, and async explanation polling.
- Tests: NIST API/persistence, workflow worker/gateway, RBAC/audit, migration/schema, and focused/full frontend coverage.
- Operations: Mac-owned source implementation only. Migration, worker/backend deployment, frontend sync, Ollama/browser-path verification, and production acceptance remain separately authorized VM work.
