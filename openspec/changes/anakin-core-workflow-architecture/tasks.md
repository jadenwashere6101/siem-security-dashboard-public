## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `anakin-core-workflow-architecture`.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. Workflow Orchestration

- [x] 2.1 Add canonical workflow constants, contracts, request/response envelopes, and conservative classifier.
- [x] 2.2 Add workflow orchestration dispatch that delegates to separate existing engines/services.
- [x] 2.3 Add compatibility adapters for existing explain/chat/draft/investigation routes without breaking legacy response shapes.
- [x] 2.4 Ensure auto-routing cannot reach SOC Briefing, Repo Assistant, preview, confirm, or mutation paths.

## 3. Workflow Behavior

- [x] 3.1 Add Decision Support behavior that returns recommendation-only reasoning and rejects artifact/mutation requests.
- [x] 3.2 Ensure Generate Artifact remains strict and performs no more than one bounded repair attempt.
- [x] 3.3 Expose Deep Investigate lifecycle stages in backend metadata/response without SSE/WebSockets.
- [x] 3.4 Preserve existing profile routing, local-only policy, RBAC, sanitization, bounded tools, audit logging, and no-paid-fallback behavior.

## 4. Inventory And Tests

- [x] 4.1 Update AI inventory/acceptance mapping so every known action maps to one canonical workflow and approved profile.
- [x] 4.2 Add focused backend tests for classification, compatibility adapters, workflow safety, Decision Support, Generate Artifact, and Deep Investigate lifecycle.
- [x] 4.3 Run focused backend tests and the existing offline acceptance harness.
- [x] 4.4 Run affected frontend contract tests only if frontend files change.

## 5. Verification

- [x] 5.1 Run Python compilation for modified backend modules.
- [x] 5.2 Run `git diff --check`.
- [x] 5.3 Run `openspec validate anakin-core-workflow-architecture --strict`.
- [x] 5.4 Confirm `git status --short`.
