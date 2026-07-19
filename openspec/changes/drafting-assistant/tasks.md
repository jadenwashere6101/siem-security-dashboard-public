## 1. Scope And Dependency Confirmation

- [x] 1.1 Re-read `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, the AI roadmap, and the completed Phase 1A-3 OpenSpecs before implementation.
- [x] 1.2 Confirm the implementation reuses `AiGateway`, Phase 1B context building/service response patterns, and Phase 3 read-tool executor where specified.
- [x] 1.3 Confirm scope excludes draft persistence, production writes, approval-gated execution, SOAR actions, schema migrations, commits, pushes, VM work, deployment, and paid-provider setup.

## 2. Backend Draft Contract

- [x] 2.1 Create the canonical draft schema/definition module under `core/ai` with supported draft types, allowed context types, output schemas, limits, labels, and source metadata rules.
- [x] 2.2 Implement validation for `detection_rule_change`, `playbook_draft`, `incident_note`, `escalation_summary`, `response_recommendation`, and `investigation_checklist`.
- [x] 2.3 Add canonical response labels proving every draft is AI-generated, read-only, not persisted, not applied, and requires separate approval before any future apply path.
- [x] 2.4 Add draft validation errors and status vocabulary for unsupported type, invalid input, insufficient context, gateway unavailable, provider timeout, fallback blocked, parse failure, and draft validation failure.
- [x] 2.5 Reuse or extend existing AI redaction helpers so draft inputs, tool evidence, prompts, responses, and logs are secret-safe.

## 3. Backend Drafting Service

- [x] 3.1 Create `core/ai/drafting_service.py` to validate requests, build canonical context, optionally gather Phase 3 read-tool evidence, build prompts, call `AiGateway.generate()`, parse model output, validate schemas, and map responses.
- [x] 3.2 Keep prompts supplied-evidence-only and require schema-shaped output, source references, uncertainty, analyst review language, and no claims that production actions occurred.
- [x] 3.3 Enforce instruction length, context size, prompt size, tool-call, result-limit, and truncation rules before gateway invocation.
- [x] 3.4 Return structured insufficient-context responses without gateway inference when required context is missing, not found, inaccessible, or too thin.
- [x] 3.5 Ensure providers never receive database handles, cursors, credentials, mutation callbacks, shell/file access, or direct SIEM service objects.

## 4. Backend Route And Safety Boundary

- [x] 4.1 Add a thin `POST /ai/drafts` route in `routes/ai_routes.py`.
- [x] 4.2 Protect the route with `login_required` and `analyst_or_super_admin_required`.
- [x] 4.3 Validate JSON request bodies and return safe errors for malformed JSON, unsupported draft types, missing identifiers, oversized instructions, malformed tool policy, and invalid context.
- [x] 4.4 Preserve expected AI states as structured responses where practical: disabled, unavailable, timeout, fallback blocked, insufficient context, and draft validation failure.
- [x] 4.5 Verify route/service code does not call incident note creation, detection rule save/update, playbook definition create/update, playbook execution creation/retry/resume/abandon, approval actions, registry commands, blocklist mutation, migrations, shell/file operations, commits, pushes, or deployment helpers.

## 5. Frontend Draft Review Experience

- [x] 5.1 Extend `frontend/src/services/aiService.js` with `requestAiDraft()` using existing `buildSiemPath`, included credentials, JSON parsing, abort support, and error handling.
- [x] 5.2 Add `AiDraftReviewPanel` or a clearly separated draft mode in `AiResponsePanel` with explicit “AI-generated draft”, “not saved”, “not applied”, validation, source, provider/model, latency, cost, and tool-evidence display.
- [x] 5.3 Add contextual draft controls only where they naturally fit existing analyst workflows and do not look like production save/apply/execute controls.
- [x] 5.4 Preserve existing loading, cancellation, retry, dismissal, stale-response, navigation, scroll, dark-theme, accessibility, and responsive behavior.
- [x] 5.5 If copy/export is added, ensure it copies only displayed draft content and preserves the AI-generated/not-applied label without submitting production changes.

## 6. Backend Verification

- [x] 6.1 Add focused tests for every supported draft type schema, required fields, validation failures, labels, and response shape.
- [x] 6.2 Add service tests proving canonical context builder reuse, optional Phase 3 read-tool evidence reuse, source attribution, truncation, and insufficient-context behavior.
- [x] 6.3 Add route tests for authentication, RBAC, JSON validation, success, disabled/unavailable/timeout/fallback-blocked states, malformed provider output, and safe error serialization.
- [x] 6.4 Add regression tests with representative mutation helpers mocked to prove draft generation does not call production write, approval, SOAR, shell/file, migration, commit, push, or deployment paths.
- [x] 6.5 Add secret-safety tests proving credential-like values are redacted from draft outputs, prompt evidence, and logs.
- [x] 6.6 Run focused backend tests covering Phase 4 plus Phase 1A-3 AI regression paths materially affected by the drafting service.
- [x] 6.7 Run `python3 -m py_compile` for new and modified Python modules.

## 7. Frontend Verification

- [x] 7.1 Add focused service tests for draft request payloads, credentials, abort signals, response parsing, and validation/error handling.
- [x] 7.2 Add focused component tests for draft rendering, labels, validation errors, source/tool metadata, retry, cancel, dismiss, stale response handling, and safe copy/export behavior if present.
- [x] 7.3 Add focused tests proving draft controls do not expose apply, approve, execute, save-to-production, or run actions.
- [x] 7.4 Run focused Phase 4 frontend tests and any existing AI response tests affected by draft rendering changes.
- [x] 7.5 Run `cd frontend && npm run build`.

## 8. Manual UI Verification

- [ ] 8.1 Run the frontend locally and visually verify draft entry points in each modified analyst workflow.
- [x] 8.2 Verify draft loading, cancel, retry, dismiss, stale-response, source/tool metadata, validation errors, and responsive layout.
- [x] 8.3 Verify drafts are immediately understandable as AI-generated proposals that are not saved, not applied, and not production state.
- [x] 8.4 Verify no UI path submits a draft to production mutation, approval, execution, registry command, playbook, detection-rule, incident-note, or blocklist APIs.

## 9. Final Validation

- [x] 9.1 Review the final implementation for unnecessary abstraction, duplicate draft schema logic, mutation-path coupling, unsafe prompts, secret exposure, dead/debug code, and UI wording that implies actions were taken.
- [x] 9.2 Run `git diff --check`.
- [x] 9.3 Run `openspec validate drafting-assistant --strict`.
- [x] 9.4 Confirm no commit, push, VM access, deployment, migration, provider configuration, or production mutation occurred unless separately authorized.
- [x] 9.5 Report whether VM sync is required after implementation review because Phase 4 changes backend and frontend runtime behavior.
