# Modularization Handoff

Last updated: 2026-05-01

This document is the starting point for future sessions working on modularization. It summarizes the current project shape, what has already been extracted safely, what boundaries are still risky, and how to continue without drifting into broad refactors.

## 1. Project Overview

The project is a SIEM security dashboard with a Flask backend and a React frontend.

Backend:

- Main backend entrypoint: `siem_backend.py`
- Supporting backend modules:
  - `backend_reporting_helpers.py`
  - `backend_enrichment_helpers.py`
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

The frontend service-boundary extraction phase is now complete. All major panels delegate HTTP calls to focused service modules. `App.js` delegates auth and alert-loading calls to service modules as well.

Completed safely:

- Small frontend presentation components were extracted.
- Pure frontend utility helpers were extracted.
- All major frontend service modules were introduced (see Section 3).
- Backend reporting/enrichment helpers were extracted without moving routes or DB logic.

Current phase:

- Service-boundary work is done for all existing panels and for `App.js` auth/alert loading.
- The next direction is small pure utility extractions where clearly duplicated logic remains inline.
- Do not start broad hooks, state movement, backend route movement, DB extraction, ingestion extraction, detection extraction, or correlation extraction yet.

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

`siem_backend.py` imports these helpers and still owns:

- Flask app setup.
- Auth/session/RBAC decorators and routes.
- Admin routes.
- Ingestion routes.
- Detection functions.
- Correlation functions.
- Alert/event routes.
- Reporting/export routes.
- Reporting SQL/query helpers.
- PDF rendering helpers.
- Notes/actions/blocklist routes.
- Frontend serving.

Backend reporting extraction should pause before PDF helper movement, SQL/query helper movement, or route movement.

## 5. Current Architectural Rules

Keep these rules active until the roadmap is intentionally updated:

- Keep state ownership in parent components.
- Avoid new custom hooks for now unless they are clearly safer than utilities/services.
- Avoid `GroupedAlertsTable` extraction for now.
- Do not move auth/session state yet.
- Do not move alert polling yet.
- Do not move frontend API ownership broadly.
- Extract one focused module/component per commit.
- Prefer pure utilities before behavior movement.
- Prefer focused service modules before hooks.
- Do not move backend routes yet.
- Do not move backend DB helpers yet.
- Do not move ingestion, detection, or correlation logic yet.
- Do not move PDF/report rendering helpers yet.
- Stop if imports become confusing, behavior becomes unclear, or multiple unrelated files need to change at once.

## 6. Current Safe Modularization Direction

The frontend service-boundary phase is complete. All panels and `App.js` now delegate HTTP calls to focused service modules. Components still own all state, handlers, loading flags, feedback, and UI orchestration.

The next candidates are small pure utility extractions where clearly duplicated display or formatting logic remains inline across multiple components. Pure utilities are the lowest-risk class of extraction because they carry no state, no side effects, and no behavior.

Hooks should wait. Moving hooks too early would mix API ownership, loading/error state, and behavior orchestration before service boundaries have been fully verified. Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

`AlertsTable.js` extraction remains paused. The remaining complexity is not presentation — it combines:

- selected alert behavior
- notes/actions behavior
- response logs
- grouped/collapsed table state
- exports/report links
- hover/selection UI
- many display styles

More `AlertsTable.js` movement should wait until there is a specific behavior boundary with clear tests or a much smaller target.

## 7. Remaining High-Risk Areas

Frontend high-risk areas:

- `AlertsTable.js` behavior coupling (notes, response actions, response logs, grouped table, exports).
- Alert polling in `App.js`.
- Auth/session state in `App.js`.
- Broad custom hooks.

Backend high-risk areas:

- Detection logic.
- Correlation logic.
- Ingestion routes and ingestion normalization.
- DB helpers and SQL/query helper extraction.
- Auth/session/RBAC route movement.
- Backend route grouping.
- PDF/report rendering helpers.
- Report/export route movement.

## 8. Suggested Next Phases

Phase 1 — COMPLETE: Verify and stabilize current extractions.

Phase 2 — COMPLETE: Frontend service-boundary modularization.

- All major panels delegate HTTP calls to service modules.
- `App.js` delegates auth and alert-loading calls to service modules.
- State, handlers, loading flags, feedback, and orchestration remain in components.

Phase 3: Small pure utility extractions (current).

- Extract only clearly duplicated pure helpers with no state or side effects.
- One extraction per commit.
- Do not mix utility and service changes in the same commit.

Phase 4: Consider small hooks after verification.

- Only after the service and utility layers are stable and smoke-tested.
- Start with a single low-complexity domain.
- Do not start with auth, alert polling, notes/actions, or `AlertsTable.js`.

Phase 5: Plan backend route grouping.

- Planning only at first.
- Identify route groups and shared dependencies.
- Do not move routes until behavior checks and rollback points are clear.

Phase 6: Backend extraction after stronger checks.

- Consider route grouping before deeper behavior movement.
- Keep DB helpers, ingestion, detection, and correlation delayed until targeted checks exist.

Phase 7: Detection and correlation modularization.

- Move only after detection/correlation behavior checks exist.
- Expect higher risk because these functions write alerts, suppress duplicates, and trigger related behavior.

## 9. Verification Checklist

Run these before continuing modularization and before committing:

```bash
cd frontend && npm run build
python3 -m py_compile siem_backend.py backend_reporting_helpers.py backend_enrichment_helpers.py
```

Useful backend compile expansion:

```bash
python3 -m py_compile adapters/azure_insights_adapter.py adapters/nginx_adapter.py adapters/otel_adapter.py scripts/ingest_log_files.py
```

Manual smoke-test areas:

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

Known existing frontend build warnings to track separately:

- `App.js` hook dependency warnings around `checkAuth` and `fetchAlerts`.
- `App.js` unused `subtitleStyle`.
- `AdminUsersPanel.js` duplicate `paddingTop` style key.

These warnings should not be mixed into modularization commits unless the user explicitly asks for cleanup.

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
