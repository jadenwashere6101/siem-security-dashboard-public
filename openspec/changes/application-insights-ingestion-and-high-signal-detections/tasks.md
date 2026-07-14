## 1. Checkpoint and paging foundation (Mac AI)

- [x] 1.1 Add migration creating `ingestion_checkpoints` (`connector_name TEXT PRIMARY KEY`, `last_processed_at TIMESTAMPTZ`, `last_poll_status TEXT`, `last_poll_counts JSONB`, `updated_at TIMESTAMPTZ`).
- [x] 1.2 Add `core/ingestion_checkpoint_store.py` with `get_checkpoint(connector_name)` and `upsert_checkpoint(connector_name, last_processed_at, poll_status, poll_counts)`.
- [x] 1.3 Add `GET /ingest/azure/checkpoint` and `PATCH /ingest/azure/checkpoint` routes guarded by `require_azure_api_key()`; `GET` returns a bounded default (`NOW() - 1 hour`, floor 15 minutes) when no row exists yet.
- [x] 1.4 In `siem-azure-function/function_app.py`, replace the fixed `ago({QUERY_WINDOW_MINUTES}m)` KQL bound with a checkpoint value read via the new endpoint at the start of each poll.
- [x] 1.5 Implement paging in `_query_recent_telemetry`: query in pages of `PAGE_SIZE` (app setting, default 25) ordered by `TimeGenerated asc`, looping up to `MAX_POLL_PAGES` (app setting, default 10) within one invocation.
- [x] 1.6 After successfully processing each page, advance the in-memory watermark to that page's last `TimeGenerated`; call `PATCH /ingest/azure/checkpoint` once at the end of the poll with the final watermark and poll outcome/counts.
- [x] 1.7 Add bounded retry with backoff (3 attempts) around `_query_recent_telemetry` and around `forward_telemetry_to_siem` per row.
- [x] 1.8 Write backend tests for the checkpoint store and routes: get returns bounded default when absent; patch persists watermark/status/counts; RBAC/API-key guard enforced.
- [x] 1.9 Run focused tests: new checkpoint store/route tests, `tests/test_ingest_api_contracts.py`.
- [x] 1.10 Run schema/migration validation for the new migration.

## 2. Classification fix and expanded telemetry coverage (Mac AI)

- [x] 2.1 In `adapters/azure_insights_adapter.py::normalize_azure_insights_telemetry`, add the `result_code in {401, 403}` branch returning `event_type = "unauthorized_access"`, `severity = "medium"` (base event severity; alert severity comes from the new threshold rule).
- [x] 2.2 Confirm `siem-azure-function/function_app.py::_classify_telemetry_row`'s existing `unauthorized_access` mapping for 401/403 now agrees end-to-end with the backend; add a regression test pinning this agreement.
- [x] 2.3 Extend `APP_INSIGHTS_QUERY` in `function_app.py` to add `AppDependencies` rows where `Success == false` and `AppAvailabilityResults` rows where `Success == false`, using the same `union isfuzzy=true` shape as the existing rows.
- [x] 2.4 Remove the `AppTraces` clause matching `"HTTP request received"` from `APP_INSIGHTS_QUERY`.
- [x] 2.5 Extend `adapters/azure_insights_adapter.py` and `_classify_telemetry_row`/`_row_to_siem_telemetry` in `function_app.py` to map dependency-failure and availability-failure rows to `event_type = "dependency_failure"` / `"availability_failure"` consistently between both layers.
- [x] 2.6 Write/update unit tests: 401/403 requests classify as `unauthorized_access` on both layers; dependency/availability failure rows classify consistently; successful dependency calls and the removed trace pattern are not ingested.
- [x] 2.7 Update `docs/azure-integration-setup.md` to describe the checkpoint-driven query, the new tables queried, and the removed trace query.
- [x] 2.8 Run focused tests: adapter tests, `tests/test_ingest_normalized_event.py`.

## 3. New detections (Mac AI)

- [x] 3.1 Add `app_insights_unauthorized_access_threshold` defaults (threshold, window_minutes, active, description) to `engines/detection_config.py`.
- [x] 3.2 Add `"app_insights_unauthorized_access_threshold": RuleApplicability("source_specific", frozenset({AZURE_INSIGHTS}))` to `engines/detection_applicability.py`; update `validate_rule_inventory` coverage.
- [x] 3.3 Implement the threshold detection function in `engines/detection_engine.py` (same shape as `_generate_http_error_threshold_alerts_core`), scoped to `unauthorized_access` events for the `azure_insights`/`cloud_api` source, severity `high`.
- [x] 3.4 Add `azure_auth_abuse_exception_correlation` as a fourth rule entry in `generate_targeted_correlation_alerts`'s `rules` tuple in `engines/correlation_engine.py`: `severity: "high"`, matching `AZURE_INSIGHTS`-source rows with `alert_type` in `{app_insights_unauthorized_access_threshold, password_spraying_threshold, failed_login_threshold}` for one required group and `application_exception_threshold` for the other.
- [x] 3.5 Register `azure_auth_abuse_exception_correlation`'s correlation weight in `core/ip_helpers.py`'s `correlation_signal_config` (consistent with existing correlation alert types) so it contributes to reputation scoring like its siblings.
- [x] 3.6 Confirm (via test) that neither new rule can produce `severity = "critical"` under any configured threshold, and that a correlation alert for a source IP with an already-open `successful_login_after_spray` alert links to that incident without a second `require_approval`/`block_ip` cycle.
- [x] 3.7 Add an investigation-only playbook definition (enrich_context, monitor, notify_slack — no require_approval/block_ip) for each new rule, following the existing `core_playbook_pack_v1` shape.
- [x] 3.8 Write/update unit tests: threshold rule fires only for `azure_insights` source; correlation rule fires only when both signals are open; correlation rule does not fire on an isolated exception spike; severity ceiling assertions.
- [ ] 3.9 (Phase 2, sequence last, droppable without renegotiating scope) Add `azure_dependency_failure_after_recon_pattern` correlating `AppDependencies`-failure with `pfsense_firewall_port_scan`/`honeypot_scanner_detected` on the same source IP, same investigation-only shape and severity ceiling as 3.4–3.8.
- [x] 3.10 Run focused tests: `tests/test_targeted_correlation.py`, `tests/test_source_aware_detection.py`, detection-config/applicability tests.

## 4. Health visibility (Mac AI)

- [x] 4.1 Extend `core/source_health.py::aggregate_source_health` to include `last_poll_status`, `last_poll_at`, `last_poll_counts` for sources with an `ingestion_checkpoints` row.
- [x] 4.2 Confirm the existing Source Health API/route surfaces the new fields without a new endpoint.
- [x] 4.3 Write/update tests in `tests/test_source_health.py`: poll failure is distinguishable from no-new-telemetry; sources without a checkpoint row are unaffected (fields absent/null, no error).
- [x] 4.4 Run focused tests: `tests/test_source_health.py`.

## 5. Matrix dependency note and documentation (Mac AI)

- [x] 5.1 If `critical-response-consistency-and-severity-matrix` has been implemented by the time this phase starts, add both new rules' `why` text and severity metadata to `engines/severity_response_matrix.py`'s per-rule mapping table; otherwise, leave a tracked follow-up note (this task, left unchecked with a comment referencing the dependency) rather than blocking this change on the other one's implementation order.
- [x] 5.2 Confirm no frontend files are modified in this change (UI is deferred per `design.md`'s scope-planning recommendation).

## 6. Verification and handoff (Mac AI verifies; VM AI / Azure Function deploy only if explicitly authorized)

- [x] 6.1 Verify a missed poll cycle does not lose events: simulate a gap, confirm the next successful poll's query starts from the persisted checkpoint and retrieves the gap's telemetry.
- [x] 6.2 Verify a burst above one page is fully retrieved within a single invocation up to the max-page bound, and that any remainder is picked up on the next poll without loss.
- [x] 6.3 Verify a transient query/forward failure is retried and only counted as failed after exhausting retries; verify the checkpoint does not advance past a failed page.
- [x] 6.4 Verify 401/403 `AppRequests` classify as `unauthorized_access` identically on the Function and backend sides.
- [x] 6.5 Verify `AppDependencies`/`AppAvailabilityResults` failures are ingested and successes are not; verify the `AppTraces` demo query no longer runs.
- [x] 6.6 Verify `app_insights_unauthorized_access_threshold` fires only for `azure_insights` source and never above High.
- [x] 6.7 Verify `azure_auth_abuse_exception_correlation` fires only when both corroborating signals are open, links to an existing `successful_login_after_spray` incident without creating a duplicate approval/containment cycle, and never exceeds High.
- [x] 6.8 Verify Source Health surfaces poll failure vs. no-new-telemetry correctly for `azure_insights`.
- [x] 6.9 Verify no new frontend files were touched.
- [x] 6.10 Run the full affected backend test suite for all modules touched in Phases 1–5.
- [x] 6.11 Run schema/migration validation for the new `ingestion_checkpoints` migration.
- [x] 6.12 Run `openspec validate application-insights-ingestion-and-high-signal-detections --strict`.
- [x] 6.13 Run `git diff --check`.
- [x] 6.14 Prepare the VM handoff document per `docs/mac-vm-source-of-truth-policy.md` §Completion Evidence for the backend/migration portion, and separately note the Azure Function redeploy (app settings, `function_app.py`) as an Azure-side deployment outside the Mac/VM boundary, requiring its own explicit authorization — do not execute any VM or Azure deployment step without it.
