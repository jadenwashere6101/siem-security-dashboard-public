# Tasks: SOAR Integration Adapter Status Frontend

Implement later in small read-only visibility steps. Do not implement as part of this
spec-only change.

## Step 1: Confirm Existing API Shape

Before writing any frontend code, verify the backend endpoint is working as expected.

- [ ] Call `GET /integrations/status` manually or inspect `routes/integration_routes.py`.
- [ ] Confirm response includes `mode`, `simulated`, `real_mode_enabled`, `real_mode_status`.
- [ ] Confirm response includes `adapters` array.
- [ ] Confirm each adapter entry includes `name`, `mode`, `simulated`, `supported_actions`.
- [ ] Confirm unauthenticated requests return existing unauthorized response shape.
- [ ] Confirm analyst and super-admin tokens return HTTP 200.

If any field is missing, investigate before writing frontend code. Do not add backend
changes as part of this change — stop and open a new spec if the backend response shape
needs adjustment.

## Step 2: Add Service Helper

File:

```text
frontend/src/services/integrationService.js
```

- [ ] Export `getIntegrationStatus()` using the same fetch wrapper and auth header
      pattern as `playbookService.js`, `approvalService.js`, and `soarQueueService.js`.
- [ ] Call `GET /integrations/status`.
- [ ] Return parsed JSON on success.
- [ ] Throw on non-OK status.
- [ ] Do not add polling, retry, or background refresh.
- [ ] Do not call any other endpoint.

Verification:

```bash
node -e "require('./frontend/src/services/integrationService.js')" 2>&1 | head -5
```

(Syntax check only — do not run against a live server during spec implementation.)

## Step 3: Add Service Tests

File:

```text
frontend/src/services/integrationService.test.js
```

- [ ] Test `getIntegrationStatus()` calls `GET /integrations/status`.
- [ ] Test `getIntegrationStatus()` returns parsed JSON on a mocked success response.
- [ ] Test `getIntegrationStatus()` throws on a mocked non-OK response.

Verification:

```bash
npm test -- --watchAll=false frontend/src/services/integrationService.test.js
```

## Step 4: Add IntegrationStatusPanel Component

File:

```text
frontend/src/components/IntegrationStatusPanel.js
```

- [ ] Call `getIntegrationStatus()` on mount via `useEffect`.
- [ ] Render a loading state while the request is in flight.
- [ ] Render a user-friendly error message on API failure.
- [ ] Render an empty state when `adapters` is missing, null, or empty.
- [ ] Render a mode summary section showing:
  - [ ] `mode` value
  - [ ] `simulated` flag clearly labeled
  - [ ] `real_mode_enabled: false` labeled as "Real mode disabled"
  - [ ] `real_mode_status` value
- [ ] Render one row or card per adapter showing:
  - [ ] Adapter name
  - [ ] Mode badge
  - [ ] Simulated flag
  - [ ] Supported actions as a readable list
- [ ] Include a persistent simulation mode notice (never conditionally hidden).
- [ ] Do not render any test-connection, run, execute, or mutation controls.
- [ ] Access all response fields defensively (guard against null/undefined).

## Step 5: Add Component Tests

File:

```text
frontend/src/components/IntegrationStatusPanel.test.js
```

- [ ] Test loading state renders while request is in flight.
- [ ] Test error state renders on mocked API failure.
- [ ] Test empty state renders when `adapters` is empty or missing.
- [ ] Test mode summary section renders `mode`, `simulated`, `real_mode_enabled`,
      and `real_mode_status`.
- [ ] Test each adapter row renders adapter name and supported actions.
- [ ] Test simulation mode notice is visible in the populated state.
- [ ] Test no test-connection, run, or execute controls are rendered.
- [ ] Test component does not crash when `supported_actions` is empty for an adapter.
- [ ] Test component does not crash when `adapters` is null or undefined.

Verification:

```bash
npm test -- --watchAll=false frontend/src/components/IntegrationStatusPanel.test.js
```

## Step 6: Register Panel in App.js

File:

```text
frontend/src/App.js
```

- [ ] Add `import IntegrationStatusPanel from './components/IntegrationStatusPanel'`.
- [ ] Add the panel entry to the panel list following the same pattern used by
      `PlaybooksPanel`, `SoarQueuePanel`, `ApprovalsPanel`, and `IncidentsPanel`.
- [ ] Do not restructure layout, routing, or any other panel.
- [ ] Do not remove or reorder existing panels.

## Step 7: Run Nearby Regression Tests

Run the full suite of related panel tests to confirm no regressions:

```bash
npm test -- --watchAll=false frontend/src/components/PlaybooksPanel.test.js
npm test -- --watchAll=false frontend/src/components/SoarQueuePanel.test.js
npm test -- --watchAll=false frontend/src/components/ApprovalsPanel.test.js
npm test -- --watchAll=false frontend/src/components/IncidentsPanel.test.js
npm test -- --watchAll=false frontend/src/services/playbookService.test.js
npm test -- --watchAll=false frontend/src/services/approvalService.test.js
npm test -- --watchAll=false frontend/src/services/soarQueueService.test.js
```

Run build:

```bash
npm run build
```

## Step 8: Run Backend Non-Regression Tests

Confirm no backend files changed:

```bash
git status --short
python3 -m py_compile routes/integration_routes.py integrations/*.py
python3 -m pytest tests/test_integration_routes.py tests/test_integration_adapters.py -v
python3 -m pytest tests/test_playbook_step_executor.py tests/test_playbook_routes.py tests/test_soar_playbook_orchestrator.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
```

Expected: no backend files in `git status --short`. All backend tests pass.

## Stop and Rollback Conditions

- [ ] Stop if the service helper requires backend changes to work.
- [ ] Stop if `App.js` integration requires layout or routing restructuring.
- [ ] Stop if any mutation control is introduced anywhere in the panel.
- [ ] Stop if the simulation mode notice cannot be made persistently visible.
- [ ] Stop if `IntegrationStatusPanel` calls any endpoint other than
      `GET /integrations/status`.
- [ ] Stop if backend files appear in `git status --short` after implementation.
- [ ] Roll back `IntegrationStatusPanel` if its tests fail.
- [ ] Roll back `App.js` change if nearby panel regression tests fail.
- [ ] Roll back service helper if service tests fail.
