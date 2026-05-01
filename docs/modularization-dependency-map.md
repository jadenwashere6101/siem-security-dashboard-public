# Modularization Dependency Map

This document is a planning reference for future modularization work.

It is intentionally read-only in spirit: it maps current dependencies, identifies safer extraction paths, and defines phase gates before any code movement. It does not recommend a big-bang split.

## Scope

Repository:

```text
/Users/jadengomez/Desktop/siem-security-dashboard-public
```

Primary files reviewed:

- `siem_backend.py`
- `backend_reporting_helpers.py`
- `adapters/`
- `scripts/`
- `frontend/src/App.js`
- `frontend/src/components/AlertsTable.js`
- other large frontend components
- existing `docs/` planning files as supporting context

## 1. Backend Dependency Map

### Main Backend File

`siem_backend.py` is the current backend hub. It owns app setup, auth, ingestion, detection, correlation, alert APIs, reporting/export, response actions, blocklist operations, and frontend serving.

### Route Groups

- Auth/session routes:
  - `/login`
  - `/logout`
  - `/auth/me`
- Admin user/RBAC routes:
  - `/admin/users`
  - `/admin/users/<username>/status`
  - `/admin/users/<username>/password`
  - `/admin/users/<username>/role`
- Admin config/audit routes:
  - `/admin/audit-log`
  - `/admin/detection-rules`
  - `/admin/detection-rules/<rule_id>`
- Ingestion routes:
  - `/ingest`
  - `/ingest/web-log`
  - `/ingest/azure`
  - `/ingest/otlp`
- Alerts/events routes:
  - `/alerts`
  - `/events/search`
  - `/alerts/backfill-reputation`
- Reporting/export routes:
  - `/alerts/<int:alert_id>/report`
  - `/alerts/<int:alert_id>/report/pdf`
  - `/alerts/report`
  - `/alerts/export/csv`
  - `/alerts/report/pdf`
- Response actions, notes, and blocklist routes:
  - `/alerts/<int:alert_id>/response-log`
  - `/alerts/<int:alert_id>/notes`
  - `/blocked-ips`
  - `/blocked-ips/<int:block_id>/unblock`
  - `/alerts/<int:alert_id>/execute`
  - `/alerts/<int:alert_id>/status`
- Frontend serving:
  - `/`
  - `/<path:path>`

### Shared Helpers

- Environment/config helpers:
  - `env_first`
  - `env_csv`
- Detection rule configuration:
  - `get_detection_rule_defaults`
  - `parse_detection_rule_parameters`
  - `validate_detection_rule_config`
  - `get_effective_detection_rule`
  - `get_all_effective_detection_rules`
- Database helpers:
  - `get_db_connection`
  - `backfill_alert_sources`
  - many direct `cur.execute(...)` usages across routes and detection logic
- Audit/reputation helpers:
  - `log_audit_event`
  - `get_ip_reputation`
  - `lookup_ip_reputation`
  - reputation label/summary helpers
- Auth/RBAC:
  - `User`
  - `load_user`
  - `admin_required`
  - `super_admin_required`
  - `analyst_or_super_admin_required`
  - `deny_rbac_access`
- API key guards:
  - `require_api_key`
  - `require_azure_api_key`
  - `require_otel_api_key`

### DB Access Points

DB access is currently centralized by helper but decentralized by usage.

- Connection creation:
  - `get_db_connection`
- High-coupling DB areas:
  - auth/admin routes
  - audit logging
  - ingestion write path
  - detection functions
  - correlation functions
  - alert search/filter routes
  - reporting/export query helpers
  - notes/actions/blocklist routes

Because SQL execution is spread through the backend, DB access should not be extracted early.

### Detection Functions

Detector functions currently create alerts, perform duplicate suppression, and may trigger correlation behavior.

- `_generate_failed_login_alerts_core`
- `_generate_password_spraying_alerts_core`
- `_generate_successful_login_after_spray_alerts_core`
- `_generate_port_scan_alerts_core`
- `_generate_http_error_alerts_core`
- `_generate_application_exception_alerts_core`
- `_generate_high_request_rate_alerts_core`

These are high-value but high-risk extraction candidates.

### Correlation Functions

Correlation logic is tightly coupled to alert table shape, alert types, severity decisions, and duplicate suppression.

- `generate_correlated_activity_alerts`
- `generate_targeted_correlation_alerts`

Delay this work until targeted behavior checks exist.

### Reporting / Export Functions

Already partially extracted:

- `backend_reporting_helpers.py`

Currently extracted helpers include:

- timestamp formatting
- display value formatting
- alert summary narrative helpers
- severity/confidence/next-step helpers

Still in `siem_backend.py`:

- alert report normalization
- alert/report SQL query helpers
- PDF rendering helpers
- TXT/PDF/CSV export routes

Reporting is the safest backend area to continue extracting, but route movement should wait.

### Adapters

Adapters are already separated and are good examples of modular boundaries.

- `adapters/azure_insights_adapter.py`
  - Azure Application Insights and identity telemetry normalization
- `adapters/nginx_adapter.py`
  - nginx access log parsing
- `adapters/otel_adapter.py`
  - OpenTelemetry payload normalization

### Scripts

- `scripts/ingest_log_files.py`
  - standalone log ingestion helper
  - reads log files and posts lines to the SIEM ingestion API

This script should remain separate from backend modularization unless shared client utilities are intentionally introduced later.

## 2. Frontend Dependency Map

### Largest Components

- `frontend/src/components/AlertsTable.js`
  - largest frontend component
  - owns grouped alert table rendering, selected alert detail UI, response logs, notes, exports, actions, grouped source IP behavior, and many inline styles
- `frontend/src/App.js`
  - owns auth/session state, section navigation, alert polling, alert filters, dashboard metrics, and chart data
- `frontend/src/components/ThreatHuntPanel.js`
  - owns threat hunt filters, event search, expanded event display, copy/pivot feedback, and large style clusters
- `frontend/src/components/AdminUsersPanel.js`
  - owns admin user table, create user flow, status toggles, role changes, and password reset state

### State Owners

- `App.js` owns:
  - authenticated session state
  - current username/role
  - active section
  - alert list
  - dashboard filters
  - selected alert ID
  - alert polling
  - dashboard metrics/chart derived data
- `AlertsTable.js` owns:
  - response logs
  - alert notes
  - note drafts
  - note/action loading flags
  - toast messages
  - selected alert object
  - hovered row state
  - collapsed alert groups
- `ThreatHuntPanel.js` owns:
  - search filters
  - event results
  - expanded event ID
  - copy feedback
  - pivot feedback/highlight state
- `AdminUsersPanel.js` owns:
  - users list
  - create-user form state
  - status/role/password mutation state
- `DetectionRulesPanel.js`, `AuditLogPanel.js`, and `BlocklistManagerPanel.js` own their own local loading, error, and mutation state.

### API Call Locations

- `App.js`:
  - `/auth/me`
  - `/login`
  - `/alerts`
  - `/logout`
  - `/alerts/<id>/status`
- `AlertsTable.js`:
  - `/alerts/<id>/response-log`
  - `/alerts/<id>/notes`
  - `/alerts/<id>/execute`
  - `/alerts`
  - report/export URLs
- `ThreatHuntPanel.js`:
  - `/events/search`
- `AdminUsersPanel.js`:
  - `/admin/users`
  - `/admin/users/<username>/status`
  - `/admin/users/<username>/password`
  - `/admin/users/<username>/role`
- `DetectionRulesPanel.js`:
  - `/admin/detection-rules`
- `AuditLogPanel.js`:
  - `/admin/audit-log`
- `BlocklistManagerPanel.js`:
  - `/blocked-ips`

### Candidates For Hooks / Components

Potential utilities:

- shared `buildSiemPath`
- session storage helpers from `App.js`
- timestamp/display formatting helpers

Potential hooks, later only:

- `useAuthSession`
- `useAlertsPolling`
- `useAlertNotes`
- `useResponseLogs`
- `useThreatHuntSearch`

Do not extract hooks until presentation extraction is proven safe.

Potential components:

- `AlertTimeline`
- `AlertsToolbar`
- `AlertDetailsPanel`
- `GroupedAlertsTable`
- `AlertTableRow`
- `AlertNotesAndActions`
- `ThreatHuntResultsTable`
- `ThreatHuntEventDetails`
- `AdminUserRow`
- `PasswordResetInlinePanel`

## 3. Safest Backend Extractions First

### First Candidates

1. Continue pure reporting helper extraction into `backend_reporting_helpers.py`.
   - Keep this limited to pure functions with no DB, Flask, request, or `current_user` dependency.

2. Extract read-only constants/config helpers.
   - Candidate future module: `backend_config.py`
   - Include environment helpers, validation sets, and static mappings only if import direction remains simple.

3. Extract small API-key guard helpers only after import boundaries are clear.
   - `require_api_key`
   - `require_azure_api_key`
   - `require_otel_api_key`

### Keep In Place Initially

- `get_db_connection`
- `ingest_normalized_event`
- detection functions
- correlation functions
- Flask route functions
- export routes

## 4. Safest Frontend Extractions First

### First Candidates

1. `AlertTimeline`
   - UI-only
   - narrow responsibility
   - low mutation risk

2. `AlertsToolbar`
   - search/filter/export controls
   - mostly controlled props
   - keep state in `AlertsTable.js`/`App.js`

3. Shared frontend path/session utilities.
   - `buildSiemPath`
   - session identity storage helpers
   - do this only if imports stay simple

4. `ThreatHuntEventDetails` or `ThreatHuntResultsTable`
   - presentation-first extraction
   - keep `/events/search` in `ThreatHuntPanel.js`

5. `AdminUserRow`
   - keep admin mutations in `AdminUsersPanel.js`

### Keep In Place Initially

- API calls
- mutation handlers
- auth/session ownership
- alert polling
- selected alert ownership
- grouped alert state
- notes/actions state

## 5. High-Risk Areas To Delay

Backend:

- DB connection and transaction ownership
- `ingest_normalized_event`
- ingestion route modularization
- detector execution functions
- correlation functions
- auth/RBAC decorators and `current_user` coupling
- report/export routes
- PDF generation response flow

Frontend:

- moving API calls into hooks
- moving auth/session state out of `App.js`
- moving alert polling
- moving notes/actions mutations from `AlertsTable.js`
- splitting grouped alert row logic before smaller display pieces are proven safe
- broad style-system cleanup during component extraction

## 6. Recommended Modularization Phases

### Phase 0: Baseline And Checkpoint

No code movement.

- Confirm the app runs.
- Confirm frontend build passes.
- Confirm backend starts.
- Confirm current behavior with a short manual checklist.
- Commit or otherwise checkpoint the current working state.

### Phase 1: Pure Helper Extraction

Backend:

- Continue extracting pure reporting/config helpers only.

Frontend:

- Extract tiny utilities only if import boundaries are obvious.

Gate:

- One helper group per commit.
- No route movement.
- No DB behavior movement.

### Phase 2: Frontend Presentation Extraction

Extract UI-only components first.

Suggested order:

1. `AlertTimeline`
2. `AlertsToolbar`
3. selected alert read-only display pieces
4. threat hunt display pieces
5. admin user row display pieces

Gate:

- No frontend state/API extraction until presentation extraction is proven safe.
- Keep parent state ownership unchanged.
- Keep prop names stable where practical.

### Phase 3: Reporting Module Expansion

Move additional reporting helpers after pure helpers are stable.

Possible later candidates:

- report header helpers
- PDF palette helpers
- report section builders
- PDF draw helpers

Gate:

- Export routes stay in `siem_backend.py` until helper extraction is clean.

### Phase 4: Admin/Auth Organization

Plan route grouping for admin/auth areas.

Gate:

- Do not move decorators and routes together without a rollback point.
- Keep login/session behavior verified before and after.

### Phase 5: Ingestion Organization

Move only after behavior checks pass.

Gate:

- No ingestion modularization until behavior checks pass.
- Keep adapter behavior stable.
- Keep `ingest_normalized_event` in place until route wrappers are stable.

### Phase 6: Detection And Correlation Modularization

Highest-risk phase.

Gate:

- No detection/correlation modularization until targeted checks exist.
- Required targeted checks should cover each detector and both correlation paths.
- Do not move detection and correlation in the same commit.

## 7. Required Checks Before / After Each Phase

### Before Each Phase

- Check `git status`.
- Confirm the intended write scope.
- Confirm no unrelated files are being changed.
- Run or manually verify:
  - backend startup
  - frontend build
  - login/logout
  - alerts load
  - one sample ingest path

### After Each Phase

Minimum behavior checks:

- `/auth/me` returns expected state.
- login works.
- logout works.
- `/alerts` loads.
- alert status update works.
- note load/add works if alert UI was touched.
- response log/action works if alert UI was touched.
- report TXT/PDF/CSV export works if reporting was touched.
- admin users work if admin/auth was touched.
- detection rules work if config/admin detection was touched.
- ingestion sample works if ingest was touched.

Frontend checks:

- `npm run build` from `frontend/`
- dashboard renders
- filters still work
- selected alert details still work
- role-based UI still behaves correctly

Backend checks:

- backend imports cleanly
- app starts
- touched endpoints return expected status codes
- no new circular imports

## 8. Rollback Strategy

- One module/component per commit.
- Avoid big-bang splits.
- Do not rename and move in the same commit.
- Keep public function/component names stable during first extraction.
- Import moved helpers back into existing callers instead of changing behavior.
- Prefer additive extraction followed by small call-site updates.
- If a phase breaks behavior, revert the single commit for that extraction.
- Do not continue stacking extractions on top of a failing phase.

## Current Standing

The project is ready to plan modularization, but not ready for a large split.

Best next move:

- start with the smallest pure helper or UI-only presentation extraction
- verify behavior after each step
- delay ingestion, detection, correlation, DB, and auth route movement until stricter checks exist

## Phase 1 Execution Target (Immediate Next Step)

Exact scope:

- Continue extracting only pure backend reporting helpers.
- Continue extracting only UI-only frontend components, such as `AlertTimeline`.

Explicitly not allowed in Phase 1:

- No route movement.
- No DB helper movement.
- No ingestion changes.
- No detection/correlation changes.
- No API call movement.
- No frontend state movement.

Success criteria:

- `siem_backend.py` shrinks slightly without breaking imports.
- Frontend components become smaller without changing behavior.
- All verification and behavior checks pass.
- No circular imports are introduced.

Stop conditions:

- Imports become confusing.
- Behavior becomes unclear.
- Multiple files need to change at once.
