## 1. OpenSpec and Coverage Inventory

- [x] 1.1 Create concise proposal, design, specification delta, and tasks for the 15-scenario pre-NIST gate.
- [x] 1.2 Map every scenario to meaningful existing tests or harness fixtures before adding coverage.
- [x] 1.3 Strictly validate the OpenSpec before implementation.

## 2. Offline Acceptance Infrastructure

- [x] 2.1 Add the immutable 15-scenario manifest with exact prompts, expected workflow/profile, layers, safety expectations, and existing coverage references.
- [x] 2.2 Add the compact `PASS` / `BLOCKING_FAIL` / `BOUNDED_FIX` / `DEFER` / `NOT_RUN` result model and deterministic classification precedence.
- [x] 2.3 Add focused tests for matrix completeness, exact prompts, coverage-reference integrity, routing expectations, paid-canary discipline, and result classification.
- [x] 2.4 Confirm the existing token-observability cleanup remains intact and unaltered by this change.

## 3. Mac Verification

- [x] 3.1 Run relevant planner, entity-binding, conversation/reference, SOC-tool, workflow, RBAC/approval, session-memory, and provider/routing/accounting tests.
- [x] 3.2 Run the offline acceptance harness with live smoke disabled and confirm zero real provider calls.
- [x] 3.3 Run PostgreSQL-backed affected tests where locally available and report any unavailable coverage honestly.
- [x] 3.4 Run Python compilation, `git diff --check`, and strict OpenSpec validation.
- [x] 3.5 Review the combined diff and classify findings without implementing speculative fixes.

## 4. Later Authorized Production Acceptance

- [ ] 4.1 VM AI: execute Layer B with live IDs, minimized duplicate planner calls, and recorded Anthropic attempt/cost evidence after explicit authorization.
- [ ] 4.2 Browser/manual owner: execute Layer C through `/siem/` and record rendered identity/evidence, lifecycle, clarification, artifact, RBAC, and failure-state results.
- [x] 4.3 Apply `docs/anakin-production-acceptance-policy.md`; until Layers B and C pass, report exactly: `Implementation complete; production behavior unverified.`
