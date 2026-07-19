## Why

Phase 4 can generate review-only AI drafts, but analysts still need a safe way to turn a small subset of reviewed drafts into existing SIEM actions without bypassing RBAC, audit logging, idempotency, validation, or outcome tracking. Phase 5 introduces that bridge while preserving the roadmap boundary that AI never acts silently or autonomously.

## What Changes

- Add a narrow approval-gated AI action contract that accepts only allowlisted Phase 5 action types.
- Add explicit preview and confirmation states so analysts see the exact payload before any mutation API is called.
- Validate each action payload against per-action schemas and route it only to the existing SIEM API/service path for that action.
- Reuse existing RBAC, audit logging, idempotency keys, and outcome vocabulary for real, simulated, tracking-only, pending, failed, and unknown results.
- Keep Phase 4 draft generation separate from Phase 5 approval/execution; a draft is never approval or executable state by itself.
- Reject unsupported, free-form, stale, cancelled, or unconfirmed actions before mutation helpers are called.
- Add focused frontend review/confirmation UI that makes AI involvement, target resources, payload, confirmation requirement, and resulting outcome clear.

## Capabilities

### New Capabilities

- `approval-gated-ai-actions`: Narrow AI-assisted action review, validation, confirmation, execution routing, audit/idempotency handling, and outcome display.

### Modified Capabilities

- None.

## Impact

- Backend: new AI action schema/service modules under `core/ai`, thin AI action routes, and narrow reuse of alert note, incident status, playbook definition, detection rule, and alert-to-incident service/API paths.
- Frontend: existing AI response/draft surfaces gain an explicit action preview, confirmation, cancellation, stale-draft protection, and result display.
- Tests: focused backend and frontend tests for allowlist validation, RBAC, no-mutation cancellation/rejection, idempotency, audit metadata, outcome mapping, and existing AI draft/read-only regressions.
- No database migration is planned unless implementation discovers that existing idempotency/audit evidence cannot safely support the required contract.
- VM sync will be required after implementation because backend and frontend runtime behavior will change.
