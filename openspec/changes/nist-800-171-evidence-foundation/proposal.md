## Why

The SIEM has substantial security telemetry but no reproducible way to relate that telemetry to NIST SP 800-171 Rev. 3 requirements without overclaiming. This change establishes deterministic assessment-support evidence, provenance, status, and collection confidence before any UI or AI explanation layer is added.

## What Changes

- Add an immutable, version-controlled catalog containing exactly 12 approved Rev. 3 requirement mappings, their evidence categories, mapping strength, limitations, source dependencies, and deterministic rules.
- Add bounded deterministic collectors over existing normalized events, alerts, incidents, audit records, source health, approvals, playbooks, and SOAR outcomes.
- Persist declared assessment boundaries, reproducible runs, requirement results, source-health snapshots, and references to canonical evidence records without copying unrestricted raw payloads.
- Add separate evidence status and collection-confidence calculations that cannot be interpreted as control satisfaction.
- Add RBAC-protected APIs for boundaries, runs, results, evidence references, and bounded JSON/CSV exports, with audit records for writes and exports.
- Normalize source aliases to the existing canonical source inventory and preserve existing SOAR execution-mode and synthetic-data distinctions.
- Structurally prohibit overall percentages and claims such as compliant, certified, passed, failed, CMMC compliant, or NIST compliant.
- Exclude frontend components, Anakin integration, provider calls, deployment, and production data changes.

## Capabilities

### New Capabilities

- `nist-evidence-assessment`: Versioned mappings, assessment boundaries, deterministic evidence collection, evidence status, collection confidence, provenance, RBAC APIs, and bounded exports for NIST SP 800-171 Rev. 3 assessment support.

### Modified Capabilities

None.

## Impact

- Backend: new catalog, collector/status engine, persistence service, and Flask blueprint.
- Database: one additive migration and corresponding `schema.sql` snapshot updates for four NIST evidence tables and narrow indexes.
- APIs: new authenticated read surfaces and super-admin boundary/run mutations.
- Governance: no UI, AI, provider routing, overall compliance score, or control-satisfaction decision is introduced.
