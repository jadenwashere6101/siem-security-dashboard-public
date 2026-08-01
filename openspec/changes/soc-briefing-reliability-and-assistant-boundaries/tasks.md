## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `soc-briefing-reliability-and-assistant-boundaries`.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. SOC Briefing Reliability

- [x] 2.1 Make SOC briefing run-step persistence idempotent for repeated `(run_id, step_index)` writes.
- [x] 2.2 Preserve deterministic monotonic step indexes and useful transition audit metadata.
- [x] 2.3 Harden stale-job recovery so active leases, retryable jobs, terminal jobs, and normal timer waiting are handled distinctly.
- [x] 2.4 Preserve bounded retries, duplicate active manual-job prevention, manual-only Run Now behavior, no paid fallback, and no production action paths.

## 3. SOC Briefing Health And UI Lifecycle

- [x] 3.1 Expose timer-aware worker health states: `healthy_waiting`, `recently_successful`, `running`, `stale`, `failed`, and `timer_inactive`.
- [x] 3.2 Ensure manual Run Now lifecycle exposes queued, running, terminal state, exact failure/blocking reason, and produced briefing id when available.
- [x] 3.3 Ensure frontend control status copy treats one-shot timer waiting as healthy/waiting rather than offline and selects produced briefings after success.

## 4. Repo Assistant Boundaries

- [x] 4.1 Add live SIEM-data question detection before repository retrieval/provider calls.
- [x] 4.2 Return a clear boundary response with guidance for Dashboard, Alert Details, or SOC Command Center.
- [x] 4.3 Preserve factual/evaluative repo answers, backend-owned citations, and authorization behavior.

## 5. Tests And Acceptance

- [x] 5.1 Add focused SOC briefing store/worker/history tests for idempotent steps, repeated processing, stale recovery, terminal lifecycle, history persistence, failure codes, worker health semantics, duplicate manual jobs, and manual-only Run Now.
- [x] 5.2 Add focused Repo Assistant tests for live-data boundaries, factual/evaluative repo questions, no retrieval for live-data questions, citations, and RBAC.
- [x] 5.3 Run PostgreSQL-backed async workflow tests from the prior change or document local DB unavailability after using the safe local path.
- [x] 5.4 Update offline acceptance coverage if boundary or SOC briefing contracts change.

## 6. Verification

- [x] 6.1 Run Python compilation for modified files.
- [x] 6.2 Run focused SOC briefing tests.
- [x] 6.3 Run focused Repo Assistant tests.
- [x] 6.4 Run PostgreSQL-backed async workflow tests from `anakin-async-workflow-execution`.
- [x] 6.5 Run affected frontend tests and production build if frontend changes.
- [x] 6.6 Run offline AI acceptance harness.
- [x] 6.7 Run `git diff --check`.
- [x] 6.8 Run strict OpenSpec validation for both current changes.
- [x] 6.9 Capture `git status --short`.
