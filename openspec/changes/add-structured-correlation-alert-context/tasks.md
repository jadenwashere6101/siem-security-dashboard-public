# Tasks: Add Structured Correlation Alert Context

Implementation must be reviewed before code changes begin. Do not implement from this spec creation step.

## Pre-Implementation Audit

- [ ] Re-read `migrations/0002_base_siem_core.sql` and current later migrations to confirm `alerts` has no JSONB context column.
- [ ] Re-read `schema.sql` and schema migration tests to match the existing migration workflow.
- [ ] Re-read `engines/correlation_engine.py` for every correlation alert insert path.
- [ ] Re-read `helpers/enrichment_helpers.py` and `/alerts` serialization in `routes/alerts_events_routes.py`.
- [ ] Re-read existing correlation and API contract tests before changing behavior.

## Schema Migration

- [ ] Add a new migration that adds `alerts.context JSONB NOT NULL DEFAULT '{}'::jsonb`.
- [ ] Keep the migration additive and idempotent with `ADD COLUMN IF NOT EXISTS`.
- [ ] Do not alter existing alert columns or constraints.
- [ ] Do not add raw event payload storage to alerts.
- [ ] Update `schema.sql` to include the new column in the `alerts` table.
- [ ] Update schema migration tests to verify the migration and snapshot.

## Correlation Context Writes

- [ ] Update `generate_correlated_activity_alerts()` to persist structured context for newly created `correlated_activity` alerts.
- [ ] Include contributing alert IDs, alert types, sources, source types, matched rule/correlation type, matched window minutes, and matched alert count where available.
- [ ] Update `generate_targeted_correlation_alerts()` to persist structured context for `web_to_app_attack_pattern`.
- [ ] Update `generate_targeted_correlation_alerts()` to persist structured context for `spray_then_success_pattern`.
- [ ] Update `generate_targeted_correlation_alerts()` to persist structured context for `cloud_app_error_pattern`.
- [ ] Include targeted matched groups where available.
- [ ] Preserve existing correlation matching logic exactly.
- [ ] Preserve existing duplicate suppression exactly.
- [ ] Preserve existing alert messages for human readability.
- [ ] Do not change SOAR queue or playbook handoff behavior.

## API and Enrichment

- [ ] Update `/alerts` query serialization to include `alerts.context`.
- [ ] Update `enrich_alert_with_correlation_context()` to prefer structured context for correlation enrichment.
- [ ] Preserve old message parsing as fallback for historical `correlated_activity` alerts with empty context.
- [ ] Ensure targeted correlation alerts with empty context do not fabricate missing contributing details.
- [ ] Keep API response changes additive and backward compatible.
- [ ] Do not expose raw event payloads through `alerts.context`.
- [ ] Do not change frontend unless API compatibility proves insufficient.

## Tests

- [ ] Add or update migration tests for `alerts.context`.
- [ ] Add or update schema snapshot tests for `alerts.context`.
- [ ] Update `tests/test_correlated_activity.py` to assert structured context is persisted.
- [ ] Update `tests/test_targeted_correlation.py` to assert structured context is persisted for all targeted correlation types.
- [ ] Update enrichment helper tests to prove context is preferred over message parsing.
- [ ] Add fallback tests for old `correlated_activity` alerts with empty context and legacy message text.
- [ ] Add tests for malformed or non-dict context returning safe output.
- [ ] Update `/alerts` API contract tests to verify structured correlation context fields without breaking existing fields.
- [ ] Preserve duplicate suppression tests.
- [ ] Preserve modern SOAR queue/playbook handoff tests.

## Verification

- [ ] Run `python3 -m py_compile engines/correlation_engine.py helpers/enrichment_helpers.py routes/alerts_events_routes.py`.
- [ ] Run focused schema migration tests.
- [ ] Run `python3 -m pytest tests/test_correlated_activity.py -v`.
- [ ] Run `python3 -m pytest tests/test_targeted_correlation.py -v`.
- [ ] Run `python3 -m pytest tests/test_alerts_api_contracts.py -v`.
- [ ] Run focused ingest normalized event tests if correlation return/handoff code is touched.
- [ ] Run focused SOAR queue/playbook handoff tests if alert return dictionaries are touched.
- [ ] Run `git diff --check`.
- [ ] Run `git status --short`.

## Safety Boundaries

- [ ] Do not change event `raw_payload` behavior.
- [ ] Do not change detection rule logic.
- [ ] Do not change correlation matching logic.
- [ ] Do not change SOAR queue/playbook behavior.
- [ ] Do not weaken approvals, protected-target behavior, retries, leases, idempotency, dead letters, or audit logging.
- [ ] Do not change integration adapter behavior.
- [ ] Do not enable real firewall execution.
- [ ] Do not refactor broadly.
- [ ] Do not commit until reviewed.

