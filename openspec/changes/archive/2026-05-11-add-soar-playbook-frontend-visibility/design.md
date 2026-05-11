# Design: SOAR Playbook Frontend Visibility

## Proposed Frontend Architecture

Add a small, modular frontend visibility surface for SOAR playbooks. The preferred shape is:

```text
frontend/src/services/playbookService.js
frontend/src/services/playbookService.test.js
frontend/src/components/PlaybooksPanel.js
frontend/src/components/PlaybooksPanel.test.js
```

The panel should follow existing dashboard patterns used by `SoarQueuePanel`,
`IncidentsPanel`, and `ApprovalsPanel`: local component state, service-layer fetch helpers,
shared timestamp formatting, consistent card/header/filter styles passed from `App.js`, and
React Testing Library tests.

If navigation is added, keep it surgical:

- import the new panel in `frontend/src/App.js`
- add one tab only if it matches the existing section navigation pattern
- render the panel only for the same role level chosen by the backend read APIs

Do not broadly refactor `App.js` or shared dashboard layout.

## Files Likely To Change

- `frontend/src/services/playbookService.js` — read-only API helpers.
- `frontend/src/services/playbookService.test.js` — service tests for paths, query params,
  credentials, and error handling.
- `frontend/src/components/PlaybooksPanel.js` — read-only definitions/executions UI.
- `frontend/src/components/PlaybooksPanel.test.js` — component tests.
- `frontend/src/App.js` — only if adding a dashboard navigation entry and panel render.

No backend, schema, ingest, detection, correlation, SOAR queue, approval, incident, adapter,
or execution files should change.

## API Calls

Service functions should use existing frontend utilities:

- `buildSiemPath`
- `parseJsonResponse`
- `getApiErrorMessage`
- `credentials: "include"`

Proposed service functions:

```javascript
listPlaybooks({ enabled, limit } = {})
getPlaybook(playbookId)
listPlaybookExecutions({ playbookId, status, limit } = {})
getPlaybookExecution(executionId)
```

Allowed HTTP methods:

- `GET` only.

Required endpoints:

- `GET /playbooks`
- `GET /playbooks/<id>`
- `GET /playbook-executions`
- `GET /playbook-executions/<id>`

The service must not define helper functions for playbook creation, updates, deletion,
execution, retry, cancel, queue enqueueing, or approval decisions.

## UI Behavior

The first implementation should prioritize inspection over workflow controls.

Recommended layout:

- One `PlaybooksPanel` with two internal tabs or sections:
  - Definitions
  - Executions
- Definitions section:
  - table or compact list of ID, name, enabled state, trigger summary, step count,
    created/updated timestamps
  - optional enabled filter: all/enabled/disabled
  - view detail action that opens a read-only detail panel
- Executions section:
  - table of execution ID, playbook ID, status, alert ID, incident ID, last completed step,
    created/started/completed timestamps
  - status filter using known values: `pending`, `running`, `success`, `failed`, `abandoned`
  - optional playbook ID filter if the UI can keep it clear
  - view detail action that opens a read-only detail panel

Detail panels may show formatted JSON for:

- `trigger_config`
- `steps`
- `steps_log`

Use a readable preformatted block or compact key/value rows. The detail view must not include
editable text areas, save buttons, run buttons, retry buttons, cancel buttons, or approval
buttons.

## Loading/Error/Empty States

Definitions:

- Initial loading: show a compact loading state.
- Refreshing: preserve current rows and indicate refresh in progress.
- Error: show safe error text from the service layer.
- Empty unfiltered state: no playbook definitions found.
- Empty filtered state: no playbook definitions match this filter.

Executions:

- Initial loading: show a compact loading state.
- Refreshing: preserve current rows and indicate refresh in progress.
- Error: show safe error text from the service layer.
- Empty unfiltered state: no playbook execution records found.
- Empty filtered state: no playbook execution records match this filter.

Detail:

- Loading detail: show detail loading state.
- Missing or failed detail load: show a safe error message.
- Close detail: clears selected record state only.

## Safety Boundaries

- Frontend is read-only.
- Do not add buttons that imply execution.
- Do not call POST, PUT, PATCH, or DELETE endpoints.
- Do not add create, edit, delete, run, retry, cancel, approve, deny, or expire controls.
- Do not alter existing SOAR queue, incident, or approval UI behavior.
- Do not refactor `App.js` broadly.
- Do not create playbook executions from frontend actions.
- Do not poll aggressively; use explicit refresh or the same restrained pattern as nearby
  panels if needed.
- Do not expose raw stack traces or unbounded JSON in a way that breaks layout.

## Test Strategy

Service tests should mock `fetch` and verify:

- `listPlaybooks` calls `GET /playbooks` with credentials.
- `listPlaybooks` includes `enabled` and `limit` query params only when appropriate.
- `getPlaybook` calls `GET /playbooks/<id>`.
- `listPlaybookExecutions` calls `GET /playbook-executions` with filters.
- `getPlaybookExecution` calls `GET /playbook-executions/<id>`.
- Non-OK responses throw useful errors.
- No service helper uses non-GET methods.

Component tests should mock the service module and verify:

- Definitions render after load.
- Executions render after load.
- Loading states render.
- Error states render.
- Empty states render.
- Filter changes call the correct service with expected params.
- Detail selection calls the appropriate detail service and renders read-only content.
- No run/retry/cancel/create/edit/delete controls are present.
- Refresh reloads data without mutating or submitting anything.

If `App.js` navigation is changed, add or update tests to verify:

- the navigation entry appears only for the intended role
- selecting it renders `PlaybooksPanel`
- existing SOAR queue, incident, approval, and dashboard sections still render as before

## Risks/Stop Conditions

- Stop if the UI requires backend changes to satisfy the first visibility goal.
- Stop if the design starts adding controls that imply execution or mutation.
- Stop if navigation changes require a broad `App.js` refactor.
- Stop if role visibility is unclear relative to backend permissions.
- Stop if adding playbook visibility changes SOAR queue, incident, approval, or alert table
  behavior.
- Stop if tests require mocking or changing ingest, detection, correlation, executor, or
  adapter behavior.
