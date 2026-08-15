## Context

`core.source_health.aggregate_source_health` currently combines health determination with dashboard statistics in one grouped query over all canonical rows in `events`. The query calculates lifetime counts and maxima and evaluates multi-path JSONB synthetic provenance across full history. At production scale it exceeds Gunicorn's 120-second timeout and blocks both `/source-health` and the synchronous NIST evidence run that snapshots source health.

The reverted `d434339` optimization used `UNNEST` plus a correlated `LATERAL ... ORDER BY created_at DESC LIMIT 256`. Production PostgreSQL selected the global `created_at` index and post-filtered source, so sparse sources walked millions of unrelated rows. A candidate cap also cannot distinguish an old real event hidden behind more than 256 synthetic rows. Runtime history queries are therefore excluded from this design.

All supported production ingestion endpoints (`/ingest`, honeypot, web log, Azure, OpenTelemetry, and pfSense) converge on `engines.ingest_engine.ingest_normalized_event`, which owns the only non-test `INSERT INTO events`. The pfSense listener sends HTTP to `/ingest/pfsense` and has no database access. The detection simulator invokes the same function inside an unconditionally rolled-back transaction. Direct external database insertion is not a supported ingestion architecture and cannot maintain application-owned state.

## Goals / Non-Goals

**Goals:**

- Make runtime push-source health reads proportional only to canonical source count.
- Maintain latest any-event and latest qualifying real-ingestion timestamps atomically with canonical event persistence.
- Preserve push/checkpoint freshness thresholds, synthetic exclusion, fail-closed states, and NIST evidence/confidence behavior.
- Initialize historical state with a bounded, resumable, idempotent, concurrency-safe backfill.
- Replace expensive decorative counters with analyst-visible health and freshness information.

**Non-Goals:**

- A generic telemetry state framework, event rollup service, Redis cache, background worker, new NIST phase, retention redesign, database tuning, Gunicorn tuning, or production deployment.
- Supporting unapproved writers that insert directly into PostgreSQL outside the normalized application path.
- Changing canonical source IDs or freshness thresholds.

## Decisions

### One small row per canonical push source

Migration `0037` adds `source_ingestion_health_state`, keyed by canonical `source`, with `latest_event_at`, `latest_qualifying_real_ingestion_at`, `historical_backfill_complete`, `backfill_high_water_event_id`, `backfill_last_processed_event_id`, and `updated_at`. The two backfill cursor fields are the minimum additional metadata needed to make initialization resumable and auditable. No secondary index is needed because the table has only the handful of push sources and is read by primary key.

Checkpoint sources remain authoritative in `ingestion_checkpoints`; `azure_insights` events do not establish checkpoint health.

### Transactional maintenance at the shared persistence layer

`ingest_normalized_event` obtains the database-assigned `events.created_at` and immediately upserts state for canonical push sources on the same cursor and transaction. `GREATEST` preserves monotonic timestamps for concurrent or out-of-order processing. Synthetic rows update only `latest_event_at`; qualifying real rows update both timestamps. Rollback of the event transaction also rolls back state, including simulator writes.

The Python qualifying decision uses a shared helper in `core.synthetic_data_policy` that follows the same ordered JSON provenance paths and synthetic-value set as the existing SQL helper. This avoids a second definition of real ingestion.

### Bounded global-ID backfill

The explicit Mac-authored/VM-operated backfill captures `MAX(events.id)` once through the primary-key index and stores that high-water mark for every push source. It processes ascending primary-key ID ranges of configurable bounded width, classifies only rows in each range, and commits state maxima plus cursor advancement atomically. A global range is scanned once for all push sources, avoiding per-source rescans and ensuring each transaction has fixed maximum work.

Live rows above the captured high-water mark update state normally. Batch updates use `GREATEST`, so older historical rows cannot overwrite newer live timestamps. Completion is set only after the stored cursor reaches the captured high-water mark. Reruns resume from the committed cursor; completed runs are no-ops. A missing or incomplete state row never triggers a runtime fallback scan.

### Health and dashboard statistics are separate concerns

`aggregate_source_health` reads push rows from `source_ingestion_health_state` and checkpoint rows from `ingestion_checkpoints`; its SQL must not reference `events`. Known qualifying timestamps resolve normally even during backfill. When no qualifying timestamp exists and backfill is incomplete, health is Unknown with an explicit incomplete-history reason. Completed history with no qualifying timestamp remains Unknown/no qualifying ingestion.

The synchronous API removes `events_last_hour`, `events_today`, and `total_events`. `last_event_at` and `ever_seen` come cheaply from durable state, while the frontend displays health, basis, latest qualifying ingestion, and backfill status. A future independently designed rollup may restore counters, but no event-history query is retained for compatibility.

### Rejected alternatives

- Per-source candidate limits cannot preserve stale-versus-never-seen behavior after arbitrarily many synthetic rows.
- Freshness-window plus historical-existence queries remain volume-dependent and planner-sensitive.
- A JSONB partial index hard-codes mutable provenance paths/values and cannot be created concurrently by the current transactional migration runner.
- Trigger-based state duplicates synthetic and canonical-source policy in database DDL; the audited application architecture already has one shared persistence layer.

## Risks / Trade-offs

- [Per-event upsert adds write contention on a hot source row] → keep the row/index minimal and add focused ingestion regression coverage; production throughput is verified after deployment.
- [Synthetic policy changes after state is populated] → keep classification centralized and require an explicit reconciliation/backfill decision with any future policy change.
- [Unsupported direct database writers bypass state] → document direct writes as unsupported and verify all deployed adapters use the HTTP/shared-ingest path.
- [Backfill is interrupted] → atomically persist each bounded batch and resume from stored cursor/high-water metadata.
- [Incomplete history could be mistaken for never seen] → expose completion and use explicit fail-closed Unknown reasoning.
- [API counter removal affects consumers] → update the only repository frontend service/panel and contract tests in the same change.

## Migration Plan

1. **Mac AI:** create migration `0037`, schema snapshot, shared classifier, transactional state maintenance, runtime reads, backfill command, frontend contract, and tests.
2. **Mac AI:** run focused and affected regression suites, frontend production build and visual review, schema validation, Python compilation, diff checks, and strict validation of both OpenSpecs.
3. **VM AI after explicit authorization:** pass the clean-tree gate, sync the approved commit, run migration dry-run/apply through the documented deployment helper, and verify Gunicorn/systemd security gates.
4. **VM AI after explicit authorization:** run the bounded backfill with a conservative batch size until all push rows report complete; record high-water marks, cursors, timestamps, batch counts, duration, and errors without exposing payloads.
5. **VM AI:** verify `/source-health`, NIST assessment execution, synthetic/stale behavior, ingestion state advancement, worker stability, and rollback readiness through production paths.

Application rollback leaves the additive table inert. Do not remove the table or discard backfill progress during rollback. Code must not be deployed before migration `0037`, because the new runtime read is intentionally fail-closed rather than history-scanning.

## Open Questions

None for implementation. Production batch size and scheduling window are VM operational choices based on observed database load, within the bounded command contract.
