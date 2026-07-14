## 1. Critical severity and correlation contract (Mac AI)

- [x] 1.1 In `engines/correlation_engine.py`, change the `web_to_app_attack_pattern` rule's `"severity"` from `"critical"` to `"high"`.
- [x] 1.2 In `engines/correlation_engine.py`, change the `spray_then_success_pattern` rule's `"severity"` from `"critical"` to `"high"`.
- [x] 1.3 Confirm `_generate_successful_login_after_spray_alerts_core` in `engines/detection_engine.py` is left unchanged (`severity = "critical"`); add/update an inline comment only if needed to record the rationale from `design.md` D2.
- [x] 1.4 Add `core/ip_helpers.floor_response_action_for_severity(response_action, severity)` that raises `"monitor"` to `"flag_high_priority"` when `severity == "critical"`, and returns the input unchanged otherwise (never returns `"block_ip"`).
- [x] 1.5 Apply the floor in `_generate_successful_login_after_spray_alerts_core` (`engines/detection_engine.py`) and in `generate_targeted_correlation_alerts` (`engines/correlation_engine.py`) before each `INSERT INTO alerts`.
- [x] 1.6 Write/update unit tests asserting: `web_to_app_attack_pattern` alerts insert with `severity = "high"`; `spray_then_success_pattern` alerts insert with `severity = "high"`; `successful_login_after_spray` alerts insert with `severity = "critical"`; a Critical alert with a low-reputation IP never inserts `response_action = "monitor"`; the floor never produces `response_action = "block_ip"`.
- [x] 1.7 Run focused tests: `tests/test_targeted_correlation.py`, and the `successful_login_after_spray`/`ip_helpers` test modules.

## 2. Incident upgrade behavior (Mac AI)

- [x] 2.1 Add `_maybe_upgrade_incident_severity(conn, incident, new_alert_severity, alert_id)` to `core/incident_store.py`, called from `maybe_create_or_link_incident`'s "existing incident found" branch, implementing the guarded `UPDATE incidents SET severity = 'CRITICAL', priority = 'P1' WHERE id = %s AND severity <> 'CRITICAL'` from `design.md` D4.
- [x] 2.2 On a successful upgrade (row actually updated), call `core.audit_helpers.log_audit_event(event_type="incident_severity_escalated", target_alert_id=alert_id, details={...})` with `incident_id`, `from_severity`, `to_severity`, `from_priority`, `to_priority`.
- [x] 2.3 Confirm `update_incident_status` and all other incident write paths are unchanged and contain no code path that lowers `severity` or `priority`.
- [x] 2.4 Write/update unit tests in `tests/test_incident_store.py`: Critical alert upgrades an existing High/P2 open incident to Critical/P1; Critical alert linking to an already-Critical incident is a no-op (no audit row, no redundant UPDATE); High alert linking to an existing Critical incident does not downgrade it; Critical alert with an existing open incident links rather than creating a duplicate incident.
- [x] 2.5 Write/update a route-level test in `tests/test_incident_routes.py` (or equivalent) confirming the audit trail is queryable after an escalation.
- [x] 2.6 Run focused tests: `tests/test_incident_store.py`, `tests/test_incident_routes.py`.

## 3. Immediate notification routing and playbook ordering (Mac AI)

- [x] 3.1 Add migration `migrations/00NN_notification_policy_critical_cross_source.sql` adding `critical_cross_source_destination TEXT NOT NULL DEFAULT 'Critical / Cross-Source Security destination' CHECK (btrim(critical_cross_source_destination) <> '')` to `notification_policy`, following the existing `pfsense_destination`/`honeypot_destination` pattern.
- [x] 3.2 Update `core/notification_policy_store.py` (load/effective-policy functions and any update/serialization functions) to read/write the new column.
- [x] 3.3 In `core/notification_policy_service.py`, add `ROUTE_KEY_CRITICAL_CROSS_SOURCE = "critical_cross_source"`; update `normalize_notification_source` (or its caller `evaluate_notification_policy`) so severity `critical` alerts/incidents from sources that are not pfSense/Honeypot resolve to this route key; add the corresponding `_policy_destination` branch; add a `critical_cross_source` case to `_route_test_source`/`_format_route_test_text` for the notification-policy route-test button.
- [x] 3.4 Confirm non-Critical alerts from unmapped sources still resolve `route_key = None` / `"source_not_routed"` (no behavior change for Low/Medium/High from unmapped sources).
- [x] 3.5 In `routes/ingest_routes.py`, remove the direct `_send_alert_notifications_for_alerts(...)` call from the ingest handlers that also call `_create_playbook_executions_for_alerts(...)` (which already sends notifications internally), so each alert's notification path is invoked exactly once per ingest request. Keep the generic `/ingest` handler's existing single-call pattern as the reference shape.
- [x] 3.6 In `core/core_playbook_pack_v1.py`, update `CORE_V1_WEB_TO_APP_ATTACK_INVESTIGATION_ID`'s `trigger_config.min_severity` from `"critical"` to `"high"`.
- [x] 3.7 In `core/core_playbook_pack_v1.py`, update `CORE_V1_SPRAY_THEN_SUCCESS_CORRELATION_INVESTIGATION_ID`'s `trigger_config.min_severity` to `"high"` and replace its steps with `[enrich_context, monitor, notify_slack]` (remove `flag_high_priority`, `require_approval`, `block_ip`).
- [x] 3.8 In `core/core_playbook_pack_v1.py`, update `CORE_V1_SPRAY_SUCCESS_RESPONSE_ID`'s trailing `notify_slack` step's `params.message` binding so its rendered text is a distinct containment-outcome message, not the same text as the immediate notification-policy alert message.
- [x] 3.9 Write a one-time idempotent reconciliation script (e.g. `scripts/reconcile_core_playbook_pack_v1.py`) that calls `update_playbook_definition` for any already-seeded `core_playbook_pack_v1` rows whose `trigger_config`/`steps` differ from the current source-of-truth pack, for use during VM handoff (Mac AI writes/tests it; VM AI runs it — see Phase 6).
- [ ] 3.10 Write/update unit tests: `evaluate_notification_policy` routes Critical `bank_app`/`nginx`/correlation alerts to `critical_cross_source` with the configured destination; non-Critical unmapped-source alerts remain unrouted; missing/blank `critical_cross_source_destination` fails safe (`should_notify = False`, no exception); `notify_for_alert` is invoked exactly once per alert across each ingest route (regression test for the double-send fix); `core-v1-web-to-app-attack-investigation` and `core-v1-spray-then-success-correlation-investigation` trigger against High-severity alerts and contain no `require_approval`/`block_ip` steps.
- [x] 3.11 Run focused tests: `tests/test_notification_policy_service.py`, `tests/test_notification_policy_store.py`, `tests/test_ingest_api_contracts.py`, `tests/test_core_playbook_pack_v1.py`, `tests/test_playbook_store.py`.
- [x] 3.12 Run schema/migration validation for the new migration per `docs/schema_migration_workflow.md`.

## 4. Duplicate-artifact prevention (Mac AI)

- [ ] 4.1 Write a regression test that simulates the full sequence — `password_spraying_threshold` alert, then `successful_login_after_spray` alert, then `spray_then_success_pattern` correlation alert, all for the same source IP within the correlation windows — and asserts: exactly one incident exists and it reaches Critical/P1; exactly one `require_approval` playbook execution reaches the `block_ip` step; the `spray_then_success_pattern` alert exists and links to the same incident but produced no second approval/containment cycle.
- [ ] 4.2 Write a regression test confirming `web_to_app_attack_pattern` alerts never create a second approval/containment cycle alongside any concurrently open Critical alert for the same IP (since it is High and investigation-only).
- [x] 4.3 Confirm the existing duplicate-open-alert guards in `generate_correlated_activity_alerts`/`generate_targeted_correlation_alerts` (skip when an open alert of the same `alert_type` already exists for the IP) are unaffected by the severity changes in Phase 1.
- [x] 4.4 Run focused tests: `tests/test_targeted_correlation.py`, `tests/test_soar_playbook_orchestrator.py`, `tests/test_playbook_not_actioned.py` (confirm unattended expiration still resolves `not_actioned` and fail-closed for the reduced `spray_then_success_pattern` playbook and the unchanged `successful_login_after_spray` playbook).

## 5. Read-only Severity & Response Matrix API and UI (Mac AI)

- [x] 5.1 Create `engines/severity_response_matrix.py` composing: the D1 severity definitions (static text, including the explicit Critical-philosophy wording — Critical is a likely-compromise signal, not confirmed compromise); per-rule default/maximum severity, a one-sentence `why` explanation, and analyst-facing metadata from `engines/detection_config.py` plus the corrected severities from Phase 1; live `playbook_definitions` rows (via `core/playbook_store`) for incident/notification/response-playbook-behavior columns; the effective `notification_policy` (via `get_effective_notification_policy`) for Slack eligibility/timing per severity/route.
- [x] 5.2 Add `GET /api/severity-response-matrix` in a route module (new or existing analyst-facing routes file), gated to `super_admin`/`analyst` roles using the existing RBAC helper pattern; read-only, no write methods.
- [x] 5.3 Ensure rules whose maximum severity is below Critical are explicitly labeled (not blank/omitted) in the API response, and every rule row includes a non-empty `why` field.
- [x] 5.4 Write backend tests: matrix API returns the four severity definitions and one row per active rule; `web_to_app_attack_pattern`/`spray_then_success_pattern` rows show `default_severity = "high"`; `successful_login_after_spray` shows `default_severity = "critical"`; a non-Critical-capable rule shows its true ceiling; every row's `why` field is present and non-empty; the Critical severity definition and the `successful_login_after_spray` `why` text do not state or imply "confirmed compromise"; unauthorized/unauthenticated requests are denied.
- [x] 5.5 Add `frontend/src/services/severityResponseMatrixService.js` calling the new endpoint.
- [x] 5.6 Add the read-only matrix component rendering severity definitions (definition, analyst expectation, incident behavior/priority, Slack eligibility/timing, approval requirement, containment behavior), a page-level "this page explains current behavior, it is not a configuration interface" statement, and the detection table (Detection, Default severity, Escalation conditions, Maximum severity, Creates incident, Notification behavior, Response/playbook behavior, Why), with links to the Notification Policy and Detection Rules (Runtime Configurables) sections. The `Why` column renders the API's `why` string verbatim — no frontend-authored explanation text.
- [x] 5.7 Register a new `severity-response-matrix` entry in `frontend/src/utils/sectionsConfig.js` (group `"soc"`, `visibleWhen: ({ canTakeAlertActions }) => canTakeAlertActions`) and wire it into `App.js`'s section rendering, following the existing `isSectionVisible` pattern.
- [x] 5.8 Add a link from `NotificationPolicyPanel.js` to the new workspace.
- [x] 5.9 Write/update frontend tests for the new service and component (loading, populated, error states; `Why` column renders the API value verbatim; page-level non-configuration statement is present; no editable controls present).
- [ ] 5.10 Run focused frontend tests, then `npm run build`; visually verify the workspace at desktop and narrow layout widths and check accessibility roles/labels/contrast against the project's existing dark-theme conventions.
- [x] 5.11 Light copy review of the per-rule `why` sentences (Open Question in `design.md`) to confirm each stays consistent with the Critical-philosophy wording (evidence/indicator language, not confirmed-compromise language) before VM handoff.

## 6. Verification and VM handoff (Mac AI verifies; VM AI deploys only if explicitly authorized)

- [x] 6.1 Verify each current Critical path's final severity end-to-end: `successful_login_after_spray` → critical; `web_to_app_attack_pattern` → high; `spray_then_success_pattern` → high.
- [x] 6.2 Verify `web_to_app_attack_pattern`'s downgraded behavior: alert is High, incident-eligible per existing High/Critical incident rules, investigation-only playbook (`enrich_context`, `monitor`, `notify_slack`), no `require_approval`/`block_ip`.
- [x] 6.3 Verify a Critical alert upgrades an existing High/P2 incident to Critical/P1, with an audit-log entry.
- [x] 6.4 Verify no incident downgrade occurs when a lower-severity alert links to an already-Critical incident.
- [ ] 6.5 Verify immediate notification occurs before any approval gate is reached for a Critical alert.
- [x] 6.6 Verify correct source webhook/channel routing: pfSense → pfSense destination, Honeypot → Honeypot destination, Critical `bank_app`/`nginx`/correlation → `critical_cross_source` destination, never through the pfSense or Honeypot webhook.
- [ ] 6.7 Verify no duplicate Critical Slack delivery: exactly one `notify_for_alert` invocation per alert across all ingest routes, and the legacy `core-v1-spray-success-response` outcome message differs from the immediate alert message.
- [x] 6.8 Verify a missing/blank `critical_cross_source_destination` fails safe (no exception, `should_notify = False`, ingest/incident/playbook processing unaffected).
- [x] 6.9 Verify unattended approval expiration remains `not_actioned` and fail-closed for both the retained `core-v1-spray-success-response` playbook and the reduced investigation-only playbooks.
- [x] 6.10 Verify no containment occurs without an approved `require_approval` step anywhere touched by this change.
- [ ] 6.11 Run the duplicate-correlation regression tests from Phase 4 and confirm they pass.
- [x] 6.12 Verify the Severity & Response Matrix API's accuracy against the corrected severities/playbooks and confirm RBAC denies non-analyst/non-super_admin access.
- [ ] 6.13 Verify the matrix UI renders correctly and accessibly at desktop and narrow layouts, including the `Why` column and the page-level non-configuration statement.
- [x] 6.14 Verify the Critical severity definition and every rule's `why` text avoid "confirmed compromise" language, consistent with the Critical-philosophy principle in `design.md` D1.
- [x] 6.15 Run the full affected backend test suite (all modules touched in Phases 1–5) and the full affected frontend test suite.
- [x] 6.16 Run `npm run build` for the frontend.
- [x] 6.17 Run schema/migration validation for the new `notification_policy` migration.
- [x] 6.18 Run `openspec validate critical-response-consistency-and-severity-matrix --strict`.
- [x] 6.19 Run `git diff --check`.
- [ ] 6.20 Prepare the VM handoff document per `docs/mac-vm-source-of-truth-policy.md` §Completion Evidence (requested/approved commit, migration plan, services to restart, reconciliation script run, smoke-test plan) — do not execute any VM step without explicit user authorization for commit, push, and deployment.
