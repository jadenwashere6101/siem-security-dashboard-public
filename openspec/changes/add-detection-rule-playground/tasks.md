## 1. Temporary Rule Contract and Safety Limits

- [x] 1.1 (Mac AI) Define the `Temporary Playground Rule` request/response contract in the simulator backend, including exact enums, types, validation errors, and response mode markers.
- [x] 1.2 (Mac AI) Implement the validator-owned source-to-source_type, source-to-input-format, and source-to-allowed-field compatibility matrices with fail-closed errors.
- [x] 1.3 (Mac AI) Enforce resource limits before evaluation: maximum 100 pasted/sample events, 256 KB total request payload, 8 KB per raw event, 256 chars per scalar string, `threshold` 1-100, `window_minutes` 1-1440, `in_list` length 1-20, and maximum 50 grouped result rows.
- [x] 1.4 (Mac AI) Implement the explicit history decision as pasted-event-only evaluation and reject any request shape that attempts history-aware or persisted-rule behavior.
- [x] 1.5 (Mac AI) Add focused contract tests for valid rules plus invalid source, source_type, field, operator, comparison value, threshold, window, unsupported group-by, event-count, and payload-size failures.

## 2. Backend Temporary-Rule Evaluator

- [x] 2.1 (Mac AI) Extend the existing simulator route/engine path with a second mode for temporary playground rules while preserving the Version 1 production-rule path unchanged.
- [x] 2.2 (Mac AI) Reuse the existing parser and normalization paths to convert pasted or sample input into normalized events before playground evaluation.
- [x] 2.3 (Mac AI) Implement the bounded evaluator for exactly one condition, `count` aggregation, one group-by field, one threshold, and one window inside the simulator-owned rollback transaction only.
- [x] 2.4 (Mac AI) Produce backend evidence for parse success/failure, normalization output, applicability, observed grouped value, configured threshold, evaluated window, threshold reached/not reached, matched entity, selected severity, and explicit non-persistence confirmation.
- [x] 2.5 (Mac AI) Extend zero-durable-write and separate-connection worker-visibility tests across `events`, `alerts`, `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `incidents`, `incident_alerts`, and `audit_log` for the temporary-rule mode.
- [x] 2.6 (Mac AI) Add regression tests proving the existing Version 1 production-rule simulation path and production detector behavior remain unchanged.

## 3. MITRE and SOAR Preview Integration

- [x] 3.1 (Mac AI) Reuse the existing alert-preview contract to build a temporary alert preview from the evaluator result without creating a durable production alert.
- [x] 3.2 (Mac AI) Reuse existing MITRE preview enrichment shape with optional `mitre_technique_id` selection and explicit no-mapping behavior when none is selected.
- [x] 3.3 (Mac AI) Reuse playbook matching and SOAR preview assembly so temporary alerts surface matching playbooks, approval requirements, and selected response previews without enqueueing or executing anything.
- [x] 3.4 (Mac AI) Add tests confirming no external integrations, no reputation/geolocation quota calls, and no worker-visible pending rows occur during temporary-rule preview runs.

## 4. Guided Rule Builder UI

- [x] 4.1 (Mac AI) Extend the existing Detection Simulator workspace with a two-mode selector for `Existing Production Rule` and `Temporary Playground Rule`.
- [x] 4.2 (Mac AI) Build the temporary-rule controls: source selector, input format selector, pasted/sample event input, condition builder, group-by selector, threshold, window, severity, optional MITRE selector, and Run/Reset controls.
- [x] 4.3 (Mac AI) Add a live plain-language rule summary and explicit non-persistence language such as `Reset Rule`, `Discard Draft`, or `Clear Builder`, with no `Save Rule` or promotion wording.
- [x] 4.4 (Mac AI) Implement frontend validation and malformed-response handling while ensuring React renders backend evidence only and performs no rule evaluation client-side.
- [x] 4.5 (Mac AI) Add focused frontend tests for builder validation, exact request submission, role visibility, no client-side evaluation, and reset/discard behavior.

## 5. Explainability and Pipeline Integration

- [x] 5.1 (Mac AI) Reuse the existing pipeline visualization and results layout for temporary-rule mode, preserving stage order and rollback disclosure.
- [x] 5.2 (Mac AI) Render backend-supplied explainability for parse failure, normalization failure, invalid rule, rule applicable/not applicable, grouped evidence, threshold reached/not reached, alert preview, MITRE preview, SOAR preview, and nothing-persisted confirmation.
- [x] 5.3 (Mac AI) Add desktop and narrow-layout, keyboard-accessibility, dark-theme, and no-new-console-error checks for the updated workspace.

## 6. Final Quality Gates and VM Handoff

- [x] 6.1 (Mac AI) Run focused backend tests, focused frontend tests, affected regressions, and the frontend production build; record results in `verification.md`.
- [x] 6.2 (Mac AI) Run local browser verification for both simulator modes and record evidence, limitations, and rollback notes in `verification.md`.
- [x] 6.3 (Mac AI) Run `git diff --check` and `openspec validate add-detection-rule-playground --strict`; record results in `verification.md`.
- [x] 6.4 (Mac AI) Confirm no migration is included unless implementation discovers a hard requirement and stops for review.
- [x] 6.5 (Mac AI) Prepare a VM handoff section in `verification.md` covering approved-commit placeholder, expected files, deployment order, read-only production checks, and rollback plan, without accessing the VM.

## 7. VM Deployment and Production Verification

- [ ] 7.1 (VM AI) After explicit authorization, verify clean VM state, fetch without merging, confirm the approved commit, and sync only per `docs/mac-vm-source-of-truth-policy.md`.
- [ ] 7.2 (VM AI) Deploy backend first, verify health and authenticated read-only simulator checks, then deploy the Mac-built frontend artifact.
- [ ] 7.3 (VM AI) Verify the deployed Detection Simulator modes, role boundaries, rollback disclosure, and zero-row-delta evidence with read-only production-safe checks only.
- [ ] 7.4 (VM AI) Record deployed commit, service/artifact actions, sanitized verification evidence, rollback readiness, and unresolved risks in `verification.md`.
