# Source Health Workspace Verification

Status: Mac-owned Phases 1–5 complete within the authorized scope; VM-owned Phase 6 remains pending explicit commit, push, and deployment authorization.

## Mac AI Evidence

- Backend final affected test command/result: `python3 -m pytest tests/test_source_health.py tests/test_events_search_api_contracts.py tests/test_ingest_api_contracts.py tests/test_source_aware_detection.py tests/test_alerts_api_contracts.py -q` — 74 passed, 2 environment warnings
- Frontend focused test command/result: `npm test -- --runInBand --watchAll=false src/utils/sourceMetadata.test.js src/services/sourceHealthService.test.js src/components/SourceHealthPanel.test.js src/utils/sectionsConfig.test.js src/App.test.js` — 47 passed
- Existing Dashboard/sidebar/Live Logs regression command/result: `npm test -- --runInBand --watchAll=false src/components/SidebarLayout.test.js src/components/Sidebar.test.js src/components/LiveLogsPanel.test.js src/components/DetectionRulesPanel.test.js src/utils/alertDashboardData.test.js src/App.test.js` — 90 passed; pre-existing React `act(...)` warnings remain in `LiveLogsPanel.test.js`
- Final full frontend suite: `npm test -- --runInBand --watchAll=false` — 60 suites and 772 tests passed; existing unrelated React `act(...)`, DOM-nesting, and style warnings remain
- Final frontend production build: `npm run build` — passed; existing warnings in `App.js`, `IncidentsPanel.js`, and `LiveLogsPanel.js`, with no new Source Health warning
- Final database aggregation query-plan evidence: the passing backend run re-executed PostgreSQL `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` over 6,000 representative events and produced one aggregate with six rows and exactly one scan of `events`; the code issues one cursor execution, and no per-source query loop or migration blocker was found
- Desktop browser evidence: `/private/tmp/source-health-populated.png`, `/private/tmp/source-health-all-never.png`, and `/private/tmp/source-health-error.png`; six canonical cards, one never-seen source, all-never-seen explanation, retained-data error, recovery, and no horizontal overflow verified
- Narrow-width browser evidence: `/private/tmp/source-health-narrow.png`; 390x844 viewport rendered all six entries without horizontal document overflow
- Keyboard/accessibility and reduced-motion evidence: source-specific accessible action names verified for all six sources; Refresh retained programmatic keyboard focus at narrow width; `prefers-reduced-motion: reduce` was active without rendering or navigation failure
- Dark-theme/contrast review: card background `rgb(22, 27, 34)` with readable light text and existing source badges verified in the desktop capture
- Polling browser evidence: Source Health request count advanced from 5 to 6 across one configured interval; error recovery retained the workspace and successful data
- Live Logs browser evidence: actions reached `Honeypot`, `Bank App`, `pfSense`, `NGINX`, `Azure`, and `OTEL` destination workspaces in canonical order
- Browser console evidence: no Source Health exceptions or errors; only existing Dashboard chart dimension warnings occurred before entering Source Health
- Dashboard regression evidence: Dashboard remained registered and unchanged in browser navigation; focused Dashboard data/App regressions and the complete frontend suite passed
- Python compilation: `PYTHONPYCACHEPREFIX=/private/tmp/source-health-pycache python3 -m py_compile core/source_inventory.py core/source_health.py routes/source_health_routes.py routes/alerts_events_routes.py siem_backend.py tests/test_source_health.py` — passed
- Schema/migration tests: `python3 -m pytest tests/test_schema_migrations.py -q` — 25 passed, 2 environment warnings
- Schema snapshot validation: `python3 scripts/validate_schema_snapshot.py` — passed; `schema.sql` matches latest migration `0018`
- `git diff --check`: passed after the final Phase 5 handoff update
- `openspec validate add-source-health-workspace --strict`: passed after the final Phase 5 handoff update; the CLI separately reported a non-fatal blocked analytics flush because external network access was unavailable
- Final implementation diff scope review: the source diff is limited to the approved Source Health inventory, grouped read-only aggregation/API, existing event-search allowlist reuse, frontend metadata/workspace/navigation, and focused tests. No ingestion route/engine, parser/listener, detection engine/rule, correlation, SOAR, pfSense behavior, Dashboard alert calculation, migration, `schema.sql`, secret, environment, service unit, or production-runtime file changed.

## Final Contract Review

- Backend ordering: `CANONICAL_SOURCES` defines exactly `honeypot`, `bank_app`, `pfsense`, `nginx`, `azure_insights`, and `opentelemetry` in that order. Aggregated rows are overlaid onto that tuple, so unknown stored source values cannot add response entries.
- Frontend alignment: `SOURCE_METADATA` is the only Source Health source inventory. Source Health rendering consumes API entries after exact order/identity validation, while sidebar Live Logs definitions, Dashboard source choices, Detection Rules display labels, and Live Logs labels derive from the shared frontend metadata.
- Query/count semantics: one grouped PostgreSQL query uses `COUNT(*)`, filtered counts, `MAX(created_at)`, `source = ANY(...)`, and `GROUP BY source`; there is no limit and no `/events/search` aggregation.
- UTC semantics: one timezone-aware observation instant supplies `generated_at`; last hour is inclusive `[generated_at - 1 hour, generated_at]`, and today is inclusive `[00:00:00 UTC, generated_at]`, using `events.created_at`.
- Never-seen behavior: missing grouped rows become `last_event_at=null`, all three counts `0`, and `ever_seen=false`, while every canonical inventory entry remains present.
- RBAC: `login_required` plus `analyst_or_super_admin_required` allows analysts and super administrators, returns `401` without authentication, and rejects insufficient roles through existing behavior.
- Frontend safety: malformed, reordered, incomplete-window, or wrong-identity responses fail explicitly; refresh failures retain the last successful data rather than substituting zeros.
- Polling/navigation: one timer is scheduled only when enabled and is cleared on unmount/workspace exit; focused tests prove focus and scroll preservation. All six actions use their canonical `live-logs-*` destinations.

## Phase 6 VM Deployment Handoff

Owner: **VM AI**, only after the user explicitly authorizes the Mac commit/push and the VM deployment. This handoff does not authorize production access or mutation.

### Release identity and expected files

- Approved commit: **`<APPROVED_COMMIT_SHA>`** (must be replaced with the explicitly authorized pushed commit before VM work).
- Backend runtime files: `core/source_inventory.py`, `core/source_health.py`, `routes/source_health_routes.py`, `routes/alerts_events_routes.py`, and `siem_backend.py`.
- Frontend runtime source/artifact inputs: `frontend/src/App.js`, `frontend/src/components/AlertsToolbar.js`, `frontend/src/components/DetectionRulesPanel.js`, `frontend/src/components/LiveLogsPanel.js`, `frontend/src/components/SourceHealthPanel.js`, `frontend/src/services/sourceHealthService.js`, `frontend/src/utils/sectionsConfig.js`, and `frontend/src/utils/sourceMetadata.js`.
- Tests and OpenSpec artifacts travel with the approved checkout but are not production runtime configuration.
- Database migration: **none**. Do not apply `schema.sql`, create an index, or run a migration for this change.

### Authorized deployment order

1. Record the approved SHA and prior VM SHA/artifact identity. On the VM run `git status --short`; stop and report any output. Do not stash, discard, merge, pull, or overwrite a dirty tree.
2. Run `git fetch origin`, confirm `git rev-parse origin/main` equals `<APPROVED_COMMIT_SHA>`, then synchronize only with `git reset --hard origin/main` under `docs/mac-vm-source-of-truth-policy.md`. Verify `git rev-parse HEAD` equals the approved SHA.
3. Deploy backend first. No migration command is needed for this change. Restart only `siem-backend.service`, then verify `systemctl status siem-backend.service --no-pager` and `curl -fsS http://127.0.0.1:5051/health`.
4. Before frontend deployment, perform the authenticated read-only `/source-health` checks below. A backend route failure blocks frontend deployment.
5. Deploy the exact Mac-built `frontend/build/` artifact using the policy rsync path:

   ```bash
   rsync -avz --delete \
     -e "ssh -i ~/.ssh/jadeng15.pem" \
     /Users/jadengomez/Projects/siem-security-dashboard-public/frontend/build/ \
     jaden@4.204.25.149:/home/jaden/siem-security-dashboard/frontend/build/
   ```

6. Run the browser checks below, record sanitized evidence, then confirm the VM worktree remains clean. Do not mark Phase 6 complete without the production evidence required by tasks 6.1–6.5.

### Exact read-only production verification

Use an existing authorized analyst and super-admin session without printing credentials or cookies.

1. `GET /health` returns HTTP 200 and `status=ok`.
2. Authenticated `GET /source-health` returns HTTP 200 with exactly these ordered source IDs: `honeypot`, `bank_app`, `pfsense`, `nginx`, `azure_insights`, `opentelemetry`.
3. Confirm each entry's exact source type and label: `honeypot/Honeypot`, `custom/Bank App`, `firewall/pfSense`, `web_log/NGINX`, `cloud_api/Azure Application Insights`, and `telemetry/OpenTelemetry`.
4. Confirm `generated_at`, `windows.last_hour_start`, and `windows.today_start` are timezone-aware, `windows.timezone` is `UTC`, the last-hour start is exactly one hour before `generated_at`, and today starts at `00:00:00 UTC` on the generated date.
5. Confirm counts are non-negative integers; `ever_seen=false` entries have null `last_event_at` and zero counts. Compare at least one seen source's `total_events` and `last_event_at` against a read-only PostgreSQL `COUNT(*)`/`MAX(created_at)` query using the same canonical source and observation cutoff. Do not insert test rows.
6. Confirm unauthenticated `GET /source-health` returns 401 and an existing insufficient-role session is rejected. Do not create or alter users for this check.
7. In the deployed UI, confirm Source Health is directly beneath Dashboard, all six cards render in canonical order, UTC wording and never-seen presentation are truthful, manual and automatic refresh retain focus/scroll, and no health classification wording appears.
8. Open every source action and confirm the matching Live Logs workspace: Honeypot, Bank App, pfSense, NGINX, Azure, and OTEL. Confirm Dashboard alert counts/charts remain unchanged and record browser console errors, if any.

### Prohibited mutating production checks

Without separate explicit authorization, do not send synthetic ingest events, configure or restart listeners, change pfSense forwarding, edit source or `.env`, create users, alter roles, change detection rules, trigger SOAR/playbooks/actions, write/delete events or alerts, run schema DDL/migrations, create indexes, or perform cleanup/backfills. The only planned production mutations in an authorized Phase 6 deployment are syncing the approved commit, restarting the affected backend service, and replacing the frontend build artifact.

### Rollback expectations

- Keep the prior approved commit SHA and prior frontend artifact available before deployment.
- If backend health, `/source-health`, RBAC, or contract verification fails, stop before frontend deployment; restore the prior approved checkout through the same clean-tree/reset workflow, restart `siem-backend.service`, and verify `/health`.
- If frontend-only verification fails after the backend passes, restore the prior frontend build artifact. Roll back the backend too if the frontend failure is a backend/frontend contract mismatch.
- No database rollback is expected or authorized because this change adds no migration and performs no data mutation.
- Record the deployed/restored SHA, service restart, artifact identity, health/API/UI results, clean-tree post-check, and unresolved issue. Return any durable defect to Mac AI; do not patch source on the VM.

## VM AI Evidence

- Explicit deployment authorization: pending
- Approved commit: pending
- Clean-tree preflight/post-check: pending
- Migration decision and evidence: pending
- Backend health and authenticated Source Health API smoke test: pending
- Frontend artifact deployment: pending
- Production counts/UTC-boundary sample verification: pending
- All-six-source Live Logs navigation verification: pending
- Rollback readiness: pending

## Scope Confirmation

- Backend Source Health inventory, aggregation, API, and tests plus the approved frontend Source Health workspace and Phase 5 handoff were completed on the Mac; VM deployment remains pending explicit authorization.
- No VM access, commit, push, deployment, archive, or production mutation is authorized by these artifacts.
- Parser failures, listener/collector health, ingest rejection/failure counts, attempted-ingest tracking, freshness thresholds, and health classifications remain out of scope.
