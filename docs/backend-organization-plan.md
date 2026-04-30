# Backend Organization Plan

This document defines stable internal ownership zones inside `siem_backend.py`.

It is a planning document only. It does not recommend immediate extraction or code movement.

## Purpose

- make the backend easier to reason about before any future extraction work
- define what each area of `siem_backend.py` should and should not own
- reduce accidental scope creep during future cleanup

## Current Major Zones

### 1. App Setup / Environment / Global Constants

Owns:
- environment helpers
- app config values
- global constants
- validation sets
- shared static mappings
- Flask app initialization

Should NOT own:
- route-specific business logic
- detector logic
- report/export behavior

Future module candidate:
- `backend_config.py` -> `backend/modules/backend_config.py`

Later extraction risk:
- Low to medium

### 2. Detection Rule Config

Owns:
- default detector parameters
- validation for detector configuration
- helper accessors for effective rule values

Should NOT own:
- actual detector execution
- alert creation behavior
- route logic

Future module candidate:
- `detection_rules.py` -> `backend/modules/detection_rules.py`

Later extraction risk:
- Medium

### 3. Database Helpers

Owns:
- DB connection creation
- schema/setup helpers already in file
- shared low-level DB helper utilities

Should NOT own:
- route ownership
- detector rules
- report formatting logic

Future module candidate:
- `db_helpers.py` -> `backend/modules/db_helpers.py`

Later extraction risk:
- High

Note:
- DB connection handling should be delayed until very late.

### 4. Audit / Reputation Helpers

Owns:
- audit event logging helper
- IP reputation lookup helpers
- shared enrichment helpers tied to reputation/audit context

Should NOT own:
- route-level permission logic
- detector logic
- report rendering

Future module candidate:
- `audit_and_reputation.py` -> `backend/modules/audit_and_reputation.py`

Later extraction risk:
- Medium to high

### 5. Auth / RBAC / Admin Routes

Owns:
- login/session handling
- RBAC decorators and enforcement
- admin management routes
- user/admin-only control paths

Should NOT own:
- ingest normalization
- detector execution
- report rendering helpers

Future module candidate:
- `auth_routes.py` -> `backend/modules/auth_routes.py`

Later extraction risk:
- High

### 6. API Key / Ingest Auth Helpers

Owns:
- API key guard helpers
- source-specific app name helpers
- small ingest-adjacent validation helpers

Should NOT own:
- full ingest route logic
- detector/correlation execution
- admin/session auth

Future module candidate:
- `ingest_auth.py` -> `backend/modules/ingest_auth.py`

Later extraction risk:
- Medium

### 7. Shared Ingest Helpers

Owns:
- normalization-adjacent helpers used by multiple ingest routes
- geolocation helper usage
- event validation sets
- central normalized event write path

Should NOT own:
- source-specific adapter behavior
- report/export logic
- admin actions

Future module candidate:
- `ingest_helpers.py` -> `backend/modules/ingest_helpers.py`

Later extraction risk:
- High

Note:
- `ingest_normalized_event(...)` is a central write path and should be delayed.

### 8. Ingestion Routes

Owns:
- `/ingest`
- `/ingest/web-log`
- `/ingest/azure`
- `/ingest/otlp`
- route-level request validation and adapter invocation

Should NOT own:
- detector rule definitions
- report rendering helpers
- admin user management

Future module candidate:
- `ingest_routes.py` -> `backend/modules/ingest_routes.py`

Later extraction risk:
- High

### 9. Detection Engine

Owns:
- detector execution logic
- alert creation for threshold and event-driven detections
- duplicate suppression behavior within detectors

Should NOT own:
- correlation logic
- UI/export formatting
- auth or admin logic

Future module candidate:
- `detectors.py` -> `backend/modules/detectors.py`

Later extraction risk:
- High

### 10. Correlation Engine

Owns:
- generic correlation
- targeted multi-signal correlation rules
- correlation alert creation flow

Should NOT own:
- ingest request handling
- report rendering
- admin/auth behavior

Future module candidate:
- `correlation.py` -> `backend/modules/correlation.py`

Later extraction risk:
- High

### 11. Alerts / Events APIs

Owns:
- read APIs for alerts/events
- query/filter behavior for dashboard-facing endpoints
- read-only enrichment applied before response payloads

Should NOT own:
- ingest writes
- detector rule execution
- export rendering internals

Future module candidate:
- `alert_query_routes.py` -> `backend/modules/alert_query_routes.py`

Later extraction risk:
- Medium

### 12. Reporting / Export Helpers and Routes

Owns:
- report formatting helpers
- report data shaping helpers
- CSV/PDF export helpers
- report/export routes

Should NOT own:
- ingest logic
- detector execution
- admin user management

Future module candidate:
- `reporting_exports.py` -> `backend/modules/reporting_exports.py`

Later extraction risk:
- Medium

Note:
- This is the safest likely first extraction candidate, but only after planning and verification guardrails exist.

### 13. Response Actions / Notes / Blocklist

Owns:
- response action execution helpers
- response log routes
- analyst notes
- blocked IP management
- alert status updates

Should NOT own:
- ingest adapter behavior
- detector definitions
- report rendering

Future module candidate:
- `response_actions.py` -> `backend/modules/response_actions.py`

Later extraction risk:
- Medium to high

### 14. Frontend Serving / Entrypoint

Owns:
- SPA static file serving
- catch-all frontend route
- app entrypoint

Should NOT own:
- ingest logic
- admin logic
- report generation

Future module candidate:
- `frontend_serving.py` -> `backend/modules/frontend_serving.py`

Later extraction risk:
- Low

## Suggested Extraction Order

This is a future extraction order, not an instruction to refactor now.

1. Reporting / Export Helpers and Routes
2. Frontend Serving / Entrypoint
3. Alerts / Events APIs
4. Detection Rule Config
5. API Key / Ingest Auth Helpers
6. Response Actions / Notes / Blocklist
7. Audit / Reputation Helpers
8. App Setup / Environment / Global Constants
9. Shared Ingest Helpers
10. Ingestion Routes
11. Detection Engine
12. Correlation Engine
13. Auth / RBAC / Admin Routes
14. Database Helpers

## Zones To Delay Until The End

Delay these until late because they have the highest regression risk:

- Database Helpers
- Auth / RBAC / Admin Routes
- Shared Ingest Helpers
- Ingestion Routes
- Detection Engine
- Correlation Engine

## Required Checks Before And After Future Extraction

Before any future extraction step:
- review `docs/verification-checklist.md`
- decide which checklist items apply to the zone being touched
- define a rollback plan before code movement

Minimum checks that should run before and after extraction work:

```bash
python3 -m py_compile siem_backend.py
cd frontend && npm run build
python3 -m py_compile siem-azure-function/function_app.py
```

Flow checks to re-run as needed from `docs/verification-checklist.md`:
- backend `/health`
- custom `/ingest`
- nginx `/ingest/web-log`
- Azure `/ingest/azure`
- OpenTelemetry `/ingest/otlp`
- events DB verification query
- alerts/report export sanity

## Planning Guidance

- Do not extract multiple high-risk zones in one phase.
- Prefer helper-heavy read-path zones before write-path zones.
- If a change starts to affect route ownership, DB connection handling, detector logic, or correlation semantics, stop and re-scope.
- Any future extraction should begin with a small planning/spec step before code movement.
