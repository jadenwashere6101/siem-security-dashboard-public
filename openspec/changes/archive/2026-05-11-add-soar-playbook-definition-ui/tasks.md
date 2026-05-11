# Tasks: SOAR Playbook Definition UI

Implement later in small frontend-only steps. Do not implement as part of this spec-only
change.

## Step 1: Reconfirm Existing UI Patterns

- [ ] Read `frontend/src/components/PlaybooksPanel.js`.
- [ ] Read `frontend/src/services/playbookService.js`.
- [ ] Read `frontend/src/components/PlaybooksPanel.test.js`.
- [ ] Read nearby mutation UI patterns such as `ApprovalsPanel.js` and
      `DetectionRulesPanel.js`.
- [ ] Confirm whether `PlaybooksPanel` already receives `userRole`.
- [ ] Confirm analysts currently have read-only Playbooks access.

Stop if frontend role gating is unclear.

## Step 2: Add Service Mutation Helpers

File:

```text
frontend/src/services/playbookService.js
```

- [ ] Add `createPlaybookDefinition(payload)`.
- [ ] Add `updatePlaybookDefinition(playbookId, payload)`.
- [ ] Add `setPlaybookDefinitionEnabled(playbookId, enabled)`.
- [ ] Use `buildSiemPath`.
- [ ] Use `parseJsonResponse`.
- [ ] Use `getApiErrorMessage`.
- [ ] Use `credentials: "include"`.
- [ ] Send `Content-Type: application/json`.
- [ ] Call only `POST /playbooks`, `PUT /playbooks/<id>`, and
      `PATCH /playbooks/<id>/enabled`.
- [ ] Do not add helpers for execution, retry, cancel, queue enqueueing, approvals,
      incidents, integrations, or deletion.

## Step 3: Add Service Tests

File:

```text
frontend/src/services/playbookService.test.js
```

Cover:

- [ ] `createPlaybookDefinition` sends `POST /playbooks`.
- [ ] `createPlaybookDefinition` sends the expected JSON body.
- [ ] `updatePlaybookDefinition` sends `PUT /playbooks/<id>`.
- [ ] `updatePlaybookDefinition` URL-encodes the ID.
- [ ] `setPlaybookDefinitionEnabled` sends `PATCH /playbooks/<id>/enabled`.
- [ ] `setPlaybookDefinitionEnabled` sends `{ "enabled": true }` or `{ "enabled": false }`.
- [ ] All mutation helpers include credentials.
- [ ] All mutation helpers include JSON content type.
- [ ] Non-OK responses throw useful errors.
- [ ] No helper uses playbook execution mutation, SOAR queue, approval, incident, or
      integration endpoints.

Verification:

```bash
npm test -- --watchAll=false frontend/src/services/playbookService.test.js
```

## Step 4: Pass User Role If Needed

File:

```text
frontend/src/App.js
```

- [ ] Pass `userRole` into `PlaybooksPanel` only if it is not already available.
- [ ] Do not change Playbooks navigation gating unless required by existing role policy.
- [ ] Do not change SOAR queue, incident, approval, dashboard, blocklist, threat hunt, or
      admin navigation behavior.

If this file changes, keep the diff limited to the prop wiring.

## Step 5: Add Form State And Validation

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Add create/edit form state.
- [ ] Add submit/loading/error/success state for definition mutations.
- [ ] Add JSON textarea state for `trigger_config`.
- [ ] Add JSON textarea state for `steps`.
- [ ] Validate create ID is present and slug-like.
- [ ] Validate ID is not editable in edit mode.
- [ ] Validate name is non-empty.
- [ ] Validate trigger JSON parses to an object.
- [ ] Validate steps JSON parses to an array.
- [ ] Validate enabled is boolean.
- [ ] Preserve form values after validation or backend errors.
- [ ] Do not call mutation services when client-side validation fails.

## Step 6: Add Super-Admin Controls

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Show `New Definition` only when `userRole === "super_admin"`.
- [ ] Show `Edit` only when `userRole === "super_admin"`.
- [ ] Show enable/disable controls only when `userRole === "super_admin"`.
- [ ] Label controls as definition management only.
- [ ] Include visible copy that execution is not enabled.
- [ ] On successful create, refresh definitions.
- [ ] On successful update, refresh definitions and selected detail if needed.
- [ ] On successful enable/disable, refresh definitions and selected detail if needed.
- [ ] Keep execution records read-only.
- [ ] Do not add run/retry/cancel/execute controls.

## Step 7: Preserve Analyst Read-Only Behavior

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Default non-super-admin users to read-only.
- [ ] Analysts can still view definitions.
- [ ] Analysts can still view executions.
- [ ] Analysts can still use filters and refresh.
- [ ] Analysts cannot see or trigger create/edit/enable-disable controls.
- [ ] Unknown roles do not see mutation controls.

## Step 8: Add Component Tests For Super Admin

File:

```text
frontend/src/components/PlaybooksPanel.test.js
```

Cover:

- [ ] Super admin sees `New Definition`.
- [ ] Super admin opens create form.
- [ ] Valid create calls `createPlaybookDefinition` with parsed JSON.
- [ ] Super admin opens edit form for an existing definition.
- [ ] Valid edit calls `updatePlaybookDefinition`.
- [ ] Enable control calls `setPlaybookDefinitionEnabled(id, true)`.
- [ ] Disable control calls `setPlaybookDefinitionEnabled(id, false)`.
- [ ] Successful mutation refreshes definitions.
- [ ] Backend mutation error is shown safely.

## Step 9: Add Component Tests For Analyst Read-Only Mode

Cover:

- [ ] Analyst sees definitions.
- [ ] Analyst sees executions.
- [ ] Analyst does not see `New Definition`.
- [ ] Analyst does not see `Edit`.
- [ ] Analyst does not see enable/disable controls.
- [ ] Analyst can still view definition details.
- [ ] Analyst can still view execution details.
- [ ] Analyst refresh still uses read-only service calls.

## Step 10: Add Validation And Safety Tests

Cover:

- [ ] Invalid create ID shows validation error.
- [ ] Blank name shows validation error.
- [ ] Invalid trigger JSON shows validation error.
- [ ] Trigger JSON array shows validation error.
- [ ] Invalid steps JSON shows validation error.
- [ ] Steps JSON object shows validation error.
- [ ] Validation failures do not call mutation service helpers.
- [ ] No run/retry/cancel/execute buttons render.
- [ ] No test path creates playbook executions.
- [ ] No mutation control appears in the Executions section.

## Frontend Verification

Run focused tests:

```bash
npm test -- --watchAll=false frontend/src/services/playbookService.test.js
npm test -- --watchAll=false frontend/src/components/PlaybooksPanel.test.js
```

If `App.js` changes, also run:

```bash
npm test -- --watchAll=false frontend/src/App.test.js
```

Run nearby frontend regressions:

```bash
npm test -- --watchAll=false frontend/src/services/soarQueueService.test.js
npm test -- --watchAll=false frontend/src/components/SoarQueuePanel.test.js
npm test -- --watchAll=false frontend/src/services/approvalService.test.js
npm test -- --watchAll=false frontend/src/components/ApprovalsPanel.test.js
npm test -- --watchAll=false frontend/src/services/incidentService.test.js
npm test -- --watchAll=false frontend/src/components/IncidentsPanel.test.js
```

Run build:

```bash
npm run build
```

## Stop/Rollback Conditions

- [ ] Stop if implementation requires backend changes.
- [ ] Stop if implementation requires schema changes.
- [ ] Stop if implementation adds playbook execution controls.
- [ ] Stop if implementation creates or mutates `playbook_executions`.
- [ ] Stop if analysts gain mutation controls.
- [ ] Stop if service helpers call endpoints other than the three definition-management
      endpoints.
- [ ] Stop if `App.js` changes become broader than minimal role prop wiring.
- [ ] Stop if SOAR queue, incident, approval, ingest, detection, correlation, adapter, or
      executor behavior changes.
- [ ] Roll back the current implementation step if focused Playbooks tests fail.
- [ ] Roll back the current implementation step if nearby SOAR UI tests regress.
