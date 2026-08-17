## Why

Production source-health aggregation currently scans the complete `events` history and evaluates JSONB provenance across millions of rows. At current volume `/source-health` exceeds Gunicorn's 120-second timeout, consumes one of only two workers, and prevents synchronous NIST evidence runs from obtaining their source-health snapshot.

Commit `d434339` attempted to bound the read with a per-source `LATERAL` lookup, but PostgreSQL selected the single-column `created_at` index and scanned millions of unrelated pfSense rows for sparse sources. That change was reverted by production baseline `e871e2f`; the health-critical path must therefore stop deriving push-source state from runtime event-history queries.

## What Changes

- Add durable, per-canonical-push-source ingestion health state maintained transactionally with normalized event persistence.
- Preserve checkpoint-driven health for `azure_insights` through `ingestion_checkpoints`.
- Add a bounded, resumable, idempotent historical backfill that captures a high-water mark and fails closed until historical processing is complete.
- Make `/source-health` and NIST health snapshots read only the small state/checkpoint tables, with work proportional to canonical source count.
- Remove rolling historical event counters from the health-critical path while retaining a durable lifetime total maintained during ingestion.
- Preserve synthetic exclusion, freshness thresholds, NIST evidence/confidence semantics, RBAC, and fail-closed behavior.

## Capabilities

### New Capabilities

- `source-ingestion-health-state`: Durable push-source freshness, transactional maintenance, safe historical initialization, bounded source-health reads, checkpoint compatibility, and the analyst-facing source-health contract.

### Modified Capabilities

None.

## Impact

- Backend: normalized ingestion persistence, synthetic provenance classification, source-health aggregation, NIST snapshot consumption, and a backfill command.
- Database: one additive migration and the canonical schema snapshot for a tiny per-source state table.
- API/frontend: source-health response validation and the Source Health panel present explicit health/freshness fields plus a durable informational lifetime total.
- Operations: a separately authorized VM migration, resumable backfill, service restart, and production verification are required after an approved commit; this change performs none of those production actions.
