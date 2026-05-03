# Modularization Handoff

Last updated: 2026-05-02 (backend modularization effectively complete; `create_app()` in place; route groups extracted to Blueprints; full pytest suite passing)

This document is the starting point for future sessions working on modularization. It summarizes the current project shape, what has already been extracted safely, what boundaries are still risky, and how to continue without drifting into broad refactors.

## 1. Project Overview

The project is a SIEM security dashboard with a Flask backend and a React frontend.

Backend:

- Main backend entrypoint: `siem_backend.py`
- Supporting backend modules:
  - `backend_db.py`
  - `backend_ip_helpers.py`
  - `backend_detection_config.py`
  - `backend_detection_engine.py`
  - `backend_correlation_engine.py`
  - `backend_audit_helpers.py`
  - `backend_auth.py`
  - `backend_api_guards.py`
  - `backend_extensions.py`
  - `backend_ingest_engine.py`
  - `backend_auth_routes.py` (Flask Blueprint: `auth_bp`)
  - `backend_blocklist_routes.py` (Flask Blueprint: `blocklist_bp`)
  - `backend_reporting_routes.py` (Flask Blueprint: `reporting_bp`)
  - `backend_admin_routes.py` (Flask Blueprint: `admin_bp`)
  - `backend_alerts_events_routes.py` (Flask Blueprint: `alerts_events_bp`)
  - `backend_alert_mutation_routes.py` (Flask Blueprint: `alert_mutation_bp`)
  - `backend_ingest_routes.py` (Flask Blueprint: `ingest_bp`)
  - `backend_reporting_helpers.py`
  - `backend_enrichment_helpers.py`
  - `backend_pdf_helpers.py`
  - `backend_query_helpers.py`
  - `backend_ingest_normalizers.py`
  - `adapters/azure_insights_adapter.py`
  - `adapters/nginx_adapter.py`
  - `adapters/otel_adapter.py`
- Supporting scripts:
  - `scripts/ingest_log_files.py`

Frontend:

- Main application shell: `frontend/src/App.js`
- Major frontend components:
  - `frontend/src/components/AlertsTable.js`
  - `frontend/src/components/ThreatHuntPanel.js`
  - `frontend/src/components/AdminUsersPanel.js`
  - `frontend/src/components/AuditLogPanel.js`
  - `frontend/src/components/DetectionRulesPanel.js`
  - `frontend/src/components/BlocklistManagerPanel.js`
- Shared frontend utilities:
  - `frontend/src/utils/`
- Focused frontend service modules:
  - `frontend/src/services/`

Current stack:

- Backend: Flask, Flask-Login/session auth, PostgreSQL access through `psycopg2`, ReportLab PDF generation, local ingestion adapters.
- Frontend: React, `react-scripts`, Recharts, `react-simple-maps`, browser `fetch`, session storage, component-local state.

## 2. Current Modularization Phase

**Backend modularization is effectively complete. Helper extraction, detection/correlation extraction, shared extension extraction, `create_app()` Phase 1, ingest engine extraction, and all major API route Blueprint extractions are complete.**

All frontend work is done. All backend helper clusters that could be safely extracted have been extracted. Detection and correlation engines were moved only after PostgreSQL-backed behavioral coverage existed. `siem_backend.py` is now the app shell: environment helpers, startup constants, `create_app()`, extension setup, Blueprint registration, module-level `app = create_app()` compatibility, `GET /health`, frontend catch-all serving, and the `__main__` run block.

### Current architecture snapshot (concise)

- **Detection/correlation:** implemented in `backend_detection_engine.py` and `backend_correlation_engine.py`; PostgreSQL-backed tests protect behavior and shared-cursor assumptions.
- **Ingest orchestration:** `ingest_normalized_event` lives in `backend_ingest_engine.py`; `siem_backend.py` imports/re-exports it for compatibility.
- **Blueprints registered** (no `url_prefix`; URLs unchanged): `auth_bp`, `blocklist_bp`, `reporting_bp`, `admin_bp`, `alerts_events_bp`, `alert_mutation_bp`, and `ingest_bp`, all registered inside `create_app()`.
- **Still implemented directly on the app shell:** `GET /health` and frontend catch-all routes only.
- **Contract tests** exist for ingest, auth/RBAC, alerts, events search, reporting/export, alert mutation, admin, backfill reputation, and blocklist. Full pytest sweep passes.

Completed safely through the current phase:

- All frontend presentation components extracted.
- All frontend utility helpers extracted (no state, no side effects).
- All major frontend service modules introduced (see Section 3).
- Backend reporting/enrichment helpers extracted (pure formatting, no Flask deps).
- Backend PDF rendering helpers extracted (`backend_pdf_helpers.py`).
- Backend SQL/query helpers extracted (`backend_query_helpers.py`).
- Backend ingest app-name normalizers extracted (`backend_ingest_normalizers.py`).
- Backend audit helpers extracted (`backend_audit_helpers.py`).
- Backend auth/RBAC helpers extracted (`backend_auth.py`).
- Backend API guard helpers extracted (`backend_api_guards.py`).
- Shared Flask-Limiter object extracted (`backend_extensions.py`).
- Backend DB connection factory and blocklist helpers extracted (`backend_db.py`). Phase 4 Step 1.
- Backend IP geolocation, reputation, and response action cluster extracted (`backend_ip_helpers.py`). Phase 4 Step 2.
- Backend detection rule config constants and helpers extracted (`backend_detection_config.py`). Phase 5.
- Backend correlation engines extracted (`backend_correlation_engine.py`).
- Backend detection cores extracted (`backend_detection_engine.py`).
- Ingest orchestration extracted (`backend_ingest_engine.py`).
- Major backend API route groups extracted to Blueprints.

What distinguished the later backend phases from earlier phases:

- Phases 1–3 were **pure lifts**: function bodies unchanged, no imports in new files.
- Phases 4–5 required **controlled body changes**: `app.logger` → `current_app.logger` in affected functions; `env_first(...)` → `os.getenv(...)` in `get_db_connection`. These were minimal but deliberate.
- Phase 4 also required moving **mutable module-level state** (`geo_cache`, `REPUTATION_CACHE`) — not possible with pure lifting.
- Detection/correlation movement was **test-gated**: PostgreSQL-backed tests were added first, then functions moved while preserving the existing conn/cur ownership and shared-cursor behavior.

Current stop point: backend modularization should stop here. Further movement would mostly be churn unless it targets a concrete bug or deployment need. Keep `GET /health`, frontend catch-all routes, and module-level `app = create_app()` in `siem_backend.py`.

## 3. Frontend Completed Work

Presentation component extractions:

- `frontend/src/components/AlertTimeline.js`
- `frontend/src/components/AlertsToolbar.js`
- `frontend/src/components/AlertDetailsPanel.js`
- `frontend/src/components/AlertResponseIndicator.js`
- `frontend/src/components/ThreatHuntEventDetails.js`
- `frontend/src/components/AdminStatusBadge.js`
- `frontend/src/components/DashboardMetrics.js`
- `frontend/src/components/DashboardVisuals.js`
- `frontend/src/components/DashboardSection.js`

Utility extractions:

- `frontend/src/utils/siemPath.js`
  - Shared SIEM base path and path builder.
- `frontend/src/utils/sessionIdentity.js`
  - Session identity storage key and read/write helpers.
- `frontend/src/utils/alertDashboardData.js`
  - Pure dashboard derived-data helpers for filtering, sorting, metrics, top IP chart data, and timeline data.
- `frontend/src/utils/threatHuntDisplay.js`
  - Pure threat hunt formatting, badge, payload, and date grouping helpers.
- `frontend/src/utils/alertDisplay.js`
  - Pure alert display helpers for source/reputation metadata, correlation display, and selected-alert timeline construction.
- `frontend/src/utils/apiResponse.js`
  - Shared JSON parsing and API error-message helpers.
- `frontend/src/utils/adminPanelDisplay.js`
  - `formatAdminTimestamp(value, fallback)` — shared UTC timestamp formatter used by AuditLogPanel, BlocklistManagerPanel, and DetectionRulesPanel. Each caller passes its own fallback to preserve existing null-handling behavior.

Service extractions:

- `frontend/src/services/adminUsersService.js`
  - `loadAdminUsers`
  - `createAdminUser`
  - `updateAdminUserStatus`
  - `resetAdminUserPassword`
  - `updateAdminUserRole`
  - `AdminUsersPanel.js` still owns state, handlers, feedback, loading flags, and UI orchestration.
- `frontend/src/services/threatHuntService.js`
  - `searchThreatHuntEvents`
  - `ThreatHuntPanel.js` still owns search/filter state, expanded event state, copy/pivot handlers, loading, and errors.
- `frontend/src/services/authService.js`
  - `loadCurrentSession`
  - `loginToDashboard`
  - `logoutFromDashboard`
  - `App.js` still owns auth/session state, session-change detection, login/logout orchestration, and session identity storage.
- `frontend/src/services/alertsService.js`
  - `loadAlerts`
  - `App.js` still owns the alert list state, polling interval, and error handling.
- `frontend/src/services/alertStatusService.js`
  - `updateAlertStatusRequest`
  - `App.js` still owns the status update handler and optimistic alert list update.
- `frontend/src/services/alertResponseService.js`
  - `loadAlertResponseLog`
  - `AlertsTable.js` still owns response log state, loading flag, and display.
- `frontend/src/services/auditLogService.js`
  - `loadAuditLogEvents`
  - `AuditLogPanel.js` still owns event list state, loading, and error handling.
- `frontend/src/services/blocklistService.js`
  - `loadBlocklistEntries`
  - `addBlocklistEntry`
  - `unblockBlocklistEntry`
  - `BlocklistManagerPanel.js` still owns entry state, form state, feedback, loading, and submitting flags.
- `frontend/src/services/detectionRulesService.js`
  - `loadDetectionRules`
  - `updateDetectionRule`
  - `DetectionRulesPanel.js` still owns rules state, editing state, draft parameters, save feedback, and loading flags.

Important frontend state ownership that has not moved:

- `App.js` still owns auth/session state, alert polling, active section, alert list, dashboard filters, and derived-data `useMemo` ownership.
- `AlertsTable.js` still owns selected alert behavior, notes, response logs, response actions, grouped/collapsed state, hover state, exports, and table rendering.
- `ThreatHuntPanel.js` still owns threat hunt orchestration.
- `AdminUsersPanel.js` still owns admin user UI orchestration.
- `BlocklistManagerPanel.js` still owns blocklist UI orchestration and form state.
- `DetectionRulesPanel.js` still owns detection rules UI orchestration and editing state.
- `AuditLogPanel.js` still owns audit log UI orchestration.

## 4. Backend Completed Work

`backend_db.py` currently owns DB connection factory and blocklist record helpers:

- `get_db_connection` — psycopg2 connection factory; `env_first(...)` replaced with `os.getenv(...)` for four env pairs
- `validate_blocked_ip` — IP address validation and normalization
- `create_blocked_ip_record` — blocklist INSERT with alert source validation
- No Flask deps. Imports: `os`, `psycopg2`, `ipaddress`.

`backend_ip_helpers.py` currently owns IP geolocation, reputation, and response action cluster:

- `_get_reputation_label`, `_build_reputation_summary` — pure label/summary formatters
- `get_ip_reputation` — SIEM-internal behavioral reputation lookup
- `lookup_ip_location` — ip-api.com geolocation with `geo_cache`
- `lookup_ip_reputation` — AbuseIPDB external lookup with `REPUTATION_CACHE`
- `determine_response_action` — reputation score → action mapping
- `execute_response_action` — response action executor (calls `create_blocked_ip_record` from `backend_db`)
- Module-level state: `geo_cache = {}`, `REPUTATION_CACHE = {}`, `ABUSEIPDB_API_KEY`
- Body changes applied: `app.logger` → `current_app.logger` in `lookup_ip_location` (1 site), `lookup_ip_reputation` (3 sites), `execute_response_action` (4 sites).

`backend_detection_config.py` currently owns detection rule configuration constants and helpers:

- 21 constants: all detection thresholds, window minutes, spray parameters, and validation bounds
- `get_detection_rule_defaults` — returns the default config dict for all 4 detection rules
- `parse_detection_rule_parameters` — JSON parsing and type validation for rule parameters
- `validate_detection_rule_config` — bounds checking for threshold and window values
- `get_effective_detection_rule` — merges DB override with defaults; reads from `detection_config` table
- `get_all_effective_detection_rules` — iterates all rule IDs through `get_effective_detection_rule`
- Body changes applied: `app.logger` → `current_app.logger` in `get_effective_detection_rule` (2 sites) and `get_all_effective_detection_rules` (1 site).
- Imports: `json`, `from flask import current_app`, `from backend_db import get_db_connection`.
- Note: detection constants are now consumed by `backend_detection_engine.py`; `CORRELATION_WINDOW_MINUTES` is consumed by `backend_correlation_engine.py`.

`backend_detection_engine.py` currently owns all 7 detection cores:

- `_generate_failed_login_alerts_core`
- `_generate_http_error_alerts_core`
- `_generate_port_scan_alerts_core`
- `_generate_password_spraying_alerts_core`
- `_generate_successful_login_after_spray_alerts_core`
- `_generate_application_exception_alerts_core`
- `_generate_high_request_rate_alerts_core`
- The functions still receive `cur` and `conn` from callers. No function creates its own DB connection.
- `get_effective_detection_rule` is still called with `cur=cur`.
- Current behavior intentionally preserved: username extraction, CTE behavior, temporal joins, duplicate suppression, `currval`, response action execution, reputation lookup, and location lookup.

`backend_correlation_engine.py` currently owns both correlation engines:

- `generate_correlated_activity_alerts`
- `generate_targeted_correlation_alerts`
- The functions still receive `cur` and `conn` from callers. No function creates its own DB connection.
- Current behavior intentionally preserved: shared-cursor reads of uncommitted prerequisite alerts, duplicate suppression, alert message format, `currval`, response action execution, and reputation lookup.

`backend_audit_helpers.py` currently owns audit logging:

- `log_audit_event`
- Function receives the active cursor from callers and does not own transaction boundaries.

`backend_auth.py` currently owns auth/RBAC helpers:

- `get_user_by_username`
- `User`
- `load_user`
- `deny_rbac_access`
- `admin_required`
- `super_admin_required`
- `analyst_or_super_admin_required`
- Flask-Login/session behavior remains route-driven in `siem_backend.py`; the helper module does not introduce an app factory.

`backend_api_guards.py` currently owns ingestion API guard helpers:

- `require_api_key`
- `require_azure_api_key`
- `require_otel_api_key`

`backend_extensions.py` currently owns shared Flask extension objects:

- `limiter` — initialized in `create_app()` with `limiter.init_app(app)`.
- Do not move `login_manager`, CORS, ProxyFix, app construction, or config into this module without a new plan.

`backend_ingest_engine.py` currently owns normalized ingest orchestration:

- `ingest_normalized_event`
- Receives `conn` and `cur` from route callers.
- Preserves detector-before-correlation ordering, shared-cursor behavior, rollback assumptions, and transaction ownership by the caller.

Route Blueprint modules currently own API route groups:

- `backend_auth_routes.py` / `auth_bp`: `POST /login`, `POST /logout`, `GET /auth/me`.
- `backend_blocklist_routes.py` / `blocklist_bp`: blocklist list/create/unblock routes.
- `backend_reporting_routes.py` / `reporting_bp`: alert reports, PDF reports, multi-alert reports, CSV export.
- `backend_admin_routes.py` / `admin_bp`: admin user routes, audit log, detection rule routes, `POST /alerts/backfill-reputation`.
- `backend_alerts_events_routes.py` / `alerts_events_bp`: `GET /alerts`, `GET /events/search`.
- `backend_alert_mutation_routes.py` / `alert_mutation_bp`: alert notes, status, execute, and response-log routes.
- `backend_ingest_routes.py` / `ingest_bp`: `POST /ingest`, `POST /ingest/web-log`, `POST /ingest/azure`, `POST /ingest/otlp`.

`backend_reporting_helpers.py` currently owns pure reporting helpers:

- `format_report_timestamp`
- `format_pdf_timestamp`
- `format_csv_timestamp`
- `format_display_value`
- `build_alert_summary`
- `build_severity_explanation`
- `build_confidence_level`
- `build_next_steps`
- `normalize_alert_report_data`
- `build_alert_report_sections`
- `build_report_header`

`backend_enrichment_helpers.py` currently owns MITRE enrichment:

- `MITRE_ATTACK_MAPPINGS`
- `enrich_alert_with_mitre`
- `enrich_alert_with_correlation_context`

`backend_pdf_helpers.py` currently owns PDF rendering (13 functions):

- `get_pdf_severity_palette`, `start_pdf_page`, `ensure_pdf_space`, `draw_pdf_wrapped_text`
- `draw_pdf_section_heading`, `draw_pdf_key_value_rows`, `draw_pdf_severity_badge`
- `draw_pdf_response_logs`, `draw_pdf_mitre_section`, `draw_pdf_next_steps`
- `draw_pdf_summary_grid`, `draw_pdf_alert_card`, `build_pdf_report_response`
- `build_pdf_report_response` is imported by `backend_reporting_routes.py` (report PDF responses).

`backend_query_helpers.py` currently owns filtered SQL helpers:

- `fetch_alert_rows` — filtered SELECT from alerts table
- `fetch_response_logs_by_alert_id` — SELECT from response_actions_log, returns dict keyed by alert_id
- `fetch_alert_csv_rows` — filtered SELECT with LEFT JOIN LATERAL for CSV export
- No imports — functions receive psycopg2 cursor as parameter.

`backend_ingest_normalizers.py` currently owns pure ingest app-name normalizers:

- `_safe_non_empty_string` — strips and validates a string value
- `_get_azure_app_name` — extracts cloud_RoleName from Azure telemetry dict
- `_is_azure_identity_payload` — detects SignInData/SignInLog baseType payloads
- `has_valid_location` — validates required location keys before ingest location lookup
- `_get_azure_identity_app_name` — extracts app name from Azure identity payload
- `_get_otel_app_name` — resolves app name from normalized OTel telemetry or payload
- No imports — pure Python, zero dependencies.

`siem_backend.py` is now the app shell and still owns:

- `env_first`, `env_csv` — runtime env helpers used by app setup and module-level startup constants.
- `DEFAULT_ALLOWED_ORIGINS`, `SIEM_ALLOWED_ORIGINS`, `SIEM_BIND_HOST`, `SIEM_PORT`, `SIEM_DEBUG`.
- `create_app()` — Flask construction, ProxyFix, limiter initialization, app config, CORS, LoginManager setup, unauthorized handler, 429 handler, user loader, and Blueprint registration.
- `app = create_app()` — required compatibility surface for tests, scripts, and deployment imports.
- `GET /health`.
- Frontend catch-all serving (`/` and `/<path:path>`), intentionally after API Blueprint registration.
- `if __name__ == "__main__"` run block.
- Compatibility import/re-export of `ingest_normalized_event`.

`siem_backend.py` should not regain route groups or domain logic unless a specific operational need is identified.

## 5. Current Architectural Rules

Keep these rules active until the roadmap is intentionally updated:

Frontend rules (unchanged):
- Keep state ownership in parent components.
- Avoid new custom hooks for now unless they are clearly safer than utilities/services.
- Avoid `GroupedAlertsTable` extraction for now.
- Do not move auth/session state yet.
- Do not move alert polling yet.
- Do not move frontend API ownership broadly.
- Prefer focused service modules before hooks.

Backend rules — Phases 3–5 (all complete, preserved for reference):
- Phase 3 was pure lifting only: no body changes, no imports in new files, no design decisions.
- Phases 4–5 allowed only: `app.logger` → `current_app.logger`, and `env_first(...)` → `os.getenv(...)` in `get_db_connection`. No other body changes.
- All extractions: one module per commit, verified before the next began.

Backend rules — current:
- Do NOT start new modularization by default. Helper extraction, detection/correlation extraction, ingest engine extraction, app factory Phase 1, and route Blueprint extraction are complete.
- Keep `siem_backend.py` as the app shell. `GET /health`, frontend catch-all serving, module-level `app = create_app()`, and the `__main__` run block should stay there.
- Keep Blueprint routes using full paths and no `url_prefix` unless a separately planned routing change is approved.
- Patch `get_db_connection` in the module namespace that imports it. For extracted routes, that means the route module, not `siem_backend.py`.
- Do NOT change conn/cur ownership. The shared-cursor transaction behavior is intentional and test-protected.
- Do NOT create new DB connections inside detection, correlation, or ingest orchestration.
- Stop if a change requires altering request/response shapes, auth semantics, session behavior, rate limiting, transaction boundaries, or frontend catch-all ordering.

## 6. Current Safe Modularization Direction

**Backend helper extraction: done.** All extractable helper clusters have been moved.

**Backend detection/correlation extraction: done.** All 7 detection cores are in `backend_detection_engine.py`. Both correlation engines are in `backend_correlation_engine.py`.

**Backend ingest orchestration extraction: done.** `ingest_normalized_event` is in `backend_ingest_engine.py` and is re-exported from `siem_backend.py` for compatibility.

**Frontend: done.** All panels and `App.js` delegate HTTP calls to focused service modules. All utility helpers are extracted. Components still own all state, handlers, loading flags, feedback, and UI orchestration.

**Frontend hooks: still on hold.** Moving hooks too early would mix API ownership, loading/error state, and behavior orchestration before service boundaries have been fully verified. Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

`AlertsTable.js` extraction remains paused. The remaining complexity is not presentation — it combines selected alert behavior, notes/actions, response logs, grouped/collapsed table state, exports/report links, hover/selection UI, and many display styles. Wait for a specific, clearly bounded target.

**Backend next step: stop modularization.**

The remaining backend work should be ordinary maintenance, documentation, or test hardening, not additional route movement. If a future change touches app setup, preserve extension initialization order, Blueprint registration order, frontend catch-all ordering, and module-level `app = create_app()` compatibility.

## 7. Remaining High-Risk Areas

Frontend — permanently blocked until explicitly re-evaluated:

- `AlertsTable.js` behavior coupling (notes, response actions, response logs, grouped/collapsed table, exports, hover/selection).
- Alert polling in `App.js`.
- Auth/session state in `App.js`.
- Broad custom hooks.

Backend — extracted and now test-protected:

- Detection engine (7 `_generate_*_core` functions, ~1,072 lines in `backend_detection_engine.py`). These write alerts, suppress duplicates, and trigger response actions. PostgreSQL-backed behavioral tests exist for all 7 cores.
- Correlation engine (`generate_correlated_activity_alerts`, `generate_targeted_correlation_alerts`, ~387 lines in `backend_correlation_engine.py`). PostgreSQL-backed behavioral tests exist for generic and targeted correlation.
- `ingest_normalized_event` — orchestration fan-out hub in `backend_ingest_engine.py`. All 7 detection cores and both correlation engines are called from here. Rollback, ordering, and shared-cursor behavior are test-protected.

Backend — remaining app-shell boundaries:

- **`GET /health`** — stays in `siem_backend.py` as platform/app-shell behavior.
- **Frontend catch-all** — stays in `siem_backend.py`; registration order after API Blueprints matters.
- **Module-level `app = create_app()`** — stays for compatibility with tests, scripts, and deployment imports.

Backend — no known modularization blockers remain. New architectural work should be justified by a concrete feature, bug, or deployment need.

## 8. Suggested Next Phases

Phase 1 — COMPLETE: Verify and stabilize current extractions.

Phase 2 — COMPLETE: Frontend service-boundary modularization.

- All major panels delegate HTTP calls to service modules.
- `App.js` delegates auth and alert-loading calls to service modules.
- State, handlers, loading flags, feedback, and orchestration remain in components.

Phase 3 — COMPLETE: Small pure backend utility extractions.

- `backend_pdf_helpers.py` — PDF rendering (13 functions, ~363 lines).
- `backend_query_helpers.py` — filtered SQL helpers (3 functions, ~114 lines).
- `backend_ingest_normalizers.py` — ingest app-name normalizers (5 functions, ~46 lines).
- All extractions were pure lifts: no body changes, no imports in new files.
- Pure utility extraction is now exhausted. Remaining functions require controlled body changes.

Phase 4 — COMPLETE: Backend DB foundation + IP/reputation cluster.

- Step 1: `backend_db.py` — `get_db_connection`, `validate_blocked_ip`, `create_blocked_ip_record`. Committed, VM smoke verified.
- Step 2: `backend_ip_helpers.py` — geo/reputation/response cluster (7 functions, 2 module-level caches). Committed, VM smoke verified.
- Controlled refactor phase: `app.logger` → `current_app.logger` (8 sites total), `env_first` → `os.getenv` in `get_db_connection`, mutable state moved.

Phase 5 — COMPLETE: Backend detection rule config extraction.

- `backend_detection_config.py` — 21 constants + 5 config/validation helpers. Committed, VM smoke verified.
- Controlled refactor: `app.logger` → `current_app.logger` in `get_effective_detection_rule` (2 sites) and `get_all_effective_detection_rules` (1 site).
- Detection constants now feed `backend_detection_engine.py`; `CORRELATION_WINDOW_MINUTES` feeds `backend_correlation_engine.py`.

Phase 6 — COMPLETE: Backend test infrastructure and behavioral coverage.

- Initial pytest infrastructure exists.
- PostgreSQL-backed test DB infrastructure exists.
- Auth/RBAC behavioral tests exist.
- Detection-core behavioral tests exist for all 7 detection cores.
- Generic correlation and targeted correlation behavioral tests exist.
- `ingest_normalized_event` orchestration tests exist.
- Shared-cursor rollback/orchestration behavior is now protected by tests.

Phase 7 — COMPLETE: Backend correlation and detection engine extraction.

- `backend_correlation_engine.py` owns `generate_correlated_activity_alerts` and `generate_targeted_correlation_alerts`.
- `backend_detection_engine.py` owns all 7 `_generate_*_core` detection functions.
- `ingest_normalized_event` later moved to `backend_ingest_engine.py` during Phase 9 closeout.
- Conn/cur ownership did not change.
- No new DB connections were introduced.
- At Phase 7 closeout, no Blueprints or `create_app()` existed yet; **Phase 9** later added `blocklist_bp` and `reporting_bp` (see §2 and Phase 9).

Phase 8 — COMPLETE: Route contract and API response-shape testing.

- Contract-level tests exist for: ingest, auth/RBAC, alerts list, events search, reporting/export, alert mutation, admin, backfill reputation, and blocklist.
- Tests live primarily under `tests/test_*api_contracts.py` with PostgreSQL fixtures where needed; patch `get_db_connection` in the module namespace that imports it.

Phase 9 — COMPLETE: Backend app shell, ingest engine, and route grouping.

- `backend_extensions.py` owns `limiter`.
- `create_app()` exists in `siem_backend.py`, with module-level `app = create_app()` preserved.
- `backend_ingest_engine.py` owns `ingest_normalized_event`.
- Blueprint route modules own auth, ingest, admin/backfill, alerts/events search, alert mutation, blocklist, and reporting/export routes.
- `siem_backend.py` owns only the app shell, health route, frontend catch-all, compatibility app object, and main run block.
- Final full test sweep passed: `116 passed, 2 warnings`.

Phase 10 — FUTURE: Frontend hooks or test fixture cleanup, only if specifically needed.

- Only after route grouping plan is stable and the backend is not actively changing.
- Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

## 9. Verification Checklist

**Current baseline (final modularized backend):**

```bash
python3 -m py_compile siem_backend.py backend_*.py
```

Full regression baseline:

```bash
python3 -m pytest -v -rs
```

Last verified result: `116 passed, 2 warnings`.

VM smoke tests verified after each phase:
- Phase 4 Step 1: login, blocklist add/remove, alert load.
- Phase 4 Step 2: alert load (reputation + geo fields present), `/alerts/backfill-reputation` (exercises `lookup_ip_reputation`).
- Phase 5: `GET /admin/detection-rules` (4 rules returned, `override_status` correct), `PATCH /admin/detection-rules/failed_login_threshold` (exercises `get_effective_detection_rule` + `current_app.logger` inside Flask app context).
- Detection/correlation extraction phase: focused PostgreSQL-backed pytest suites passed for detection cores, correlation engines, and `ingest_normalized_event`.

**Adapter compile check (run if adapters are touched):**

```bash
python3 -m py_compile adapters/azure_insights_adapter.py adapters/nginx_adapter.py adapters/otel_adapter.py scripts/ingest_log_files.py
```

Manual smoke-test areas (full regression):

- Login.
- Logout.
- `/auth/me` session restore.
- Alert loading.
- Dashboard metrics/charts/map.
- Alert filtering and sorting.
- Alert selection and details panel.
- Alert timeline.
- Alert notes.
- Response actions.
- Response logs.
- Alert report/export flows.
- Threat hunt search.
- Threat hunt expanded event details.
- Threat hunt copy/pivot actions.
- Admin user load.
- Admin role/status/password actions.
- Admin create-user flow.
- Audit log panel.
- Detection rules panel.
- Blocklist manager panel.

Known existing frontend build warnings to track separately (do not fix in modularization commits):

- `App.js` hook dependency warnings around `checkAuth` and `fetchAlerts`.
- `App.js` unused `subtitleStyle`.
- `AdminUsersPanel.js` duplicate `paddingTop` style key.

## 10. Git Workflow Rules

- Run `git status --short` before starting.
- Inspect relevant files before editing.
- Make one module/component extraction per commit.
- Do not mix unrelated frontend and backend changes in the same commit unless the task explicitly requires it.
- Run verification before committing.
- Inspect the generated diff before committing.
- Avoid giant mixed commits.
- Do not commit build artifacts.
- Do not revert user changes unless explicitly asked.
- If a change starts requiring state movement, route movement, or broad behavior changes, stop and re-plan.

## 11. Context-Window Guidance

Use this handoff at the start of a fresh session.

Recommended startup sequence:

1. Read `docs/MODULARIZATION_HANDOFF.md`.
2. Read `docs/modularization-dependency-map.md` only for deeper background.
3. Run `git status --short`.
4. Inspect only the files needed for the next task.
5. Execute one small modularization step.
6. Run verification.
7. Show the diff.

Refresh the session when:

- The conversation becomes very long.
- Multiple extractions have happened in one session.
- The next task touches a different subsystem.
- The model starts suggesting broad refactors instead of small bounded moves.
- The repo has just reached a clean commit checkpoint.

Fresh context matters here because the project is intentionally modularizing in small steps. Long sessions can lose the exact boundary rules, which increases the chance of drifting into risky hook extraction, route movement, or large component rewrites.

## 12. Phase 4 and Phase 5 Architecture Notes

**Phase 4 status: COMPLETE. Phase 5 status: COMPLETE. Later test-gated detection/correlation extraction is also COMPLETE.**

### Why Phase 4 Cannot Be Done as Pure Lifting

Three constraints block copy-and-paste extraction for the IP/reputation cluster:

1. **`app.logger` in function bodies.** `lookup_ip_location`, `lookup_ip_reputation`, and `execute_response_action` all call `app.logger.*` directly. The Flask `app` object cannot be imported from a helper module without a circular import. The accepted Flask solution is `current_app.logger` (from `flask import current_app`). This requires changing those specific call sites inside the function bodies — 1 site in `lookup_ip_location`, 3 sites in `lookup_ip_reputation`, 4 sites in `execute_response_action`.

2. **Mutable module-level caches.** `geo_cache = {}` (line 83 of `siem_backend.py`) and `REPUTATION_CACHE = {}` (line 1401) are populated entirely at runtime by the functions that own them. No other code reads or writes them directly. They must move with the owning functions into `backend_ip_helpers.py`. This is safe because the caches are empty at startup and populated lazily at runtime.

3. **Circular import from `get_db_connection`.** `get_ip_reputation` calls `get_db_connection()` when `cur=None`. If `get_ip_reputation` moves to `backend_ip_helpers.py` while `get_db_connection` stays in `siem_backend.py`, the new module would need `from siem_backend import get_db_connection` while `siem_backend.py` imports from `backend_ip_helpers.py`. Python will crash at startup with an `ImportError`. The fix is to extract `get_db_connection` first into `backend_db.py`, which neither file imports from the other.

### Phase 4 Step 1: Extract `backend_db.py`

**Functions to move:**

| Function | Approx lines | Notes |
|---|---|---|
| `get_db_connection()` | ~7 | One permitted body change: `env_first(...)` → `os.getenv(...) or os.getenv(...)` for each env pair |
| `validate_blocked_ip(ip_address)` | ~20 | Pure — move verbatim |
| `create_blocked_ip_record(cur, ...)` | ~50 | Cursor-passing pattern — move verbatim |

Historical note: `backfill_alert_sources` was later confirmed dead and cleaned up; it is no longer part of `siem_backend.py`.

**`backend_db.py` imports:** `import os`, `import psycopg2`, `import ipaddress`. No Flask deps.

**Why `env_first` → `os.getenv` is allowed:** `env_first` is defined in `siem_backend.py` and cannot be imported without a circular import. Its behavior for these four env pairs is exactly equivalent to `os.getenv("PRIMARY") or os.getenv("FALLBACK")` — env_first skips empty strings, and Python's `or` operator does the same for the empty string case.

**Blast radius:** `get_db_connection()` is called in 32 places in `siem_backend.py`. None of those call sites change — the name is imported into `siem_backend.py`'s namespace via `from backend_db import get_db_connection`. Similarly for `validate_blocked_ip` and `create_blocked_ip_record`.

**Call site audit for `create_blocked_ip_record` (historical Step 1 note):**
- Inside `execute_response_action` (now `backend_ip_helpers.py`) — no conflict
- Blocklist INSERT paths — **now** live in `backend_blocklist_routes.py` (still uses `create_blocked_ip_record` from `backend_db`)

**Risk: LOW-MEDIUM.** Wide blast radius (32 call sites) but zero call site changes. Primary verification is compile check + blocklist smoke test.

**Step 1 implementation prompt:**

> Read `docs/MODULARIZATION_HANDOFF.md` first.
>
> Safe backend helper extraction: DB connection factory and blocklist helpers.
>
> Repo: `/Users/jadengomez/Desktop/siem-security-dashboard-public`
>
> Create `backend_db.py` at the project root.
>
> Move ONLY these three functions from `siem_backend.py`:
> - `get_db_connection` — replace each `env_first("SIEM_X", "X")` call in the body with `os.getenv("SIEM_X") or os.getenv("X")` for the four env pairs (DB_NAME, DB_USER, DB_HOST, DB_PASSWORD). This is the only permitted body change.
> - `validate_blocked_ip` — move verbatim.
> - `create_blocked_ip_record` — move verbatim.
>
> Historical only: the original extraction prompt said not to move `backfill_alert_sources`; it was later removed as dead code.
>
> `backend_db.py` imports: `import os`, `import psycopg2`, `import ipaddress`. No other imports.
>
> In `siem_backend.py`: add `from backend_db import get_db_connection, validate_blocked_ip, create_blocked_ip_record` to the import block. Remove the three function bodies. Do not change any call sites.
>
> After: show diff summary. Run `python3 -m py_compile siem_backend.py backend_db.py`. Do NOT commit. Do NOT begin Step 2.

---

### Phase 4 Step 2: Extract `backend_ip_helpers.py`

**Prerequisite: Step 1 committed and verified.**

**Functions to move:**

| Function | Location | Body changes | Dependencies |
|---|---|---|---|
| `_get_reputation_label(score)` | line 465 | None | None |
| `_build_reputation_summary(signals)` | line 477 | None | None |
| `get_ip_reputation(source_ip, cur=None)` | line 489 | None | `get_db_connection` from `backend_db` |
| `lookup_ip_location(ip_address)` | line 1439 | `app.logger` → `current_app.logger` (1 site) | `geo_cache`, `requests` |
| `lookup_ip_reputation(ip_address)` | line 1934 | `app.logger` → `current_app.logger` (3 sites) | `REPUTATION_CACHE`, `ABUSEIPDB_API_KEY`, `requests` |
| `determine_response_action(reputation_score)` | line 2023 | None | None |
| `execute_response_action(cur, ...)` | line 2032 | `app.logger` → `current_app.logger` (4 sites) | `create_blocked_ip_record` from `backend_db` |

**`backend_ip_helpers.py` imports:**

```python
import os
import requests
from flask import current_app
from backend_db import create_blocked_ip_record, get_db_connection

geo_cache = {}
REPUTATION_CACHE = {}
ABUSEIPDB_API_KEY = os.getenv("SIEM_ABUSEIPDB_API_KEY") or os.getenv("ABUSEIPDB_API_KEY")
```

**State movement:**
- `geo_cache = {}` moves from `siem_backend.py` line 83. No other code references it directly.
- `REPUTATION_CACHE = {}` and `ABUSEIPDB_API_KEY` move from lines 1400–1401. No other code references them directly.

**`app.logger` → `current_app.logger` is safe here because:** all three affected functions are called exclusively from within route handlers or from functions called by route handlers. A Flask application context is always active at call time. `current_app` is the standard Flask pattern for helper modules that need access to the app context.

**Changes to `siem_backend.py`:**
- Remove `geo_cache = {}` (line 83).
- Remove `REPUTATION_CACHE = {}` and `ABUSEIPDB_API_KEY = env_first(...)` (lines 1400–1401).
- Remove all seven function bodies (~275 lines).
- Add one import block for `backend_ip_helpers`.
- All detection core and correlation engine call sites (`lookup_ip_reputation`, `determine_response_action`, `execute_response_action`) do not change — names remain in scope via import.

**Risk: MEDIUM.** Controlled body changes in 3 functions (8 total logger swap sites). Mutable global state movement. All call sites unchanged. Wider surface than Phase 3 extractions but well-bounded.

### Phase 4 Stop Boundary

- Phase 3: COMPLETE.
- Phase 4 Step 1 (`backend_db.py`): COMPLETE. Commit: `b5ddea3`.
- Phase 4 Step 2 (`backend_ip_helpers.py`): COMPLETE. Commit: `f6200b5`.
- Phase 5 (`backend_detection_config.py`): COMPLETE. VM smoke verified.

### Phase 5 Architecture Notes

**Why `backend_detection_config.py` followed the Phase 4 pattern:**

- `get_effective_detection_rule` and `get_all_effective_detection_rules` used `app.logger` directly (3 sites total). Same `current_app.logger` fix as Phase 4.
- 21 detection constants moved with the cluster. Detection constants are now consumed by `backend_detection_engine.py`; `CORRELATION_WINDOW_MINUTES` is consumed by `backend_correlation_engine.py`.
- `import json` was confirmed unused in `siem_backend.py` after the move (only user was `parse_detection_rule_parameters`) and was removed.

### Test-Gated Detection/Correlation Architecture Notes

**Why detection/correlation moved only after tests:**

- Detection cores and correlation engines write alerts, suppress duplicates, depend on real PostgreSQL `SERIAL`/`currval` behavior, and rely on shared transaction/cursor reads.
- PostgreSQL-backed behavioral tests were added first for all 7 detection cores, generic correlation, targeted correlation, and `ingest_normalized_event`.
- External reputation/network behavior is mocked in tests where needed. Real PostgreSQL transaction, cursor, duplicate suppression, and `currval` behavior remain covered.
- `execute_response_action` remains real unless a specific test needs a narrow failure injection.

**Preserved architecture decisions:**

- `ingest_normalized_event` is the orchestration hub in `backend_ingest_engine.py`; `siem_backend.py` re-exports it for compatibility.
- Detection cores live in `backend_detection_engine.py`.
- Correlation engines live in `backend_correlation_engine.py`.
- `create_app()` owns app setup in `siem_backend.py`, and module-level `app = create_app()` remains for compatibility.
- Flask Blueprints own all major API route groups and are registered from `create_app()` with no `url_prefix`.
- Conn/cur ownership remains shared and centralized; detection and correlation functions receive the caller's cursor and connection.
- Shared-cursor transaction behavior remains critical and test-protected.

**Current stop point:** backend modularization is effectively complete. `siem_backend.py` is the app shell plus health/frontend serving. Full verification passed with `python3 -m py_compile siem_backend.py backend_*.py` and `python3 -m pytest -v -rs` (`116 passed, 2 warnings`). Future work should be ordinary maintenance, focused test cleanup, or feature work, not additional route movement by default.
