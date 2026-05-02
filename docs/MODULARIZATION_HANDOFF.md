# Modularization Handoff

Last updated: 2026-05-02 (detection/correlation complete; route contract coverage in place; blocklist + reporting Blueprints registered; `create_app()` still blocked)

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
  - `backend_blocklist_routes.py` (Flask Blueprint: `blocklist_bp`)
  - `backend_reporting_routes.py` (Flask Blueprint: `reporting_bp`)
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

**Backend helper extraction is complete. Detection/correlation extraction is complete. Route architecture is no longer “all or nothing”: incremental Blueprint extraction is in progress on the existing module-level `app`; `create_app()` remains intentionally blocked.**

All frontend work is done. All backend helper clusters that could be safely extracted have been extracted. Detection and correlation engines were moved only after PostgreSQL-backed behavioral coverage existed. `siem_backend.py` is ~1,795 lines (down from ~5,183 at start of modularization; line count drops further as additional route modules are split out). The remaining weight is mostly Flask app initialization, routes not yet moved to Blueprints, auth/session/RBAC, and the ingest orchestration hub.

### Current architecture snapshot (concise)

- **Detection/correlation:** implemented in `backend_detection_engine.py` and `backend_correlation_engine.py`; PostgreSQL-backed tests protect behavior and shared-cursor assumptions.
- **Ingest orchestration:** `ingest_normalized_event` remains **centralized in `siem_backend.py`** (intentional hub; do not relocate without a dedicated plan).
- **Blueprints registered** (no `url_prefix`; URLs unchanged): `blocklist_bp` from `backend_blocklist_routes.py`; `reporting_bp` from `backend_reporting_routes.py` — both registered via `app.register_blueprint(...)` in `siem_backend.py` after Flask-Login setup.
- **Still implemented as routes on the core app module** (non-exhaustive): auth/session, admin, ingest endpoints, alert list and alert mutation/execute, health, events search, reputation backfill, frontend static shell.
- **Contract tests** exist for ingest, alerts, events search, reporting/export, alert mutation, admin (subset), and blocklist — see `tests/test_*api_contracts.py` (plus `tests/test_auth_rbac.py` for session/RBAC smoke).

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
- Backend DB connection factory and blocklist helpers extracted (`backend_db.py`). Phase 4 Step 1.
- Backend IP geolocation, reputation, and response action cluster extracted (`backend_ip_helpers.py`). Phase 4 Step 2.
- Backend detection rule config constants and helpers extracted (`backend_detection_config.py`). Phase 5.
- Backend correlation engines extracted (`backend_correlation_engine.py`).
- Backend detection cores extracted (`backend_detection_engine.py`).

What distinguished the later backend phases from earlier phases:

- Phases 1–3 were **pure lifts**: function bodies unchanged, no imports in new files.
- Phases 4–5 required **controlled body changes**: `app.logger` → `current_app.logger` in affected functions; `env_first(...)` → `os.getenv(...)` in `get_db_connection`. These were minimal but deliberate.
- Phase 4 also required moving **mutable module-level state** (`geo_cache`, `REPUTATION_CACHE`) — not possible with pure lifting.
- Detection/correlation movement was **test-gated**: PostgreSQL-backed tests were added first, then functions moved while preserving the existing conn/cur ownership and shared-cursor behavior.

Current stop point: continue **small, test-backed** route/Blueprint steps only. Route/API contract coverage for the groups listed above is in place; further Blueprint moves require the same discipline (surgical diff, no behavior drift, watch limiter/auth/import boundaries). Do **not** introduce `create_app()` or relocate `ingest_normalized_event` without an explicit reviewed plan.

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

`siem_backend.py` imports these helpers and still owns:

- `env_first`, `env_csv` — runtime env helpers (used by Flask app setup itself, cannot move).
- Flask app setup, CORS, rate limiter, session config.
- Auth/session routes and Flask-Login initialization.
- Admin routes (user management, audit log, detection rule admin).
- `ingest_normalized_event` fan-out and transaction orchestration.
- Ingestion routes (custom event, web log, Azure, OTel).
- Alert/event routes (list, search, mutation, execute, reputation backfill, etc.).
- Registration of `blocklist_bp` and `reporting_bp` (route implementations live in `backend_blocklist_routes.py` and `backend_reporting_routes.py`).
- `backfill_alert_sources` — dead code, no callers, not needed.
- Frontend serving.

`siem_backend.py` line count: ~1,795 (down from ~5,183 at start of modularization).

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
- Do NOT start random modularization. Helper extraction is complete. Detection/correlation extraction is complete.
- **Blueprint extraction is incremental and surgical:** register Blueprints on the existing module-level `app` with `app.register_blueprint(...)`; preserve URL paths, decorators, SQL, response shapes, and conn/cur ownership. **Do not** add `url_prefix` unless explicitly planned (current Blueprints define full paths on the blueprint).
- **Contract tests first:** new route groups should mirror the existing `tests/test_*api_contracts.py` pattern; patch `get_db_connection` in the **route module namespace** when tests use isolated PostgreSQL schemas (see blocklist/reporting tests).
- Do NOT move `ingest_normalized_event`. It remains the orchestration hub and owns the shared transaction/cursor fan-out. **Ingest HTTP routes** stay in `siem_backend.py` for now (API-key guards, limiter, and tight coupling to the hub).
- Do NOT introduce `create_app()` yet. App initialization remains module-level.
- **Auth/session routes** stay in `siem_backend.py` for now (module-level `admin_username` / `admin_password`, `login_manager`, and Flask-Login wiring).
- **Limiter / imports:** several **admin** and **alert-mutation** routes use `@limiter.limit(...)`. Extracting those groups risks **circular imports** (`limiter` ↔ route module ↔ `siem_backend`). Do not move them until a deliberate pattern is chosen (e.g. defer applying decorators, a tiny extensions module, or limit registration order documented and tested).
- Do NOT change conn/cur ownership. The shared-cursor transaction behavior is intentional and now test-protected.
- Do NOT create new DB connections inside detection, correlation, or ingest orchestration.
- Stop if imports become circular or confusing.
- Stop if a route move requires changing request/response shapes, auth semantics, session behavior, or transaction boundaries.

## 6. Current Safe Modularization Direction

**Backend helper extraction: done.** All extractable helper clusters have been moved.

**Backend detection/correlation extraction: done.** All 7 detection cores are in `backend_detection_engine.py`. Both correlation engines are in `backend_correlation_engine.py`. `ingest_normalized_event` remains in `siem_backend.py` as the orchestration hub.

**Frontend: done.** All panels and `App.js` delegate HTTP calls to focused service modules. All utility helpers are extracted. Components still own all state, handlers, loading flags, feedback, and UI orchestration.

**Frontend hooks: still on hold.** Moving hooks too early would mix API ownership, loading/error state, and behavior orchestration before service boundaries have been fully verified. Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

`AlertsTable.js` extraction remains paused. The remaining complexity is not presentation — it combines selected alert behavior, notes/actions, response logs, grouped/collapsed table state, exports/report links, hover/selection UI, and many display styles. Wait for a specific, clearly bounded target.

**Backend next step: incremental Blueprint planning + dependency untangling — not broad refactors.**

Reporting and blocklist Blueprint extractions are complete. Before the next Blueprint:

1. **Plan** the next route group with explicit notes on **limiter** binding and **auth/session** imports (avoid circular imports with `siem_backend`).
2. **Optionally harden tests** where gaps remain (e.g. admin **write** routes, `POST /alerts/<id>/execute`) so the next extraction stays test-gated.
3. **`create_app()`** remains **planning-only** until factory-relevant behavior (session cookies, limiter attachment, login manager order) is enumerated and optionally covered.

Do not begin `create_app()` implementation without a reviewed plan. Do not move `ingest_normalized_event` or ingest routes without a dedicated orchestration/import strategy.

## 7. Remaining High-Risk Areas

Frontend — permanently blocked until explicitly re-evaluated:

- `AlertsTable.js` behavior coupling (notes, response actions, response logs, grouped/collapsed table, exports, hover/selection).
- Alert polling in `App.js`.
- Auth/session state in `App.js`.
- Broad custom hooks.

Backend — extracted and now test-protected:

- Detection engine (7 `_generate_*_core` functions, ~1,072 lines in `backend_detection_engine.py`). These write alerts, suppress duplicates, and trigger response actions. PostgreSQL-backed behavioral tests exist for all 7 cores.
- Correlation engine (`generate_correlated_activity_alerts`, `generate_targeted_correlation_alerts`, ~387 lines in `backend_correlation_engine.py`). PostgreSQL-backed behavioral tests exist for generic and targeted correlation.
- `ingest_normalized_event` — orchestration fan-out hub. All 7 detection cores and both correlation engines are called from here. It remains intentionally centralized in `siem_backend.py`; rollback, ordering, and shared-cursor behavior are now test-protected.

Backend — incremental Blueprint / factory blockers:

- **Further route Blueprints** — contract coverage exists for the major groups listed in §2; each **next** extraction still needs a short plan (rollback, limiter/auth import graph, test patch targets for `get_db_connection` in the new module).
- **`create_app()`** — app initialization remains module-level. Do not introduce an app factory until route/auth/session and extension attachment behavior are explicitly accounted for.
- **Ingest routes + hub** — blocked from Blueprint moves by intentional `ingest_normalized_event` centralization and ingest-specific wiring (API keys, rate limits, orchestration).
- **Auth/session routes** — blocked from casual moves by module-level env bootstrap and Flask-Login initialization coupling to `siem_backend.py`.

Backend — Flask-session bound:

- Login/logout/session routes and Flask-Login app setup remain in `siem_backend.py`. Auth/RBAC helpers are already extracted to `backend_auth.py`, but broader route movement remains session-critical.

Backend — dead code (ignore):

- `backfill_alert_sources` — maintenance utility, no callers in `siem_backend.py`. Not needed by any module.

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
- `ingest_normalized_event` remains in `siem_backend.py`.
- Conn/cur ownership did not change.
- No new DB connections were introduced.
- At Phase 7 closeout, no Blueprints or `create_app()` existed yet; **Phase 9** later added `blocklist_bp` and `reporting_bp` (see §2 and Phase 9).

Phase 8 — COMPLETE (for the current contract scope): Route contract and API response-shape testing.

- Contract-level tests exist for: ingest, alerts list, events search, reporting/export, alert mutation (notes/status/response-log), admin (subset), blocklist.
- Tests live primarily under `tests/test_*api_contracts.py` with PostgreSQL fixtures where needed; patch `get_db_connection` in **both** `siem_backend` and the **route module** (`backend_blocklist_routes`, `backend_reporting_routes`, etc.) when isolating DB state.

Phase 9 — IN PROGRESS: Backend route grouping via Flask Blueprints (incremental).

- **Done:** `backend_blocklist_routes.py` / `blocklist_bp`; `backend_reporting_routes.py` / `reporting_bp` — registered in `siem_backend.py` after Flask-Login setup, no `url_prefix`, behavior-preserving moves.
- **Next:** plan the following groups carefully — **admin** and **alert mutation** routes often use `@limiter.limit` (circular-import risk with `limiter`); **auth/session** routes are tied to module-level env and `login_manager`; **ingest** routes tied to `ingest_normalized_event`.
- Do not introduce `create_app()` until app initialization and session behavior are explicitly covered or documented for a factory.

Phase 10 — FUTURE: Frontend hooks (low-complexity domain only).

- Only after route grouping plan is stable and the backend is not actively changing.
- Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

## 9. Verification Checklist

**Current baseline (post detection/correlation extraction):**

```bash
python3 -m py_compile siem_backend.py backend_blocklist_routes.py backend_reporting_routes.py backend_detection_engine.py backend_correlation_engine.py backend_detection_config.py backend_db.py backend_ip_helpers.py backend_audit_helpers.py backend_auth.py backend_api_guards.py backend_reporting_helpers.py backend_enrichment_helpers.py backend_pdf_helpers.py backend_query_helpers.py backend_ingest_normalizers.py
```

Focused PostgreSQL-backed behavioral test baseline:

```bash
python3 -m pytest tests/test_auth_rbac.py tests/test_failed_login_detection.py tests/test_port_scan_detection.py tests/test_password_spraying_detection.py tests/test_successful_login_after_spray_detection.py tests/test_http_error_detection.py tests/test_application_exception_detection.py tests/test_high_request_rate_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_normalized_event.py -v -rs
```

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

**Do NOT move** `backfill_alert_sources` — it is a maintenance utility with no callers in `siem_backend.py`.

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
> Do NOT move `backfill_alert_sources`.
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

- `ingest_normalized_event` remains the orchestration hub inside `siem_backend.py`.
- Detection cores live in `backend_detection_engine.py`.
- Correlation engines live in `backend_correlation_engine.py`.
- App initialization remains module-level in `siem_backend.py`.
- **Flask Blueprints:** `blocklist_bp` and `reporting_bp` are registered on the same `app` object (no `create_app()` factory).
- No `create_app()` factory exists.
- Conn/cur ownership remains shared and centralized; detection and correlation functions receive the caller's cursor and connection.
- Shared-cursor transaction behavior remains critical and test-protected.

**Current stop point:** `siem_backend.py` is ~1,795 lines. Helper extraction and detection/correlation extraction are complete. **Route contract tests** cover the main public API groups; **two Blueprints** (blocklist, reporting) are live. Next work is **incremental** Blueprint/import planning (watch **limiter** and **auth/session** coupling), optional **test gap fill** (admin writes, alert execute), and eventual **`create_app()`** planning only when warranted — not random modularization.
