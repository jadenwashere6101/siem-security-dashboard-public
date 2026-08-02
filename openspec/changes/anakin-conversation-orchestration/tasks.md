## 1. Architecture And Contract

- [x] 1.1 Validate `ddc4f33` thread creation, turns, versions, concurrency, idempotency, async linkage, ownership, assertions, reset, and PostgreSQL behavior.
- [x] 1.2 Trace canonical prompt construction, profile budgets, async request lifecycle, worker identity, frontend recovery, and Repo/SOC boundaries.
- [x] 1.3 Strictly validate the conversation orchestration OpenSpec before implementation.

## 2. Context And Reference Engine

- [x] 2.1 Implement a provenance-aware conversation context selector over owner-scoped state, entities, turns, hypotheses, and fresh evidence.
- [x] 2.2 Implement deterministic reference classification and resolved/clarification/unresolved outcomes for follow-up, comparison, continuation, prior focus, correction, and entity switching.
- [x] 2.3 Implement whole-item context compaction, explicit inclusion/omission metadata, corrupt-state rebuild behavior, and hard workflow budget enforcement.
- [x] 2.4 Add untrusted-memory prompt framing to explain, investigation, and artifact builders without changing model profiles.

## 3. Orchestration Lifecycle

- [x] 3.1 Implement owner-scoped conversational submission, terminal idempotency, queued user turns, and synchronous Quick Explain completion.
- [x] 3.2 Atomically create/link async requests and enforce one active generation per thread.
- [x] 3.3 Revalidate worker users, rebuild context at execution, persist assistant turns/state, and reject stale completion.
- [x] 3.4 Preserve failed-generation state, correction precedence, unresolved questions, entity focus, and artifact-preview labels.
- [x] 3.5 Expose linked lifecycle/turn recovery through authenticated reads and reject Repo Assistant/SOC Briefing conversation envelopes.

## 4. Minimal Client Continuity

- [x] 4.1 Add focused frontend service calls and scope-keyed thread identity plumbing without storing authoritative history in the browser.
- [x] 4.2 Pass conversation version/idempotency metadata through existing Ask Anakin and workflow controls and recover linked progress after refresh.

## 5. Regression Coverage

- [x] 5.1 Add PostgreSQL tests for sync/async turn ordering, terminal retries, concurrent tabs, stale versions/completions, failures, and refresh recovery.
- [x] 5.2 Add resolver tests for pronouns, why, continue, compare, go back, corrections, missing evidence, ambiguity, entity switching, and deleted targets.
- [x] 5.3 Add prompt-budget, compaction, corrupt-state rebuild, prompt-injection, and provenance tests for all participating workflow profiles.
- [x] 5.4 Add boundary tests proving Repo Assistant and SOC Briefing never consume SIEM conversation context and artifact behavior remains preview-only.
- [x] 5.5 Add focused frontend service/App recovery tests if frontend plumbing changes.

## 6. Verification And Handoff

- [x] 6.1 Run Python compilation and the full PostgreSQL-backed test suite without required skips.
- [x] 6.2 Run focused frontend tests and production build if frontend files changed.
- [x] 6.3 Run the AI acceptance harness, schema snapshot/migration validation, `git diff --check`, and strict OpenSpec validation.
- [x] 6.4 Review every failure class for general invariant enforcement and record files, status, risks, and deployment handoff.
- [x] 6.5 Apply the Anakin production completion gate from `docs/anakin-production-acceptance-policy.md`; because no VM/browser-path work is authorized, report exactly `Implementation complete; production behavior unverified.` and do not claim production readiness.

Full-suite correction note: the unrestricted PostgreSQL run executed without required skips at 2451 passed / 14 failed. The 14 failures exactly match baseline commit `266fb35`; there are zero new failures. The affected PostgreSQL-backed set is green at 182 passed, including 35 conversation-orchestration tests.

## 7. Production-Defect Correction

- [x] 7.1 Refactor packet construction to measure mandatory overhead, reserve final bookkeeping, compact optional categories progressively, and prove the final serialized packet fits every participating workflow budget.
- [x] 7.2 Implement explicit-entity precedence and one validated resolved execution-context object shared by turn state, workflow payload, model/tool inputs, and response metadata.
- [x] 7.3 Wire why, evidence, unique/multiple IP, go back, continue, compare, and clarification behavior through the canonical resolved context without model/request creation on ambiguity.
- [x] 7.4 Normalize full, structured-only, partial/degraded, provider/tool-failure, and malformed Deep Investigate terminal results without arbitrary object stringification or false success state.
- [x] 7.5 Add production-derived PostgreSQL, prompt-budget measurement, ownership, reset, workflow-boundary, and terminal-result regression coverage.
- [x] 7.6 Run focused compilation/tests/harness and strict validation, then run the full PostgreSQL suite once and compare failures with baseline `266fb35`.
- [x] 7.7 Complete the failure-class review and production-unverified handoff without commit, push, VM access, deployment, model/config changes, or production mutation.
