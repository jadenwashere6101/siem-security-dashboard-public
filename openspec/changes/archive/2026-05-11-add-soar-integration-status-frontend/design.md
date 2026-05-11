# Design: SOAR Integration Adapter Status Frontend

## Proposed architecture

Add a small frontend service function that calls the existing read-only `GET /integrations/status`
endpoint, and a new `IntegrationStatusPanel` component that renders the result. The panel
follows the same read-only visibility pattern used by `SoarQueuePanel`, `ApprovalsPanel`,
and `PlaybooksPanel`.

No backend, schema, executor, or queue code changes are required. The backend endpoint
already exists and is stable.

## API being consumed

```http
GET /integrations/status
```

Expected response shape (already implemented):

```json
{
  "mode": "simulation",
  "simulated": true,
  "real_mode_enabled": false,
  "real_mode_status": "disabled",
  "adapters": [
    {
      "name": "slack",
      "mode": "simulation",
      "simulated": true,
      "real_client": false,
      "supported_actions": ["send_message"]
    },
    {
      "name": "email",
      "mode": "simulation",
      "simulated": true,
      "real_client": false,
      "supported_actions": ["send_email"]
    },
    {
      "name": "firewall",
      "mode": "simulation",
      "simulated": true,
      "real_client": false,
      "supported_actions": ["block_ip"]
    },
    {
      "name": "webhook",
      "mode": "simulation",
      "simulated": true,
      "real_client": false,
      "supported_actions": ["post_event"]
    }
  ]
}
```

## Files to create or modify

**New files:**

- `frontend/src/services/integrationService.js` — exports `getIntegrationStatus()` which
  calls `GET /integrations/status` using the existing fetch/auth helper pattern.
- `frontend/src/components/IntegrationStatusPanel.js` — read-only panel component.
- `frontend/src/services/integrationService.test.js` — service layer tests.
- `frontend/src/components/IntegrationStatusPanel.test.js` — component render tests.

**Modified files:**

- `frontend/src/App.js` — add `IntegrationStatusPanel` to the panel layout in the same
  way other SOAR panels are registered. Only modify the panel list and imports; do not
  restructure layout or routing.

No backend files, schema files, executor files, queue files, or other frontend files
should change.

## Service helper design

`integrationService.js` should export a single named function:

```js
export async function getIntegrationStatus() { ... }
```

It should use the same fetch wrapper and auth token pattern already used by
`playbookService.js`, `approvalService.js`, and `soarQueueService.js`. It should not
add retry logic, polling, or background refresh. It returns the parsed JSON response or
throws on non-OK status.

## Component design

`IntegrationStatusPanel` should:

- Call `getIntegrationStatus()` on mount with a `useEffect` following the same pattern
  used in other panels.
- Display a loading state while the request is in flight.
- Display a user-friendly error message if the request fails, consistent with error
  rendering in other panels.
- Display an empty state if the `adapters` array is missing or empty.
- Render a top-level mode summary section showing:
  - `mode` value (always `"simulation"` in current implementation)
  - `simulated: true` clearly labeled
  - `real_mode_enabled: false` clearly labeled as "Real mode disabled"
  - `real_mode_status` value
- Render one row or card per adapter with:
  - Adapter name
  - Mode badge
  - Simulated flag
  - Supported actions as a readable list or inline tags
- Include a visible note at the top or bottom of the panel stating that all adapters
  are running in simulation mode and no real integrations are active. This note must
  never be hidden or conditionally suppressed.

The panel must not render any of the following under any condition:
- Test connection buttons
- Run adapter buttons
- Execute action controls
- Any form input
- Any mutation trigger of any kind

## Auth and role expectations

- Follow the same auth header pattern as other frontend service files.
- The backend already restricts `GET /integrations/status` to analyst and super-admin
  roles and returns an unauthorized response shape for unauthenticated requests.
- The frontend panel does not need to implement role-gating logic independently; the
  backend enforces access.
- If the API returns a 401 or 403, render the same error state used for other panels.

## Loading, error, and empty state behavior

| State          | Trigger                                         | Render                                               |
|----------------|-------------------------------------------------|------------------------------------------------------|
| Loading        | Request in flight                               | Consistent loading indicator matching other panels   |
| Error          | Non-OK response or network failure              | Error message, no adapter rows                       |
| Empty          | `adapters` array is missing, null, or length 0  | "No integration adapters registered." or equivalent |
| Populated      | `adapters` array has one or more entries        | Mode summary + per-adapter rows                      |

## Safety boundaries

- Panel is read-only with no mutation controls.
- No test-connection calls are made from the frontend.
- The simulation mode notice must always be visible when the panel is populated.
- The panel must never render a state that implies real integrations are active.
- No executor, queue, approval, playbook, ingest, detection, or correlation paths are
  invoked or referenced.

## Failure behavior

- API failure renders an error state without crashing the panel or other panels.
- Unexpected or missing fields in the response (e.g., no `adapters` key) render the
  empty state rather than throwing a JS error. Field access should be defensive.
- An adapter with no `supported_actions` renders with an empty actions list rather
  than crashing.

## Test strategy

**Service tests (`integrationService.test.js`):**

- `getIntegrationStatus()` calls `GET /integrations/status`.
- `getIntegrationStatus()` returns parsed JSON on success.
- `getIntegrationStatus()` throws on non-OK response.

**Component tests (`IntegrationStatusPanel.test.js`):**

- Loading state is rendered while the request is in flight.
- Error state is rendered on API failure.
- Empty state is rendered when `adapters` is empty or missing.
- Mode summary section renders `mode`, `simulated`, `real_mode_enabled`, and
  `real_mode_status` from the response.
- Each adapter renders its name and supported actions.
- The simulation mode notice is always visible in the populated state.
- No test-connection, run, execute, or mutation controls are rendered.
- The component does not crash when `supported_actions` is missing or empty for an adapter.
- The component does not crash when `adapters` is null or undefined.
- Existing panels (`PlaybooksPanel`, `SoarQueuePanel`, `ApprovalsPanel`, `IncidentsPanel`)
  are not rendered or affected by these tests.

## Risks and stop conditions

- Stop if the frontend service helper requires backend changes to work.
- Stop if `App.js` integration requires layout or routing restructuring beyond adding
  a panel entry and import.
- Stop if the panel cannot clearly label simulation mode without backend changes.
- Stop if any adapter field access pattern could unintentionally suggest real execution
  is possible.
- Stop if rendering requires calling any endpoint other than `GET /integrations/status`.
