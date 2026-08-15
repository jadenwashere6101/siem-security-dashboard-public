## 1. Architecture and Schema

- [x] 1.1 Confirm every supported production event ingestion path converges on the shared normalized persistence function and document unsupported direct database writers.
- [x] 1.2 Add additive migration `0037` for the minimal durable source-ingestion health-state and resumable-backfill metadata.
- [x] 1.3 Update `schema.sql` and migration/schema assertions consistently without unnecessary indexes.

## 2. Transactional State Maintenance

- [x] 2.1 Add one canonical Python JSON provenance classifier that matches the existing ordered SQL synthetic policy.
- [x] 2.2 Implement monotonic source-state upsert helpers for canonical push sources.
- [x] 2.3 Wire state maintenance immediately after canonical event insertion on the same cursor/transaction and preserve rollback-only simulator behavior.
- [x] 2.4 Add ingestion tests for every supported route family, synthetic exclusion, monotonic updates, and transaction rollback.

## 3. Historical Backfill

- [x] 3.1 Implement an explicit configurable bounded-batch command with a captured global event-ID high-water mark.
- [x] 3.2 Persist batch state and cursor progress atomically with monotonic timestamp merging.
- [x] 3.3 Add PostgreSQL tests for initialization, incomplete fail-closed state, resumption, idempotency, completion, and concurrent live-ingestion safety.

## 4. Runtime Health and NIST

- [x] 4.1 Replace the events aggregation with bounded state-table and checkpoint-table reads, with no history fallback.
- [x] 4.2 Preserve push freshness, stale/never-established, incomplete-history, and Azure checkpoint semantics.
- [x] 4.3 Prove structurally and with default-planner PostgreSQL tests that runtime health SQL never references `events` and work remains constant as event volume grows.
- [x] 4.4 Preserve NIST `evidence_available`, degraded/unknown `no_evidence_found` prevention, and synthetic operational-evidence regression behavior.

## 5. API and Frontend Contract

- [x] 5.1 Remove uncapped historical counters from the synchronous source-health response and update backend route-contract tests.
- [x] 5.2 Update the frontend service validator and Source Health panel to present explicit health, freshness, durable timestamps, and backfill state.
- [x] 5.3 Run focused frontend tests, production build, dark-theme/accessibility review, and practical visual verification.

## 6. Verification and Handoff

- [x] 6.1 Run focused source-health, ingestion persistence, NIST evidence, migration/lint, and affected backend regression tests without provider calls.
- [x] 6.2 Run Python compilation, schema snapshot validation, `git diff --check`, and strict validation for both related OpenSpecs.
- [x] 6.3 Review the complete diff for unrelated changes and document exact separately authorized VM migration, backfill, verification, and rollback steps.
