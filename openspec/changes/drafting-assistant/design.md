## Context

Phase 1A provides the provider-neutral `AiGateway`, local-first routing, timeout/fallback behavior, and metadata. Phase 1B adds `POST /ai/explain`, `POST /ai/chat`, `core/ai/context_builder.py`, `core/ai/explainer_service.py`, and shared frontend AI response components for read-only analyst assistance. Phase 2 adds a separate super-admin repo assistant. Phase 3 adds fixed, API-backed SOC read tools through `core/ai/soc_tools.py` and `core/ai/soc_tool_executor.py`.

Phase 4 should let AI propose structured follow-up content, but it must not blur the line between a suggestion and production state. Existing mutation paths already exist for incident updates, playbook definitions/executions, response registry commands, approvals, and SOAR actions. Draft generation must remain upstream of those workflows and must not call them.

## Goals / Non-Goals

**Goals:**

- Generate AI-authored drafts for detection rule changes, playbook drafts, incident notes, escalation summaries, response recommendations, and investigation checklists.
- Define one canonical backend draft contract with explicit schemas, validation, source attribution, status vocabulary, and read-only metadata.
- Reuse Phase 1A gateway metadata, Phase 1B context/prompt flow, and Phase 3 read-tool evidence where useful.
- Add a thin authenticated API endpoint that returns review-only draft payloads and never persists or applies them.
- Extend the existing analyst AI UI to present drafts as visibly AI-generated, reviewable proposals that are not production state.
- Add focused verification for non-persistence, mutation-path separation, RBAC, validation, grounding, redaction, and UI clarity.

**Non-Goals:**

- Approval-gated execution, draft application, draft persistence, database migrations, or production writes.
- Creating or modifying detection rules, playbook definitions, incidents, notes, registry commands, approvals, SOAR actions, blocklists, files, commits, pushes, deployments, or VM state.
- Redesigning the AI gateway, Phase 1B chat/explainer flow, Phase 3 read-tool executor, approval architecture, or SOAR execution architecture.
- A broad workflow builder, autonomous agent, fine-tuning, vector store, background drafting, or speculative future action framework.
- Paid-provider setup or new provider adapters.

## Decisions

### Add canonical draft schemas under `core/ai`

Create `core/ai/draft_schemas.py` or `core/ai/drafts.py` with the canonical draft contract:

- `DraftTypeDefinition`: draft type, description, input fields, output schema, allowed context types, optional read-tool evidence policy, maximum section/item counts, and future handoff target label.
- `DraftRequest`: draft type, analyst question/instruction, context payload, optional `use_tools`, tool policy, actor metadata, and client request id.
- `DraftResult`: status, draft type, draft payload, validation errors, sources, tool summary, gateway metadata, generated timestamp, `ai_generated=true`, `read_only=true`, `persisted=false`, `applied=false`, and `approval_required_before_apply=true`.
- `DraftValidationError`: safe validation error with status code and error code.

Initial supported draft types:

| Draft type | Purpose | Review-only output |
| --- | --- | --- |
| `detection_rule_change` | Propose bounded detection rule edits or new rule logic | title, rationale, target rule when known, suggested condition/query/pseudocode, severity, false-positive notes, test ideas, rollback notes |
| `playbook_draft` | Propose a playbook outline | name, trigger context, ordered steps, approval gates, simulation/real caveats, required integrations, risks |
| `incident_note` | Draft a note for an incident record | summary, evidence, uncertainty, recommended next steps, attribution |
| `escalation_summary` | Draft handoff/escalation text | audience, urgency, business/security impact, evidence, asks, next update criteria |
| `response_recommendation` | Propose response options | recommended action class, prerequisites, expected outcome, approval need, risk, alternatives |
| `investigation_checklist` | Produce analyst checklist | ordered checks, data sources, expected findings, stop conditions |

Rationale: one schema location prevents drift across backend services, tests, and UI labels. The contract is intentionally draft-oriented and does not share execution payload classes with Phase 5 actions.

Alternative considered: free-form text drafts only. Rejected because review safety requires predictable fields and validation.

### Add a separate draft service, not mutation hooks

Create `core/ai/drafting_service.py`. It SHALL:

1. Validate request shape and draft type.
2. Build canonical SIEM context through Phase 1B `build_ai_context()`.
3. Optionally gather Phase 3 read-tool evidence when explicitly requested and safe for the actor.
4. Build a supplied-evidence-only prompt that asks for structured JSON matching the selected draft schema.
5. Call `AiGateway.generate()` only after validation and context/evidence preparation.
6. Parse and validate model output into the canonical draft result.
7. Return a review-only response with metadata, sources, tool evidence, and draft validation status.

The service SHALL NOT call incident note creation, detection rule save/update, playbook definition create/update, response registry commands, approval creation, SOAR execution, blocklist mutation, shell/file operations, migrations, commits, pushes, deployment helpers, or direct database writes.

Rationale: draft generation belongs near the existing AI service layer, but must remain independent from production mutation services.

Alternative considered: add draft buttons directly to existing mutation forms. Rejected for Phase 4 because it makes it too easy to confuse generated proposals with editable production state.

### Add one thin authenticated draft route

Extend `routes/ai_routes.py` with:

- `POST /ai/drafts`

The route SHALL use `login_required` and `analyst_or_super_admin_required`, accept JSON only, validate request bodies through `drafting_service`, and return JSON. Expected disabled/unavailable/provider-timeout/fallback-blocked/insufficient-context states should return structured draft responses where practical; invalid client input returns `400`; auth/RBAC remains existing `401/403`.

Request shape:

```json
{
  "draft_type": "incident_note",
  "instruction": "Draft a concise note for the incident timeline.",
  "context_type": "incident",
  "context": {"incident_id": 123},
  "use_tools": true,
  "tool_policy": {"max_tool_calls": 3, "time_window_hours": 24},
  "client_request_id": "optional-ui-id"
}
```

Response shape:

```json
{
  "status": "success",
  "draft": {
    "draft_type": "incident_note",
    "title": "AI draft incident note",
    "payload": {},
    "validation": {"valid": true, "errors": []},
    "labels": {
      "ai_generated": true,
      "read_only": true,
      "persisted": false,
      "applied": false,
      "approval_required_before_apply": true
    }
  },
  "context": {},
  "tools": {},
  "metadata": {},
  "error": null
}
```

### Treat drafts as generated artifacts, not production records

Phase 4 SHALL keep draft history client-session-only unless the user explicitly copies text out of the UI. The backend response is transient. Do not add database tables, server-side draft storage, browser local storage, or automatic draft-to-form injection.

If the UI offers copy/export, it must copy only the displayed draft content and preserve the “AI-generated draft, not applied” label. It must not submit the draft to existing production APIs.

Rationale: persistence introduces retention, audit, ownership, and approval semantics that belong to later phases.

### Reuse source grounding and Phase 3 evidence

Draft prompts SHALL use only:

- validated request instruction;
- Phase 1B canonical context payloads and source metadata;
- optional Phase 3 read-tool evidence gathered through the fixed executor;
- existing gateway/provider metadata.

The prompt SHALL instruct the model to:

- output only the selected draft schema;
- avoid claiming production changes were made;
- mark uncertainty and assumptions;
- include source/evidence references;
- avoid secrets and credential-like values;
- avoid commands or payloads that execute changes directly.

If context or tool evidence is insufficient for a safe draft, the service SHALL return `insufficient_context` or `draft_validation_failed` rather than inventing a complete proposal.

### Frontend review experience extends existing AI UI

Add or extend frontend code minimally:

- `frontend/src/services/aiService.js`: add `requestAiDraft()`.
- `frontend/src/components/AiDraftReviewPanel.js` or a clearly separated draft mode inside `AiResponsePanel`.
- Optional draft display utility for labels, validation errors, and draft-type names.
- Contextual “Draft…” controls only where a draft naturally belongs: incident detail, alert/detail investigation surfaces, response registry context, source-IP/recon investigation views, and playbook/detection-related workspaces if existing UI already exposes them.

The UI SHALL visibly show:

- “AI-generated draft”;
- “Not applied” / “Not saved”;
- draft type;
- validation status;
- source/tool evidence summary;
- provider/model/cost metadata;
- retry/cancel/dismiss behavior consistent with Phase 1B;
- stale response warning when visible context changes.

Do not add controls that look like execution, approval, or production-save actions in Phase 4.

### File-level implementation plan

Expected backend files:

- Create `core/ai/draft_schemas.py`.
- Create `core/ai/drafting_service.py`.
- Modify `routes/ai_routes.py`.
- Modify `core/ai/__init__.py` only if exports are needed.
- Add `tests/test_ai_drafting_assistant.py`.

Expected frontend files:

- Modify `frontend/src/services/aiService.js` and tests.
- Create `frontend/src/components/AiDraftReviewPanel.js` and tests, or extend `AiResponsePanel` with explicitly tested draft rendering.
- Modify only the existing AI entry-point components needed to expose draft controls.
- Add/update focused component tests for draft controls and review rendering.

## Risks / Trade-offs

- [Drafts look like production state] -> Use explicit labels, `persisted=false`, `applied=false`, no save/apply buttons, and UI tests for draft-only copy.
- [Implementation accidentally calls mutation helpers] -> Add regression tests with representative mutation helpers mocked and assert they are not called.
- [Model returns malformed or unsafe JSON] -> Parse, validate, and return `draft_validation_failed` without presenting invalid payloads as usable drafts.
- [Drafts leak secrets from context/tool evidence] -> Reuse redaction before prompt construction and response serialization; test credential-like keys/values.
- [Local model quality is inconsistent] -> Keep schemas concise, allow validation failure, and preserve analyst review as mandatory.
- [Phase 4 bleeds into Phase 5] -> No persistence, approvals, execution, direct form submission, or action payload handoff in this phase.

## Migration Plan

1. Implement draft schemas/service, thin route, and focused backend tests in the Mac repository only.
2. Extend the existing AI frontend service/review surface and add focused component tests.
3. Run Python compilation, focused backend tests, focused frontend tests, frontend build, `git diff --check`, and `openspec validate drafting-assistant --strict`.
4. No VM work occurs during implementation. Because Phase 4 changes backend and frontend runtime behavior, VM sync will be required later only after review, commit/push authorization, and a separate deployment task.

Rollback is code-only: remove the draft route/service/modules and draft UI controls. No database rollback is expected because Phase 4 introduces no persisted draft state.

## Future Phase Dependencies

Phase 5 approval-gated actions may reuse draft schemas as input references, but it must define separate approval and execution contracts. Phase 5 must not treat a Phase 4 draft response as approval, production state, or an executable command.

Future provider/model improvements may improve draft quality, but providers still must not receive mutation capabilities, database handles, shell/file access, or direct approval/execution privileges.

## Open Questions

- None blocking. Implementation may choose a separate `AiDraftReviewPanel` or a clearly separated draft mode inside `AiResponsePanel`, provided the UI visibly distinguishes drafts from normal answers and from production actions.
