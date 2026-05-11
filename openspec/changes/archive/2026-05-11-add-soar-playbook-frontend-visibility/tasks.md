# Tasks: SOAR Playbook Frontend Visibility

Implement later in small, read-only steps. Do not implement as part of this spec-only
change.

## Step 1: Read Existing Frontend Patterns

- [ ] Read `frontend/src/components/SoarQueuePanel.js`.
- [ ] Read `frontend/src/components/IncidentsPanel.js`.
- [ ] Read `frontend/src/components/ApprovalsPanel.js`.
- [ ] Read `frontend/src/services/soarQueueService.js`.
- [ ] Read `frontend/src/services/incidentService.js` and `frontend/src/services/approvalService.js`.
- [ ] Read the matching component and service tests.
- [ ] Confirm where a playbook visibility entry belongs in `App.js`, if any.

Stop if the role or navigation placement is unclear.

## Step 2: Add Read-Only Service Functions

File:

```text
frontend/src/services/playbookService.js
```

- [ ] Add `listPlaybooks({ enabled, limit } = {})`.
- [ ] Add `getPlaybook(playbookId)`.
- [ ] Add `listPlaybookExecutions({ playbookId, status, limit } = {})`.
- [ ] Add `getPlaybookExecution(executionId)`.
- [ ] Use `buildSiemPath`.
- [ ] Use `parseJsonResponse`.
- [ ] Use `getApiErrorMessage`.
- [ ] Use `credentials: "include"`.
- [ ] Use only `GET` requests.
- [ ] Do not add create/update/delete/run/retry/cancel helpers.

Verification:

```bash
npm test -- --watchAll=false frontend/src/services/playbookService.test.js
```

## Step 3: Add Service Tests

File:

```text
frontend/src/services/playbookService.test.js
```

Cover:

- [ ] `listPlaybooks` calls `/playbooks` with credentials.
- [ ] `listPlaybooks` sends `enabled` and `limit` query params correctly.
- [ ] `getPlaybook` calls `/playbooks/<id>`.
- [ ] `listPlaybookExecutions` calls `/playbook-executions`.
- [ ] `listPlaybookExecutions` sends `playbook_id`, `status`, and `limit` query params correctly.
- [ ] `getPlaybookExecution` calls `/playbook-executions/<id>`.
- [ ] Each function throws a useful error on non-OK responses.
- [ ] No tested request uses `POST`, `PUT`, `PATCH`, or `DELETE`.

## Step 4: Add Playbooks Panel Component

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Render a read-only panel following existing dashboard card/header patterns.
- [ ] Load definitions and executions through `playbookService`.
- [ ] Show a definitions section with ID, name, enabled state, trigger summary, step count,
      and timestamps.
- [ ] Show an executions section with execution ID, playbook ID, status, alert ID,
      incident ID, last completed step, and timestamps.
- [ ] Add filter controls only for read API query params.
- [ ] Add refresh controls that only re-run GET requests.
- [ ] Add optional read-only detail panels for definitions and executions.
- [ ] Show `trigger_config`, `steps`, and `steps_log` as read-only content.
- [ ] Include loading, refreshing, error, and empty states.
- [ ] Do not add buttons or controls for create, edit, delete, run, retry, cancel, approve,
      deny, expire, or enqueue.

Verification:

```bash
npm test -- --watchAll=false frontend/src/components/PlaybooksPanel.test.js
```

## Step 5: Add Component Tests

File:

```text
frontend/src/components/PlaybooksPanel.test.js
```

Cover:

- [ ] Initial loading state.
- [ ] Definitions render after successful load.
- [ ] Executions render after successful load.
- [ ] Definition empty state.
- [ ] Execution empty state.
- [ ] Definition load error.
- [ ] Execution load error.
- [ ] Enabled filter calls `listPlaybooks` with expected params.
- [ ] Execution status filter calls `listPlaybookExecutions` with expected params.
- [ ] Detail selection calls `getPlaybook` or `getPlaybookExecution`.
- [ ] Detail panel renders JSON fields read-only.
- [ ] Refresh calls only read service functions.
- [ ] No run/retry/cancel/create/edit/delete controls are rendered.

## Step 6: Add Navigation Entry If Consistent

File:

```text
frontend/src/App.js
```

- [ ] Import `PlaybooksPanel`.
- [ ] Add a single navigation tab only if consistent with existing dashboard section patterns.
- [ ] Gate the tab with the same role expectation as the backend read APIs.
- [ ] Render `PlaybooksPanel` with existing shared style props.
- [ ] Do not refactor unrelated navigation or section rendering.
- [ ] Do not alter existing SOAR queue, incident, approval, dashboard, blocklist, threat hunt,
      or admin behavior.

If adding navigation is not consistent with current patterns, keep `PlaybooksPanel` ready for
future integration and document the decision in the implementation notes.

## Step 7: Add Navigation Tests If App.js Changes

Update the relevant app tests only if navigation is added.

Cover:

- [ ] Intended role can see the Playbooks navigation entry.
- [ ] Unauthorized role cannot see the entry if role-gated.
- [ ] Clicking the entry renders `PlaybooksPanel`.
- [ ] Existing SOAR Queue navigation still works.
- [ ] Existing SOAR Incidents navigation still works.
- [ ] Existing SOAR Approvals navigation still works.

## Frontend Verification

Run the focused tests:

```bash
npm test -- --watchAll=false frontend/src/services/playbookService.test.js
npm test -- --watchAll=false frontend/src/components/PlaybooksPanel.test.js
```

If `App.js` changes, also run:

```bash
npm test -- --watchAll=false frontend/src/App.test.js
```

Run the existing nearby regression tests:

```bash
npm test -- --watchAll=false frontend/src/services/soarQueueService.test.js
npm test -- --watchAll=false frontend/src/components/SoarQueuePanel.test.js
npm test -- --watchAll=false frontend/src/services/approvalService.test.js
npm test -- --watchAll=false frontend/src/components/ApprovalsPanel.test.js
npm test -- --watchAll=false frontend/src/services/incidentService.test.js
npm test -- --watchAll=false frontend/src/components/IncidentsPanel.test.js
```

Run a production build:

```bash
npm run build
```

## Stop/Rollback Conditions

- [ ] Stop if implementation requires backend changes.
- [ ] Stop if implementation requires schema changes.
- [ ] Stop if implementation starts adding playbook mutation or execution controls.
- [ ] Stop if any service function needs POST, PUT, PATCH, or DELETE.
- [ ] Stop if `App.js` requires a broad refactor.
- [ ] Stop if SOAR queue, incident, approval, ingest, detection, correlation, adapter, or
      executor behavior would change.
- [ ] Roll back the current implementation step if focused frontend tests fail.
- [ ] Roll back the current implementation step if existing SOAR queue, approval, incident,
      or app navigation tests regress.
