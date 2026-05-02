# Modularization Handoff

Last updated: 2026-05-02 (Phase 5 complete; extraction surface exhausted; next step is planning only)

This document is the starting point for future sessions working on modularization. It summarizes the current project shape, what has already been extracted safely, what boundaries are still risky, and how to continue without drifting into broad refactors.

## 1. Project Overview

The project is a SIEM security dashboard with a Flask backend and a React frontend.

Backend:

- Main backend entrypoint: `siem_backend.py`
- Supporting backend modules:
  - `backend_db.py`
  - `backend_ip_helpers.py`
  - `backend_detection_config.py`
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

**Phase 5 is complete. The safe extraction surface is now exhausted. The next step is read-only planning only — no implementation.**

All frontend work is done. All backend helper clusters that could be safely extracted have been extracted. `siem_backend.py` is at ~4,018 lines (down from 5,183 at start of modularization). The remaining content is routes, detection/correlation engines, auth/RBAC, and orchestration — all blocked until a deliberate plan exists.

Completed safely through Phase 5:

- All frontend presentation components extracted.
- All frontend utility helpers extracted (no state, no side effects).
- All major frontend service modules introduced (see Section 3).
- Backend reporting/enrichment helpers extracted (pure formatting, no Flask deps).
- Backend PDF rendering helpers extracted (`backend_pdf_helpers.py`).
- Backend SQL/query helpers extracted (`backend_query_helpers.py`).
- Backend ingest app-name normalizers extracted (`backend_ingest_normalizers.py`).
- Backend DB connection factory and blocklist helpers extracted (`backend_db.py`). Phase 4 Step 1.
- Backend IP geolocation, reputation, and response action cluster extracted (`backend_ip_helpers.py`). Phase 4 Step 2.
- Backend detection rule config constants and helpers extracted (`backend_detection_config.py`). Phase 5.

What distinguished Phase 4 and Phase 5 from earlier phases:

- Phases 1–3 were **pure lifts**: function bodies unchanged, no imports in new files.
- Phases 4–5 required **controlled body changes**: `app.logger` → `current_app.logger` in affected functions; `env_first(...)` → `os.getenv(...)` in `get_db_connection`. These were minimal but deliberate.
- Phase 4 also required moving **mutable module-level state** (`geo_cache`, `REPUTATION_CACHE`) — not possible with pure lifting.

Current stop point: all remaining content in `siem_backend.py` requires either a test harness (detection/correlation), a blueprint architecture decision (routes), or is Flask-session-bound (auth/RBAC). None of these are extraction-ready under the current rules.

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
- Note: 7 constants (`HTTP_ERROR_THRESHOLD`, `HTTP_ERROR_WINDOW_MINUTES`, `APPLICATION_EXCEPTION_THRESHOLD`, `APPLICATION_EXCEPTION_WINDOW_MINUTES`, `HIGH_REQUEST_RATE_THRESHOLD`, `HIGH_REQUEST_RATE_WINDOW_MINUTES`, `CORRELATION_WINDOW_MINUTES`) are also used directly in detection core and correlation function bodies. They are re-imported into `siem_backend.py`'s namespace so those function bodies require no changes.

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

`backend_pdf_helpers.py` currently owns PDF rendering (13 functions):

- `get_pdf_severity_palette`, `start_pdf_page`, `ensure_pdf_space`, `draw_pdf_wrapped_text`
- `draw_pdf_section_heading`, `draw_pdf_key_value_rows`, `draw_pdf_severity_badge`
- `draw_pdf_response_logs`, `draw_pdf_mitre_section`, `draw_pdf_next_steps`
- `draw_pdf_summary_grid`, `draw_pdf_alert_card`, `build_pdf_report_response`
- Only `build_pdf_report_response` is imported by `siem_backend.py`.

`backend_query_helpers.py` currently owns filtered SQL helpers:

- `fetch_alert_rows` — filtered SELECT from alerts table
- `fetch_response_logs_by_alert_id` — SELECT from response_actions_log, returns dict keyed by alert_id
- `fetch_alert_csv_rows` — filtered SELECT with LEFT JOIN LATERAL for CSV export
- No imports — functions receive psycopg2 cursor as parameter.

`backend_ingest_normalizers.py` currently owns pure ingest app-name normalizers:

- `_safe_non_empty_string` — strips and validates a string value
- `_get_azure_app_name` — extracts cloud_RoleName from Azure telemetry dict
- `_is_azure_identity_payload` — detects SignInData/SignInLog baseType payloads
- `_get_azure_identity_app_name` — extracts app name from Azure identity payload
- `_get_otel_app_name` — resolves app name from normalized OTel telemetry or payload
- No imports — pure Python, zero dependencies.

`siem_backend.py` imports these helpers and still owns:

- `env_first`, `env_csv` — runtime env helpers (used by Flask app setup itself, cannot move).
- Flask app setup, CORS, rate limiter, session config.
- Auth/session/RBAC decorators and routes.
- Admin routes (user management, audit log, detection rule admin).
- Ingest API key guards, `has_valid_location`, `ingest_normalized_event` fan-out.
- Ingestion routes (custom event, web log, Azure, OTel).
- Detection functions (7 `_generate_*_core` functions — **BLOCKED**).
- Correlation functions (2 engines — **BLOCKED**).
- Alert/event routes.
- Reporting/export routes.
- Notes/actions/blocklist/status routes.
- `enrich_alert_with_correlation_context` — pure helper, single caller, low value to move.
- `backfill_alert_sources` — dead code, no callers, not needed.
- Frontend serving.

`siem_backend.py` line count: ~4,018 (down from 5,183 at start of modularization).

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

Backend rules — current (extraction surface exhausted):
- Do NOT start new helper extractions without a formal re-evaluation. The trivial remaining candidates (`enrich_alert_with_correlation_context`, `has_valid_location`) are not worth a commit on their own.
- Do NOT move backend routes. Route grouping requires a Blueprint architecture decision first — planning only, no implementation.
- Do NOT move detection cores, correlation engines, or `ingest_normalized_event`. These require a behavioral test harness before any movement.
- Do NOT move auth/RBAC helpers — Flask-Login session bound, no safe extraction pattern exists yet.
- Stop if any work requires touching detection or correlation function bodies.
- Stop if imports become circular or confusing.

## 6. Current Safe Modularization Direction

**Backend helper extraction: done.** All extractable helper clusters have been moved. The safe extraction surface is exhausted.

**Frontend: done.** All panels and `App.js` delegate HTTP calls to focused service modules. All utility helpers are extracted. Components still own all state, handlers, loading flags, feedback, and UI orchestration.

**Frontend hooks: still on hold.** Moving hooks too early would mix API ownership, loading/error state, and behavior orchestration before service boundaries have been fully verified. Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

`AlertsTable.js` extraction remains paused. The remaining complexity is not presentation — it combines selected alert behavior, notes/actions, response logs, grouped/collapsed table state, exports/report links, hover/selection UI, and many display styles. Wait for a specific, clearly bounded target.

**Backend next step: read-only planning only.**

The next session should choose ONE of:

1. **Route grouping plan** — map route groups, identify shared decorator dependencies, and design a Flask Blueprint architecture. Planning only. Do not move any routes until the plan is written, reviewed, and the rollback strategy is clear.
2. **Detection/correlation test harness plan** — design behavioral tests for all 7 detection cores and both correlation engines before any code moves. Planning only. Do not move detection or correlation code without passing tests.

Do not begin implementation of either path without a written plan agreed on first.

## 7. Remaining High-Risk Areas

Frontend — permanently blocked until explicitly re-evaluated:

- `AlertsTable.js` behavior coupling (notes, response actions, response logs, grouped/collapsed table, exports, hover/selection).
- Alert polling in `App.js`.
- Auth/session state in `App.js`.
- Broad custom hooks.

Backend — permanently blocked until a test harness exists:

- Detection engine (7 `_generate_*_core` functions, ~1,060 lines). These write alerts, suppress duplicates, and trigger correlation. Moving these requires behavioral tests that confirm identical alert output before and after. Do not touch without tests.
- Correlation engine (`generate_correlated_activity_alerts`, `generate_targeted_correlation_alerts`, ~389 lines). Cross-references alert types, writes alerts. Same requirement. Do not touch without tests.
- `ingest_normalized_event` — orchestration fan-out hub. All 7 detection cores and both correlation engines are called from here. Blocked until detection/correlation tests exist.

Backend — blocked until Blueprint architecture plan exists:

- All routes — grouping into Flask Blueprints requires a written plan covering shared decorators, import structure, and rollback strategy. Planning first, implementation after.

Backend — permanently blocked (Flask-session bound):

- Auth/RBAC helpers, `User` class, `load_user`, login/logout/session routes — Flask-Login bound and session-critical. No safe extraction pattern exists.

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
- 7 constants also used directly in detection core and correlation bodies; re-imported into `siem_backend.py` namespace — zero call site changes.

Phase 6 — FUTURE: Frontend hooks (low-complexity domain only).

- Only after route grouping plan is stable and the backend is not actively changing.
- Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

Phase 7 — FUTURE: Backend route grouping planning.

- Planning only at first. Map route groups, identify shared decorator dependencies, design Blueprint architecture.
- Do not move routes until the plan is written, reviewed, and rollback strategy is clear.

Phase 8 — FUTURE: Detection and correlation modularization.

- Move only after behavioral tests exist for all 7 detection cores and both correlation engines.
- Expect high risk: these functions write alerts, suppress duplicates, and trigger related behavior.
- Tests are a hard prerequisite — do not begin without them.

## 9. Verification Checklist

**Phase 5 baseline (current passing state):**

```bash
python3 -m py_compile siem_backend.py backend_detection_config.py backend_db.py backend_ip_helpers.py backend_reporting_helpers.py backend_enrichment_helpers.py backend_pdf_helpers.py backend_query_helpers.py backend_ingest_normalizers.py
```

VM smoke tests verified after each phase:
- Phase 4 Step 1: login, blocklist add/remove, alert load.
- Phase 4 Step 2: alert load (reputation + geo fields present), `/alerts/backfill-reputation` (exercises `lookup_ip_reputation`).
- Phase 5: `GET /admin/detection-rules` (4 rules returned, `override_status` correct), `PATCH /admin/detection-rules/failed_login_threshold` (exercises `get_effective_detection_rule` + `current_app.logger` inside Flask app context).

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

**Phase 4 status: COMPLETE. Phase 5 status: COMPLETE.**

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

**Call site audit for `create_blocked_ip_record`:**
- Line 2048: inside `execute_response_action` — this function moves in Step 2, no conflict
- Line 4400: inside a blocklist route — stays in `siem_backend.py`, resolves via import

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
- 21 detection constants moved with the cluster. 7 of those constants (`HTTP_ERROR_THRESHOLD`, `HTTP_ERROR_WINDOW_MINUTES`, `APPLICATION_EXCEPTION_THRESHOLD`, `APPLICATION_EXCEPTION_WINDOW_MINUTES`, `HIGH_REQUEST_RATE_THRESHOLD`, `HIGH_REQUEST_RATE_WINDOW_MINUTES`, `CORRELATION_WINDOW_MINUTES`) are also referenced directly in detection core and correlation function bodies in `siem_backend.py`. These were re-exported via the `from backend_detection_config import ...` block so detection function bodies required zero changes.
- `import json` was confirmed unused in `siem_backend.py` after the move (only user was `parse_detection_rule_parameters`) and was removed.

**Current stop point:** `siem_backend.py` is at ~4,018 lines. The safe extraction surface is exhausted. Next work is planning only.
