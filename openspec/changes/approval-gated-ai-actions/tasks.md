## 1. Backend Contracts

- [x] 1.1 Create canonical AI action schema definitions under `core/ai` with the exact Phase 5 allowlist, per-action required fields, field limits, role requirements, dispatch mapping, stale-source fields, and outcome vocabulary.
- [x] 1.2 Add validation for unsupported action types, route/path/function smuggling fields, mutation-like free-form requests, malformed target ids, oversized text, stale source metadata, and idempotency-key/payload-digest mismatch.
- [x] 1.3 Verify whether a real incident note storage/API path exists; implement `add_incident_note` only through that path or add the smallest explicit incident-note path required by the spec.

## 2. Service And Route Implementation

- [x] 2.1 Add `core/ai/action_service.py` with preview and confirm operations that keep preview read-only and revalidate confirmation immediately before dispatch.
- [x] 2.2 Add thin authenticated `POST /ai/actions/preview` and `POST /ai/actions/confirm` routes in `routes/ai_routes.py`.
- [x] 2.3 Extract or reuse existing helper logic for alert notes, incident status, disabled playbook definition creation, detection rule parameter updates, and incident creation/linking from alert without duplicating complex SQL.
- [x] 2.4 Implement per-action RBAC so analyst-level actions remain analyst/super-admin and playbook/detection admin actions remain super-admin-only.
- [x] 2.5 Implement confirmation tokens, payload digests, idempotency keys, duplicate-submission handling, stale-source rejection, and safe error responses.
- [x] 2.6 Add audit logging for confirmed AI action attempts with safe metadata only, preserving existing action-specific audit events where existing paths emit them.
- [x] 2.7 Map existing helper results into explicit AI action outcomes: real, simulated, tracking-only, pending, failed, unknown, duplicate, cancelled, and rejected.

## 3. Frontend Implementation

- [x] 3.1 Extend `frontend/src/services/aiService.js` with AI action preview and confirm calls that use existing SIEM path/JSON/error conventions.
- [x] 3.2 Extend the existing AI draft/response UI with action preview, exact payload display, target resource display, role requirement display, stale-source warning, explicit confirmation, cancel/reject, retry, loading, and result states.
- [x] 3.3 Ensure draft generation does not automatically preview or confirm actions; action controls must be a separate explicit analyst workflow.
- [x] 3.4 Add role-gated or disabled UI behavior for super-admin-only actions and stale previews.

## 4. Backend Verification

- [x] 4.1 Add focused backend tests covering all allowlisted action schemas and valid preview responses.
- [x] 4.2 Add focused backend tests proving preview, cancellation, rejection, stale-source rejection, unsupported actions, RBAC failures, validation failures, and idempotency mismatches do not call mutation helpers or write production state.
- [x] 4.3 Add focused backend tests for confirmed dispatch of every implemented allowlisted action, including idempotency duplicate behavior, audit metadata, and outcome mapping.
- [x] 4.4 Add regression tests proving providers, read tools, and draft generation do not receive mutation callbacks, DB handles, shell/file access, or direct action privileges.
- [x] 4.5 Run existing focused regression tests for AI drafting, AI explainer/chat, alert note contracts, incident routes, playbook routes, detection rule admin contracts, audit/idempotency helpers, and outcome semantics affected by helper extraction.

## 5. Frontend Verification

- [x] 5.1 Add focused service tests for preview/confirm request and error handling.
- [x] 5.2 Add focused component/integration tests for exact payload visibility, explicit confirmation gating, cancel/reject no-mutation messaging, stale preview blocking, duplicate-submit protection, outcome display, and role-gated controls.
- [x] 5.3 Run focused frontend tests for the modified AI response/draft/action UI and services.
- [x] 5.4 Run `cd frontend && npm run build`.
- [ ] 5.5 Perform focused manual browser verification of preview, confirm, cancel/reject, stale-source blocking, result states, responsive layout, and existing draft/read-only AI separation when practical.
  - Pending: automated component/service coverage exists, but local Flask-served `/siem` still renders a blank white page; dev-server smoke renders the login page only.

## 6. Final Checks

- [x] 6.1 Run `python3 -m py_compile` for new and modified Python modules.
- [x] 6.2 Run `git diff --check`.
- [x] 6.3 Run `openspec validate approval-gated-ai-actions --strict`.
- [x] 6.4 Review the final diff for unrelated changes, accidental mutation shortcuts, debug code, broad cleanup, secret exposure, and UI wording that implies autonomous action.
- [x] 6.5 Confirm no commit, push, VM access, deployment, migration, provider configuration, or production mutation occurred during implementation unless separately authorized.
