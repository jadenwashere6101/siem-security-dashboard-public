## Context

Phase 1A established `core/ai` as the only provider boundary. Phase 1B added contextual SIEM chat/explain routes and shared response UI. Phase 3 added fixed read-only SOC tools. Phase 4 added transient draft generation through `POST /ai/drafts`, canonical draft schemas in `core/ai/draft_schemas.py`, and draft UI labels showing `ai_generated`, `read_only`, `persisted=false`, `applied=false`, and `approval_required_before_apply=true`.

Current mutation paths already exist and should be reused rather than duplicated:

- Alert notes: `POST /alerts/<alert_id>/notes` in `routes/alert_mutation_routes.py`, analyst/super-admin, validates `note_text` length.
- Incident status: `POST /incidents/<incident_id>/status` in `routes/incident_routes.py`, analyst/super-admin, uses `update_incident_status()` and writes `UPDATE_INCIDENT_STATUS` audit events.
- Playbook definitions: `POST /playbooks` and `PUT /playbooks/<playbook_id>` in `routes/playbook_routes.py`, super-admin only, uses existing playbook validators and does not run executions.
- Detection rules: `PATCH /admin/detection-rules/<rule_id>` in `routes/admin_routes.py`, super-admin only, validates parameters/active through detection config helpers and writes `detection_rule_updated` audit events.
- Incident creation/linking from an alert: no public dedicated route was found; existing behavior lives in `core.incident_store.maybe_create_or_link_incident()` and related incident helpers used by ingest, plus escalation-oriented logic in `core.response_command_service`.

Existing approval requests in `core/approval_store.py` are oriented around SOAR/playbook gates. Phase 5 should not broaden that table into a generic AI action executor unless implementation proves an existing helper cleanly supports a specific allowlisted action. The safer design is a dedicated AI action preview/confirmation service that routes to existing mutation helpers only after explicit confirmation, while recording AI-specific audit metadata.

## Goals / Non-Goals

**Goals:**

- Convert reviewed Phase 4 drafts or explicit analyst requests into a small allowlist of validated action previews.
- Require explicit analyst confirmation before any production mutation helper or API path is called.
- Route each confirmed action through the existing canonical service/API path for that action.
- Preserve RBAC, audit logging, idempotency, validation, outcome classification, stale-draft protection, cancellation/rejection no-mutation behavior, and secret-safe logging.
- Display the exact payload, target resources, AI-generated origin, confirmation state, execution result, and outcome classification in the frontend.

**Non-Goals:**

- Autonomous execution, silent writes, background actions, model-chosen write tools, generic "create anything" APIs, direct DB writes from providers, shell/file access, SOAR action execution, block IP actions, approval-system redesign, schema migrations by default, or broad cleanup.
- Treating Phase 4 drafts as persisted approvals or executable state.
- Adding arbitrary registry commands, playbook executions, approval decisions, dead-letter operations, provider configuration changes, migrations, deployments, or VM operations.
- Replacing existing admin/detection/playbook/incident UI workflows.

## Decisions

### Use one canonical AI action contract under `core/ai`

Create `core/ai/action_schemas.py` for the Phase 5 allowlist, schemas, RBAC metadata, idempotency policy, stale-source fields, and output vocabulary. Initial action types are exactly:

| Action type | Purpose | Required role | Existing target path/helper |
| --- | --- | --- | --- |
| `add_alert_note` | Add reviewed note text to an alert | analyst or super-admin | `POST /alerts/<alert_id>/notes` behavior / extracted helper |
| `add_incident_note` | Add reviewed note text to an incident | analyst or super-admin | New narrow helper/route only if no existing incident note path exists |
| `change_incident_status` | Move incident to an allowed status | analyst or super-admin | `update_incident_status()` / `POST /incidents/<id>/status` behavior |
| `create_playbook_draft` | Create a disabled playbook definition from reviewed draft payload | super-admin | `POST /playbooks` validation path with `enabled=false` |
| `update_detection_rule_parameters` | Patch existing bounded detection rule parameters | super-admin | `PATCH /admin/detection-rules/<rule_id>` validation path; parameters only by default |
| `create_incident_from_alert` | Create or link an incident for an existing alert | analyst or super-admin | extracted reuse of `maybe_create_or_link_incident()` or equivalent incident helper |

The implementation SHALL NOT include `block_ip`, `monitor`, `flag_high_priority`, registry commands, playbook execution, approval decisions, integrations, queue retry, file changes, or shell commands in the Phase 5 allowlist.

Rationale: the roadmap lists five candidate action categories. Splitting note creation into alert and incident variants keeps schemas precise while staying within "add alert or incident note." Keeping playbook creation disabled makes "playbook draft" concrete without running automation.

Alternative considered: generic action objects with route/path fields. Rejected because they allow route smuggling and make RBAC, validation, audit, and outcome mapping hard to prove.

### Add a preview/confirm service, not a write-capable AI tool loop

Create `core/ai/action_service.py`. It SHALL expose two operations:

1. `preview_ai_action(payload, actor)` validates action type, target ids, payload shape, source draft metadata, current target state, RBAC, and stale-source hashes/timestamps, then returns an action preview with `requires_confirmation=true`.
2. `confirm_ai_action(payload, actor)` revalidates the preview, requires an exact `confirmation_token` and `confirm=true`, checks idempotency, dispatches to the mapped existing helper, writes audit metadata, and returns an outcome.

Routes in `routes/ai_routes.py` stay thin:

- `POST /ai/actions/preview`
- `POST /ai/actions/confirm`

Both routes require `login_required`; per-action role checks are performed by the service using existing RBAC helpers/role vocabulary. Routes must not contain business validation or dispatch logic.

Rationale: preview and confirm are separate state transitions. Confirmation must not rely on client-visible draft text alone.

Alternative considered: add "Apply" directly to `POST /ai/drafts`. Rejected because it couples generation with mutation and makes cancellation/rejection no-mutation harder to verify.

### Treat Phase 4 drafts as evidence, not authority

The action preview may accept an optional `source_draft` reference copied from the displayed Phase 4 response:

- `draft_type`
- `client_request_id`
- `generated_at`
- `labels`
- selected payload fields
- source ids/context ids

The service must validate the action payload independently. Draft labels are checked to ensure the source was AI-generated and not already applied, but a valid draft does not grant permission, bypass RBAC, or skip confirmation.

Stale-source detection should compare target identifiers plus a bounded target state fingerprint where available, such as incident status, detection rule updated timestamp/parameters, playbook id existence, or alert status/source fields. A stale preview returns `stale_source` and does not mutate.

### Dispatch through existing validated helpers

Implementation should extract small service helpers from existing routes when route logic is currently trapped inside Flask handlers. Extraction is allowed only to reuse validation and persistence logic; do not copy complex SQL into AI modules.

Expected helper targets:

- Alert notes: extract `create_alert_note(conn, alert_id, actor, note_text)` or equivalent from `routes/alert_mutation_routes.py`.
- Incident notes: if no incident notes table/API exists, Phase 5 implementation must either add a narrow incident note helper consistent with alert notes or mark `add_incident_note` blocked in implementation. Do not fake incident notes by appending to unrelated fields.
- Incident status: call `update_incident_status()` and preserve transition validation.
- Playbook draft: call existing `_validate_*` helper equivalents and `create_playbook_definition()` with `enabled=false`; if route validators need extraction, move them into a small reusable helper.
- Detection rule parameters: use `validate_detection_rule_config()` and existing persistence/audit semantics; Phase 5 should not toggle `active` unless the spec is explicitly amended.
- Create incident from alert: reuse `maybe_create_or_link_incident()` or extract a helper that loads the alert, applies existing incident policy, creates/links idempotently, and logs/audits the result.

### Idempotency and duplicate submission

Every preview returns a server-derived `confirmation_token` and recommended `idempotency_key`. Confirm requests must include the same token, action type, target ids, payload digest, and idempotency key. Duplicate confirms with the same idempotency key and payload digest return the original outcome when safe, or `duplicate_suppressed` when the prior outcome cannot be safely replayed.

If existing target APIs do not support idempotency for a specific action, the AI action service must implement a narrow idempotency guard before dispatch. This may be in-memory for tests only if no durable mutation can happen twice in production; otherwise use existing persisted records/audit evidence or stop for schema discussion.

### Audit and outcome vocabulary

Confirmed actions must write an audit event such as `AI_ACTION_CONFIRMED` with safe metadata:

- actor username/role
- action type
- target resource keys
- source draft type/request id when present
- confirmation token digest only
- idempotency key
- status/outcome classification
- existing route/helper used

Do not log prompt text, raw draft bodies, credentials, long note bodies, full playbook steps, or raw provider output.

Outcome mapping:

- `real`: target mutation succeeded and represents production state.
- `tracking_only`: target path records tracking-only state, if reused in future; not expected for the initial allowlist except through existing outcome helpers.
- `simulated`: existing path explicitly reports simulation.
- `pending`: action created a pending object requiring later work.
- `failed`: validation or dispatch failed after confirmation without known mutation, with rollback where possible.
- `unknown`: dispatch result cannot prove mutation status.
- `cancelled` / `rejected`: user did not confirm; no mutation helper called.

### Frontend review and confirmation experience

Extend the existing AI draft/response surface rather than adding a separate workspace. The UI SHALL show:

- AI-generated source and draft/action type.
- Exact target resource and payload preview.
- Role/permission requirement.
- Stale-source warning when target state changed.
- Explicit confirmation checkbox or typed confirmation plus a final confirm button.
- Cancel/reject action with visible "No production change made" state.
- Loading, retry, duplicate-submission protection, disabled confirm while stale, and result outcome.

The frontend must never call existing mutation services directly from a draft panel. It calls only `/ai/actions/preview` and `/ai/actions/confirm`; the backend performs final validation and dispatch.

## Risks / Trade-offs

- [AI action path becomes a generic executor] -> Fixed allowlist, no route/path fields, per-action schemas, and tests rejecting unknown/free-form/mutation-like action names.
- [Drafts appear approved] -> Drafts remain transient evidence; preview and confirm require independent validation and role checks.
- [Double-submit creates duplicate notes/incidents/playbooks] -> Idempotency key plus payload digest is mandatory before dispatch; tests cover duplicate confirms.
- [Cancellation/rejection mutates accidentally] -> Preview cannot call mutation helpers; cancel/reject has no backend mutation path other than optional metadata-free UI state.
- [Existing helper extraction changes behavior] -> Extract minimally and run existing alert, incident, playbook, detection, and AI regression tests.
- [Incident notes may not exist] -> Implementation must not fake them. Add a narrow real incident note path only if schema/support exists or is explicitly accepted by this spec's implementation plan.
- [Live action UI confuses simulated/tracking-only/real outcomes] -> Use existing outcome labels and explicit result badges.

## Migration Plan

1. Implement schemas/service/routes and helper extraction in the Mac repository only.
2. Add focused backend tests for all action schemas, RBAC, preview no-mutation, confirm dispatch, idempotency, audit metadata, stale-source rejection, cancellation/rejection, and unsupported action rejection.
3. Add focused frontend tests for action preview, confirmation, cancellation, stale-draft, result states, and role-gated controls.
4. Run Python compilation, focused backend tests, focused frontend tests, frontend build, `git diff --check`, and `openspec validate approval-gated-ai-actions --strict`.
5. No VM work during implementation. After commit/review approval, backend and frontend runtime changes require a separate VM deployment task.

Rollback is code-only unless implementation adds a new incident note persistence path. If a migration becomes necessary, rollback must include the migration rollback plan and VM handoff.

## Future Phase Dependencies

Future phases may add more action types only by adding a schema entry, explicit target helper mapping, RBAC rule, audit/outcome contract, and focused no-mutation tests. This design does not create autonomous action selection. A future autonomous SOC engine would require a separate OpenSpec and should not reuse Phase 5 confirmation as implicit permission.

## Open Questions

- Incident note storage/API was not found during the scoped audit. Implementation must verify whether an incident note path exists in migrations or hidden helpers. If it does not, either add a narrow incident note path as part of the `add_incident_note` action or leave that action unimplemented with a documented blocker; do not write notes into unrelated incident fields.
