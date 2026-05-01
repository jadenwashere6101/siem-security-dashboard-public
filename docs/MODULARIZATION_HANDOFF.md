# Modularization Handoff

Last updated: 2026-05-01 (Phase 3 complete; Phase 4 planned, not started)

This document is the starting point for future sessions working on modularization. It summarizes the current project shape, what has already been extracted safely, what boundaries are still risky, and how to continue without drifting into broad refactors.

## 1. Project Overview

The project is a SIEM security dashboard with a Flask backend and a React frontend.

Backend:

- Main backend entrypoint: `siem_backend.py`
- Supporting backend modules:
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

**Phase 3 is complete. Phase 4 is planned but has NOT started.**

All frontend work is done. The backend pure-utility extraction phase is done. The project is now at a natural boundary between "pure extraction" work and "controlled refactor" work.

Completed safely through Phase 3:

- All frontend presentation components extracted.
- All frontend utility helpers extracted (no state, no side effects).
- All major frontend service modules introduced (see Section 3).
- Backend reporting/enrichment helpers extracted (pure formatting, no Flask deps).
- Backend PDF rendering helpers extracted (`backend_pdf_helpers.py`).
- Backend SQL/query helpers extracted (`backend_query_helpers.py`).
- Backend ingest app-name normalizers extracted (`backend_ingest_normalizers.py`).

What changed in the backend approach from Phase 3 to Phase 4:

- Phase 3 extractions were **pure lifts**: function bodies unchanged, zero imports in new files, no design decisions required.
- Phase 4 extractions require **controlled body changes**: `app.logger` → `current_app.logger` in three functions; `env_first(...)` → `os.getenv(...)` in `get_db_connection`. These are minimal but real changes and must be deliberate.
- Phase 4 also requires moving **mutable module-level state** (`geo_cache`, `REPUTATION_CACHE`) — not possible with pure lifting.

Current stop point: `siem_backend.py` is at ~4,669 lines (down from 5,183). The remaining extractable clusters all require the Phase 4 approach. Do not attempt them as if they were Phase 3 work.

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

- Flask app setup.
- Auth/session/RBAC decorators and routes.
- Admin routes.
- Ingestion routes and `ingest_normalized_event` fan-out.
- Detection functions (7 cores).
- Correlation functions (2 engines).
- Alert/event routes.
- Reporting/export routes.
- Notes/actions/blocklist routes.
- IP geolocation + reputation lookup (module-level caches).
- Response action helpers.
- Frontend serving.

`siem_backend.py` line count: ~4,669 (down from 5,183 at start of modularization).

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

Backend rules — Phase 3 (now complete, preserved for reference):
- Phase 3 was pure lifting only: no body changes, no imports in new files, no design decisions.
- PDF, query, and ingest normalizer extractions are done and follow this pattern.

Backend rules — Phase 4 (active for the next session):
- Extract one module per commit. Do not combine `backend_db.py` and `backend_ip_helpers.py` in a single commit.
- `backend_db.py` must be extracted and verified before `backend_ip_helpers.py` begins. These are not parallel steps.
- Allowed body changes in Phase 4 are limited to: `app.logger` → `current_app.logger`, and `env_first(...)` → inline `os.getenv()` in `get_db_connection` only. No other body changes are permitted.
- Do not move backend routes in Phase 4.
- Do not move detection, correlation, or `ingest_normalized_event` in Phase 4.
- Do not move auth/RBAC helpers in Phase 4.
- Stop if any extraction requires touching detection or correlation function bodies.
- Stop if imports become circular or confusing.

## 6. Current Safe Modularization Direction

**Frontend: done.** All panels and `App.js` delegate HTTP calls to focused service modules. All utility helpers are extracted. Components still own all state, handlers, loading flags, feedback, and UI orchestration. No frontend work is needed before the next backend phase.

**Frontend hooks: still on hold.** Moving hooks too early would mix API ownership, loading/error state, and behavior orchestration before service boundaries have been fully verified. Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

`AlertsTable.js` extraction remains paused. The remaining complexity is not presentation — it combines selected alert behavior, notes/actions, response logs, grouped/collapsed table state, exports/report links, hover/selection UI, and many display styles. Wait for a specific, clearly bounded target.

**Backend next step: Phase 4 Step 1 — extract `backend_db.py`.**

This is the only safe next action. Do not skip to Step 2. Do not attempt `backend_ip_helpers.py` without `backend_db.py` in place first. See Section 12 for the full Phase 4 plan and the exact prompt for Step 1.

## 7. Remaining High-Risk Areas

Frontend — permanently blocked until explicitly re-evaluated:

- `AlertsTable.js` behavior coupling (notes, response actions, response logs, grouped/collapsed table, exports, hover/selection).
- Alert polling in `App.js`.
- Auth/session state in `App.js`.
- Broad custom hooks.

Backend — off-limits in Phase 4, still blocked:

- Detection engine (7 `_generate_*_core` functions, ~1,065 lines). These write alerts, suppress duplicates, and trigger correlation. Do not touch.
- Correlation engine (`generate_correlated_activity_alerts`, `generate_targeted_correlation_alerts`, ~390 lines). Cross-references alert types. Do not touch.
- `ingest_normalized_event` — orchestration fan-out hub. All 7 detection cores and both correlation engines are called from here. Do not touch.
- All routes — no route movement in Phase 4.
- Auth/RBAC helpers and routes — Flask-Login bound, session-critical.
- `backfill_alert_sources` — maintenance utility, no callers in `siem_backend.py`, not needed by any helper module.

Backend — planned for Phase 4 Step 1 (see Section 12):

- `get_db_connection`, `validate_blocked_ip`, `create_blocked_ip_record` — moving to `backend_db.py`.

Backend — planned for Phase 4 Step 2, blocked until Step 1 is committed (see Section 12):

- `lookup_ip_location`, `lookup_ip_reputation`, `get_ip_reputation`, `determine_response_action`, `execute_response_action`, `_get_reputation_label`, `_build_reputation_summary` — moving to `backend_ip_helpers.py`.

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

Phase 4 — PLANNED, NOT STARTED: Backend DB foundation + IP/reputation cluster.

- See Section 12 for full design decisions, order of operations, and risk notes.
- Step 1: Extract `backend_db.py`. Prerequisite for Step 2.
- Step 2: Extract `backend_ip_helpers.py`. Requires Step 1 committed and verified first.
- Do not combine Step 1 and Step 2 in a single commit.
- This is a controlled refactor phase, not a pure extraction phase.

Phase 5 — FUTURE: Frontend hooks (low-complexity domain only).

- Only after Phase 4 is stable and smoke-tested.
- Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

Phase 6 — FUTURE: Backend route grouping planning.

- Planning only at first. Identify route groups and shared dependencies.
- Do not move routes until behavior checks and rollback points are clear.

Phase 7 — FUTURE: Detection and correlation modularization.

- Move only after detection/correlation behavior checks exist.
- Expect high risk because these functions write alerts, suppress duplicates, and trigger related behavior.

## 9. Verification Checklist

**Phase 3 baseline (current passing state):**

```bash
cd frontend && npm run build
python3 -m py_compile siem_backend.py backend_reporting_helpers.py backend_enrichment_helpers.py backend_pdf_helpers.py backend_query_helpers.py backend_ingest_normalizers.py
```

**After Phase 4 Step 1 (`backend_db.py`):**

```bash
python3 -m py_compile siem_backend.py backend_db.py backend_reporting_helpers.py backend_enrichment_helpers.py backend_pdf_helpers.py backend_query_helpers.py backend_ingest_normalizers.py
```

Smoke test after Step 1: login, blocklist add, blocklist remove, alert load.

**After Phase 4 Step 2 (`backend_ip_helpers.py`):**

```bash
python3 -m py_compile siem_backend.py backend_ip_helpers.py backend_db.py backend_reporting_helpers.py backend_enrichment_helpers.py backend_pdf_helpers.py backend_query_helpers.py backend_ingest_normalizers.py
```

Smoke test after Step 2: ingest a test event (exercises `lookup_ip_location`), load alerts (exercises `get_ip_reputation`), trigger `/alerts/backfill-reputation` (exercises `lookup_ip_reputation`), verify reputation and response fields on a detection-generated alert.

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

## 12. Phase 4 Architecture Notes

**Status: planned and approved, not started. Next session begins with Step 1 only.**

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
- Phase 4 Step 1 (`backend_db.py`): NOT STARTED. Begin here next session.
- Phase 4 Step 2 (`backend_ip_helpers.py`): NOT STARTED. Do not start until Step 1 is committed and verified.
- Do not combine Step 1 and Step 2 in a single commit.
- Do not attempt detection, correlation, route, or auth extraction in Phase 4.
