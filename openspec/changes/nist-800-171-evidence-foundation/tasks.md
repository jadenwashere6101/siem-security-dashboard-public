## 1. Catalog and Deterministic Semantics

- [x] 1.1 Implement the immutable 12-mapping Rev. 3 catalog, evidence categories, limitations, versions, and deterministic catalog hash.
- [x] 1.2 Implement canonical source alias normalization without creating a second source registry.
- [x] 1.3 Implement pure evidence-status and collection-confidence evaluation, including stale/unknown health behavior.
- [x] 1.4 Implement explicit synthetic/test and SOAR operational-evidence classification.

## 2. Bounded Evidence Collection

- [x] 2.1 Implement bounded event, alert/detection, audit, incident, and investigation evidence collectors.
- [x] 2.2 Implement bounded source-health, approval, playbook, response-outcome, and boundary-traffic collectors.
- [x] 2.3 Preserve occurrence/ingestion/outcome/verification timestamps, truncation, counts, safe summaries, and query hashes without copying unrestricted raw payloads.
- [x] 2.4 Wire requirement-specific category plans and limitations for exactly the 12 approved mappings.

## 3. Persistence and Migration

- [x] 3.1 Add migration `0036` for assessment boundaries, runs, requirement results, evidence references, constraints, and narrow indexes.
- [x] 3.2 Update `schema.sql` canonical snapshot and schema-version marker.
- [x] 3.3 Implement boundary validation/create/update/list/read persistence helpers.
- [x] 3.4 Implement transactional assessment-run, result, evidence-reference, source-health snapshot, and summary persistence helpers.

## 4. API, RBAC, Audit, and Export

- [x] 4.1 Add the NIST evidence blueprint and register it without frontend changes.
- [x] 4.2 Add analyst/super-admin read APIs for boundaries, run summaries, results, and bounded evidence references.
- [x] 4.3 Add super-admin boundary mutations and assessment-run initiation with safe audit events.
- [x] 4.4 Add deterministic bounded JSON and CSV run exports with provenance and safe export auditing.
- [x] 4.5 Verify API/export contracts contain no overall score, pass/fail label, certification status, raw payload, secret, prompt, or reasoning field.

## 5. Focused Tests

- [x] 5.1 Add catalog tests for exactly 12 official mappings, strengths, canonical sources, versions/hash, and prohibited claims.
- [x] 5.2 Add status/confidence tests for complete, partial, healthy-empty, degraded-empty, unknown, stale, and not-assessable inputs.
- [x] 5.3 Add one meaningful deterministic collector/status test for each of the 12 mappings.
- [x] 5.4 Add provenance, timestamp, truncation, query-hash, raw-payload exclusion, SOAR-state, and synthetic-evidence tests.
- [x] 5.5 Add migration/schema tests for additive tables, constraints, indexes, forward application, and snapshot version.
- [x] 5.6 Add API/RBAC/audit/export tests for authorized reads, denied writes, audited writes/exports, deterministic ordering, and secret/overclaim protection.

## 6. Verification and Handoff

- [x] 6.1 Run focused NIST catalog, engine, collector, persistence, route, export, migration, source-health, RBAC, audit, incident, and SOAR tests.
- [x] 6.2 Run relevant existing acceptance/regression tests without real AI providers.
- [x] 6.3 Run Python compilation, schema snapshot validation, `git diff --check`, and strict OpenSpec validation.
- [x] 6.4 Review the final diff for unrelated changes and document remaining production migration/API verification for the VM owner.
