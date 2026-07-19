## ADDED Requirements

### Requirement: AI actions are restricted to a fixed allowlist
The system SHALL accept only the Phase 5 AI action allowlist and SHALL reject unsupported, free-form, route-specified, shell/file, provider-config, SOAR execution, approval-decision, registry-command, or autonomous action requests before any mutation helper is called.

#### Scenario: Supported action types are accepted for validation
- **WHEN** an authenticated user requests preview for `add_alert_note`, `add_incident_note`, `change_incident_status`, `create_playbook_draft`, `update_detection_rule_parameters`, or `create_incident_from_alert`
- **THEN** the system validates the request against that action type's canonical schema

#### Scenario: Unsupported action type is rejected
- **WHEN** a request names an action type outside the Phase 5 allowlist
- **THEN** the system returns a safe validation error and does not call context builders, mutation helpers, provider inference, shell/file access, or direct database write paths

#### Scenario: Client cannot select arbitrary backend route
- **WHEN** a request includes a route, URL, function name, SQL, shell command, or arbitrary operation field
- **THEN** the system ignores or rejects that field and uses only the canonical allowlist mapping

### Requirement: Per-action schemas are centralized and bounded
The system SHALL define action schemas, required fields, optional fields, field limits, target resource rules, role requirements, idempotency policy, and dispatch mapping in one backend location under `core/ai`.

#### Scenario: Alert note payload is bounded
- **WHEN** an `add_alert_note` action is previewed or confirmed
- **THEN** the payload requires an existing `alert_id` and non-empty `note_text` within the existing alert note length limit

#### Scenario: Incident note payload requires a real note path
- **WHEN** an `add_incident_note` action is implemented
- **THEN** it uses a real incident note API/helper with bounded note text and does not store the note in unrelated incident fields

#### Scenario: Incident status payload uses existing status vocabulary
- **WHEN** a `change_incident_status` action is previewed or confirmed
- **THEN** the payload requires an existing `incident_id` and a status from the existing incident status set

#### Scenario: Playbook draft payload is disabled by default
- **WHEN** a `create_playbook_draft` action is confirmed
- **THEN** the created playbook definition is disabled unless a later OpenSpec explicitly allows AI-assisted enablement

#### Scenario: Detection rule update is bounded to parameters
- **WHEN** an `update_detection_rule_parameters` action is previewed or confirmed
- **THEN** the payload targets an existing detection rule and includes only bounded parameter changes validated by the existing detection rule configuration validator

#### Scenario: Incident creation uses alert source data
- **WHEN** a `create_incident_from_alert` action is previewed or confirmed
- **THEN** the payload requires an existing alert id and uses existing alert/incident policy data rather than AI-supplied severity or source-IP values as authority

### Requirement: Preview never mutates production
The system SHALL provide an AI action preview operation that validates target, payload, RBAC, stale-source state, idempotency metadata, and dispatch plan without creating, updating, deleting, approving, executing, or persisting production state.

#### Scenario: Preview returns exact payload and confirmation requirement
- **WHEN** a valid preview request is submitted
- **THEN** the response includes action type, target resource keys, exact normalized payload, required role, existing dispatch path/helper, idempotency key, confirmation token, `requires_confirmation=true`, and no production mutation result

#### Scenario: Preview cancellation has no mutation
- **WHEN** an analyst cancels or dismisses an action preview
- **THEN** no target API, mutation helper, approval decision, SOAR execution, database write, or audit event for confirmed execution is called

#### Scenario: Preview failure has no partial mutation
- **WHEN** preview validation fails because context is missing, stale, unauthorized, unsupported, malformed, or insufficient
- **THEN** the system returns a safe error and no production mutation is attempted

### Requirement: Confirmation is explicit and revalidated
The system SHALL execute an AI action only after explicit user confirmation and SHALL revalidate the action type, payload digest, target state, RBAC, confirmation token, and idempotency key immediately before dispatch.

#### Scenario: Missing confirmation is rejected
- **WHEN** a confirm request omits explicit confirmation, confirmation token, idempotency key, or matching payload digest
- **THEN** the system rejects the request before dispatch and reports that no production change was made

#### Scenario: Stale preview is rejected
- **WHEN** target state changed after preview in a way that invalidates the payload or target fingerprint
- **THEN** confirmation returns `stale_source` and does not call the mapped mutation helper

#### Scenario: Confirm dispatch uses existing path
- **WHEN** a confirmed action passes all validation
- **THEN** the system dispatches only to the action's mapped existing API/service helper and returns the helper result mapped into the AI action outcome contract

#### Scenario: User rejection is no-mutation
- **WHEN** the user rejects the preview or closes the confirmation flow without confirming
- **THEN** the system records only client UI state if needed and does not mutate production

### Requirement: RBAC is enforced per action
The system SHALL enforce existing authentication and role boundaries for every preview and confirm request, with super-admin-only actions remaining super-admin-only.

#### Scenario: Analyst can preview analyst-level actions
- **WHEN** an analyst previews `add_alert_note`, `add_incident_note`, `change_incident_status`, or `create_incident_from_alert`
- **THEN** the request is allowed to proceed to schema and target validation

#### Scenario: Analyst cannot execute super-admin action
- **WHEN** an analyst previews or confirms `create_playbook_draft` or `update_detection_rule_parameters`
- **THEN** the system returns forbidden before action dispatch

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated user calls an AI action preview or confirm endpoint
- **THEN** existing authentication behavior rejects the request before validation, provider calls, or mutation helper calls

### Requirement: Existing mutation paths remain source of truth
The system SHALL reuse existing validated service/API paths for action execution and SHALL NOT introduce parallel write logic for alerts, incidents, playbooks, detection rules, approvals, response registry records, SOAR actions, or integrations.

#### Scenario: Alert note uses alert note path
- **WHEN** `add_alert_note` is confirmed
- **THEN** the system uses the same validation and persistence behavior as the existing alert note creation path

#### Scenario: Incident status uses incident store transition logic
- **WHEN** `change_incident_status` is confirmed
- **THEN** the system uses existing incident status validation and update behavior

#### Scenario: Playbook draft uses playbook definition validators
- **WHEN** `create_playbook_draft` is confirmed
- **THEN** the system uses existing playbook definition validation and persistence helpers and does not create a playbook execution

#### Scenario: Detection rule update uses admin validator
- **WHEN** `update_detection_rule_parameters` is confirmed
- **THEN** the system uses existing detection rule validation semantics and audit-compatible update behavior

#### Scenario: Incident creation reuses incident policy
- **WHEN** `create_incident_from_alert` is confirmed
- **THEN** the system reuses existing incident creation/linking policy for alerts and does not rely on AI-generated severity, source IP, or title as the source of truth

### Requirement: Idempotency prevents duplicate confirmed actions
The system SHALL require idempotency for every confirmed AI action and SHALL prevent duplicate submissions from creating duplicate production effects.

#### Scenario: Duplicate confirmation is suppressed or replayed safely
- **WHEN** the same idempotency key and payload digest are submitted more than once
- **THEN** the system returns the original safe outcome when available or `duplicate_suppressed` without repeating the mutation

#### Scenario: Idempotency mismatch is rejected
- **WHEN** an idempotency key is reused with a different action type, target, or payload digest
- **THEN** the system rejects the request before dispatch

### Requirement: Audit logs are written for confirmed actions
The system SHALL write safe audit metadata for confirmed AI actions and SHALL preserve existing action-specific audit events where those paths already emit them.

#### Scenario: Confirmed action writes AI audit event
- **WHEN** an AI action is confirmed and dispatch is attempted
- **THEN** the audit log records actor, role, action type, target resource keys, source draft metadata, dispatch path, idempotency key, outcome status, and safe error code if applicable

#### Scenario: Audit excludes sensitive content
- **WHEN** an AI action includes note text, playbook steps, detection parameters, source evidence, model output, or provider metadata
- **THEN** audit logs do not contain raw prompt text, raw draft bodies, credentials, secrets, long note bodies, full playbook steps, or raw provider responses

#### Scenario: Rejected preview is not logged as execution
- **WHEN** an action preview is rejected, cancelled, or not confirmed
- **THEN** the system does not write an audit event implying production execution occurred

### Requirement: Outcomes distinguish actual effects
The system SHALL map confirmed action results into explicit outcome categories that distinguish real, simulated, tracking-only, pending, failed, unknown, duplicate, cancelled, and rejected states.

#### Scenario: Successful production mutation is real
- **WHEN** a mapped helper confirms that production state changed
- **THEN** the AI action response reports outcome `real` with target resource identifiers and the updated state summary

#### Scenario: Pending result is not reported as complete
- **WHEN** a mapped helper creates pending work rather than completing a production change
- **THEN** the AI action response reports outcome `pending` and identifies the pending record

#### Scenario: Failed or unknown dispatch is explicit
- **WHEN** dispatch fails or cannot prove whether mutation occurred
- **THEN** the AI action response reports `failed` or `unknown` and does not claim success

#### Scenario: Cancelled and rejected are no-mutation states
- **WHEN** an analyst cancels or rejects an AI action
- **THEN** the UI and API state report no production change made

### Requirement: Frontend shows safe action review and confirmation
The frontend SHALL present AI action previews with exact payloads, target resources, role requirements, stale-source state, confirmation controls, cancellation controls, loading/error states, and outcome results before and after confirmation.

#### Scenario: Preview displays exact payload
- **WHEN** the frontend receives a valid AI action preview
- **THEN** it displays the normalized payload that will be submitted on confirm, the target resources, and the mapped action type

#### Scenario: Confirm is gated by explicit user action
- **WHEN** an AI action preview is visible
- **THEN** the final confirm control remains unavailable until the user explicitly acknowledges the payload and confirmation requirement

#### Scenario: Stale preview disables confirmation
- **WHEN** preview state is stale because context or target selection changed
- **THEN** the frontend disables confirmation and instructs the analyst to regenerate the preview

#### Scenario: Result state is visible
- **WHEN** confirmation completes
- **THEN** the frontend shows the outcome category, target identifiers, success/failure message, and whether the result was real, pending, duplicate, failed, or unknown

### Requirement: AI action flow remains separate from draft generation and read tools
The system SHALL keep draft generation, read-only SOC tools, action preview, and action confirmation as separate phases with separate contracts.

#### Scenario: Draft generation does not preview or execute action
- **WHEN** `POST /ai/drafts` returns a draft
- **THEN** no AI action preview or confirm request is automatically created or executed

#### Scenario: Read tools remain read-only
- **WHEN** a Phase 3 read tool result is used as source evidence for a later AI action preview
- **THEN** the read tool itself does not mutate state and is not treated as confirmation

#### Scenario: Provider receives no mutation capability
- **WHEN** an AI action is previewed or confirmed
- **THEN** the provider is not given database handles, route dispatch callbacks, shell/file access, approval privileges, or direct mutation tools

### Requirement: Verification proves no-mutation boundaries
The implementation SHALL include focused verification proving preview, cancellation, rejection, stale-source rejection, unsupported actions, RBAC failures, validation failures, and duplicate mismatches do not call mutation helpers or write production state.

#### Scenario: No-mutation tests guard preview paths
- **WHEN** focused backend tests run preview and rejection cases
- **THEN** representative mutation helpers for notes, incident status, playbooks, detection rules, incident creation, SOAR actions, shell/file access, and direct DB writes are not called

#### Scenario: Confirm tests cover all allowlisted actions
- **WHEN** focused backend tests run confirmed action cases
- **THEN** every allowlisted action is covered for valid dispatch, invalid payload, RBAC, idempotency, audit metadata, and outcome mapping

#### Scenario: Frontend tests cover review workflow
- **WHEN** focused frontend tests run
- **THEN** they cover preview rendering, exact payload visibility, explicit confirmation, cancellation, stale preview blocking, result display, and role-gated controls
