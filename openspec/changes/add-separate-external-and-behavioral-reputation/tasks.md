# Tasks: Separate External and Behavioral Reputation

Implementation must be reviewed before code changes begin. Do not implement from this spec creation step.

## Pre-Implementation Audit

- [x] Re-read `core/ip_helpers.py` and document the difference between `lookup_ip_reputation()` and `get_ip_reputation()`.
- [x] Re-read all alert creation paths in `engines/detection_engine.py` that store `alerts.reputation_*`.
- [x] Re-read all correlation alert creation paths in `engines/correlation_engine.py` that store `alerts.reputation_*`.
- [x] Re-read `routes/alerts_events_routes.py` for `GET /alerts`, `GET /events/search`, and `POST /alerts/backfill-reputation`.
- [x] Re-read report/export helpers in `helpers/query_helpers.py` and `helpers/reporting_helpers.py`.
- [x] Re-read `engines/playbook_engine.py` to confirm playbook trigger reputation semantics stay unchanged.
- [x] Re-read frontend alert reputation display components before editing.

## Backend API Changes

- [x] Update `GET /alerts` to return stored alert `reputation_score`, `reputation_label`, `reputation_source`, and `reputation_summary` from the database row.
- [x] Stop overwriting top-level alert `reputation_*` response fields with `get_ip_reputation()` values.
- [x] Add `behavioral_reputation` object to each alert response.
- [x] Populate `behavioral_reputation.score` from `get_ip_reputation()["reputation_score"]`.
- [x] Populate `behavioral_reputation.label` from `get_ip_reputation()["reputation_label"]`.
- [x] Populate `behavioral_reputation.source` with `siem_internal`.
- [x] Populate `behavioral_reputation.summary` from `get_ip_reputation()["reputation_summary"]`.
- [x] Populate `behavioral_reputation.contributing_signals` from `get_ip_reputation()["contributing_signals"]`.
- [x] Preserve top-level `contributing_signals` as a compatibility alias if current frontend/tests still require it.
- [x] Do not change `GET /events/search` behavior except optional additive naming clarity.
- [x] Do not change alert creation logic.
- [x] Do not change detection logic.
- [x] Do not change correlation logic.
- [x] Do not change SOAR queue/playbook behavior.
- [x] Do not change AbuseIPDB/mock/fallback provider behavior.
- [x] Keep `/alerts/backfill-reputation` as an external reputation backfill endpoint.

## Frontend Changes

- [x] Update `frontend/src/components/AlertTableRow.js` to distinguish external threat intelligence from behavioral reputation.
- [x] Update `frontend/src/components/AlertReputationDetails.js` to render both reputation concepts.
- [x] Update `frontend/src/components/AlertDetailsPanel.js` to render both reputation concepts.
- [x] Update `frontend/src/components/AlertCorrelationSignals.js` to read behavioral contributing signals from `behavioral_reputation.contributing_signals` with compatibility fallback.
- [x] Update `frontend/src/components/MapView.js` to avoid a single ambiguous `Reputation` label.
- [x] Update `frontend/src/utils/alertDisplay.js` only if badge styling needs to support both external and behavioral labels.
- [x] Leave threat-hunt event views behavioral-only unless API changes require additive handling.

## Tests

- [x] Update `tests/test_alerts_api_contracts.py` so `GET /alerts` proves stored external `reputation_*` fields are preserved.
- [x] Add backend API tests proving `behavioral_reputation` is present and separate.
- [x] Add backend API tests proving top-level `reputation_source` is not overwritten with `siem_internal`.
- [x] Preserve or update tests for top-level `contributing_signals` compatibility.
- [x] Update `tests/test_backfill_reputation_api_contracts.py` to clarify external backfill behavior if needed.
- [x] Preserve event search API tests for behavioral scoring.
- [x] Add or update frontend tests for alert reputation display.
- [x] Add or update map/detail/table tests if those components have existing coverage.

## Verification

- [x] Run `python3 -m py_compile routes/alerts_events_routes.py core/ip_helpers.py`.
- [x] Run `python3 -m pytest tests/test_alerts_api_contracts.py -v`.
- [x] Run `python3 -m pytest tests/test_backfill_reputation_api_contracts.py -v`.
- [x] Run `python3 -m pytest tests/test_events_search_api_contracts.py -v`.
- [x] Run focused frontend tests for alert table/detail/map components.
- [x] Run `git diff --check`.
- [x] Run `git status --short`.

## Safety Boundaries

- [x] Do not perform schema migration unless a reviewed implementation finding proves it is required.
- [x] Do not remove AbuseIPDB support.
- [x] Do not remove internal behavioral scoring.
- [x] Do not redesign detection logic.
- [x] Do not redesign enrichment providers.
- [x] Do not change playbook trigger behavior without a separate reviewed decision.
- [x] Do not change SOAR queue/playbook behavior.
- [x] Do not weaken approvals, retries, leases, idempotency, dead letters, or protected-target behavior.
- [x] Do not commit until reviewed.
