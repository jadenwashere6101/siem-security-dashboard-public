# Design: SOAR Playbook Definition UI

## Proposed Frontend Architecture

Extend the existing read-only frontend playbook visibility implementation rather than adding
a separate page. The current `PlaybooksPanel` already owns definitions, executions, filters,
details, and refresh behavior. This change should add a small definition-management layer to
that component while preserving analyst read-only behavior.

Recommended shape:

```text
frontend/src/services/playbookService.js
frontend/src/services/playbookService.test.js
frontend/src/components/PlaybooksPanel.js
frontend/src/components/PlaybooksPanel.test.js
frontend/src/App.js                  # only if userRole is not already passed
```

If the panel does not already receive `userRole`, pass it from `App.js` with the same minimal
style used by nearby panels such as approvals. Do not restructure navigation or section
rendering.

## Files Likely To Change

- `frontend/src/services/playbookService.js` — add mutation helpers for definition
  management.
- `frontend/src/services/playbookService.test.js` — add service tests for mutation helpers.
- `frontend/src/components/PlaybooksPanel.js` — add super-admin-only create/edit/toggle UI.
- `frontend/src/components/PlaybooksPanel.test.js` — add component tests.
- `frontend/src/App.js` — only to pass `userRole` into `PlaybooksPanel` if needed.

No backend, schema, ingest, detection, correlation, SOAR queue, approval, incident, adapter,
or executor files should change.

## API Service Changes

Extend `playbookService.js` with:

```javascript
createPlaybookDefinition(payload)
updatePlaybookDefinition(playbookId, payload)
setPlaybookDefinitionEnabled(playbookId, enabled)
```

Expected requests:

- `createPlaybookDefinition` calls `POST /playbooks`.
- `updatePlaybookDefinition` calls `PUT /playbooks/<id>`.
- `setPlaybookDefinitionEnabled` calls `PATCH /playbooks/<id>/enabled`.

All mutation helpers must:

- use `buildSiemPath`
- use `parseJsonResponse`
- use `getApiErrorMessage`
- include `credentials: "include"`
- send `Content-Type: application/json`
- return parsed response JSON
- throw safe errors for non-OK responses

Do not add service helpers for:

- executing playbooks
- creating playbook executions
- retrying executions
- cancelling executions
- enqueueing SOAR actions
- deleting definitions

## UI Behavior

### Super Admin

When `userRole === "super_admin"`, the Definitions section may show:

- `New Definition` button.
- `Edit` button per definition.
- Enable/disable control per definition.

Create/edit may use an inline panel or modal-like in-page form. Keep it consistent with the
existing dashboard style and avoid broad layout changes.

Form fields:

- ID: create-only, slug text input.
- Name: text input.
- Description: optional text input or textarea.
- Enabled: checkbox/toggle.
- Trigger config: JSON textarea.
- Steps: JSON textarea.

Recommended create defaults:

```json
{
  "trigger_config": {},
  "steps": [
    {
      "action": "monitor",
      "params": {},
      "on_failure": "abort"
    }
  ],
  "enabled": false
}
```

Use explicit copy that makes the scope clear, for example:

- "Definition management only"
- "Execution is not enabled"

Do not use labels such as "Run", "Execute", "Retry", "Dispatch", or "Start".

### Analyst

When `userRole === "analyst"`, preserve the current read-only experience:

- no create button
- no edit buttons
- no enable/disable controls
- no form
- read-only details and filters still work

### Viewer Or Unknown Role

Follow existing app gating. If viewers cannot access the Playbooks section today, do not add
new access. If the component is rendered for an unknown role in tests, default to read-only.

## Permission Behavior

Frontend role gating is usability and defense-in-depth only. Backend remains authoritative.

Expected frontend behavior:

- Super admin sees mutation controls.
- Analyst sees read-only visibility.
- Mutation errors from backend `401`/`403` are displayed safely.
- If session role changes while the panel is open, controls should disappear on re-render
  when `userRole` is no longer `super_admin`.

If `App.js` needs to pass `userRole` into `PlaybooksPanel`, make that the only App-level
change.

## Validation/Error Behavior

Validate before calling mutation service helpers.

ID:

- Required for create.
- Slug style: lowercase letters, digits, underscores, and hyphens.
- Do not allow editing ID in update mode.

Name:

- Required.
- Trim whitespace.

Description:

- Optional.
- Trim whitespace or send `null`/empty string consistently with backend expectations.

Trigger config:

- Must parse as JSON.
- Parsed value must be an object, not an array.
- Default `{}`.

Steps:

- Must parse as JSON.
- Parsed value must be an array.
- Do not attempt to fully duplicate backend registry validation in the UI. Lightweight
  validation may check that each step has an `action` string, but backend validation remains
  authoritative.

Enabled:

- Must be boolean.

Error handling:

- Show client-side validation errors without calling the API.
- Show backend validation/permission errors from service helpers.
- Keep form data intact after failed submissions.
- On success, close or reset the form, refresh definitions, and show concise success
  feedback.

## Safety Boundaries

- UI must not imply playbooks can execute yet.
- Do not add execution controls.
- Do not add run, retry, cancel, replay, approve, deny, expire, or enqueue controls.
- Do not create `playbook_executions`.
- Do not call `/playbook-executions` with a mutation method.
- Do not call SOAR queue, approval, incident, Slack, email, firewall, dry-run adapter, ingest,
  detection, or correlation endpoints.
- Do not alter existing SOAR queue, incident, or approval UI behavior.
- Keep `App.js` changes minimal or none.
- Preserve read-only execution record display.

## Test Strategy

### Service Tests

Mock `fetch` and verify:

- `createPlaybookDefinition` calls `POST /playbooks`.
- `updatePlaybookDefinition` calls `PUT /playbooks/<id>`.
- `setPlaybookDefinitionEnabled` calls `PATCH /playbooks/<id>/enabled`.
- Mutation helpers include credentials and JSON headers.
- Mutation helpers serialize expected JSON bodies.
- Non-OK mutation responses throw safe errors.
- No service helper calls execution, retry, cancel, queue, approval, incident, or adapter
  endpoints.

### Component Tests

Mock `playbookService` and render `PlaybooksPanel`.

Super admin:

- sees `New Definition`
- can open create form
- can submit valid create payload
- can open edit form with existing values
- can submit valid update payload
- can enable/disable a definition
- sees success/error feedback
- definitions refresh after successful mutation

Analyst:

- sees definitions and executions
- does not see create/edit/enable-disable controls
- cannot open mutation forms

Validation:

- invalid ID blocks create
- blank name blocks create/update
- invalid trigger JSON blocks submit
- array trigger JSON blocks submit
- invalid steps JSON blocks submit
- non-array steps JSON blocks submit
- validation failures do not call mutation service helpers

Safety:

- no run/retry/cancel/execute controls render
- execution records remain read-only
- existing refresh/view-detail behavior remains intact

### App Tests

Only if `App.js` changes:

- `PlaybooksPanel` receives `userRole`.
- existing Playbooks navigation still renders for intended roles.
- existing SOAR queue, incident, and approval navigation remains unchanged.

## Risks/Stop Conditions

- Stop if UI requires backend changes.
- Stop if implementation starts adding execution-like controls.
- Stop if analysts need mutation controls.
- Stop if service helpers need endpoints beyond the three definition-management endpoints.
- Stop if `App.js` changes grow beyond passing role props or a small local wiring update.
- Stop if SOAR queue, incident, approval, ingest, detection, correlation, adapter, or executor
  behavior would change.
- Stop if tests require creating playbook executions.
