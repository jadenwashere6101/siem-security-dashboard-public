# Proposal: SOC Briefing Reliability And Assistant Boundaries

## Summary

Fix the remaining live Anakin defects after the async workflow work:

- make SOC briefing manual/timer execution reliable when a run is retried or recovered;
- make timer-based worker health truthful instead of treating a one-shot timer as offline between invocations;
- prevent the Repo Architecture Assistant from answering live SIEM operational-data questions using repository context.

This change does not redesign the six canonical Anakin workflows. It only hardens SOC Briefing reliability and Repo Assistant scope boundaries.

## Motivation

Production diagnosis showed manual SOC briefing job `#3` failed because the worker retried step persistence and hit `UniqueViolation` for `(run_id, step_index) = (3, 13)`. Stale recovery later marked the job failed and no usable briefing was persisted. The UI also reported the timer-driven worker as offline when it was merely not running between scheduled one-shot executions.

The Repo Assistant also answered “What is my most severe alert?” from repository context. That assistant is functioning for codebase questions, but it needs a fail-closed boundary for live SIEM-data questions.

## Goals

- Make SOC briefing run-step persistence idempotent and deterministic.
- Preserve auditability of real step transitions while preventing duplicate step-index writes.
- Make stale recovery distinguish abandoned, active leased, retryable, terminal, and normal timer-waiting states.
- Expose timer-aware worker health states such as `healthy_waiting`, `recently_successful`, `running`, `stale`, `failed`, and `timer_inactive`.
- Preserve manual Run Now queueing and lifecycle visibility without running long AI work inside Gunicorn.
- Ensure successful manual runs refresh/open the produced briefing through existing APIs.
- Add Repo Assistant live-data boundary detection that avoids repository retrieval for operational SIEM questions.
- Preserve RBAC, local-only Ollama, no paid fallback, PostgreSQL durability, no automatic SOC actions, and bounded duplicate prevention.

## Non-Goals

- No redesign of six Anakin workflows.
- No migration unless required by implementation.
- No VM access, deployment, runtime config change, commit, push, model install, or production mutation.
- No silent auto-routing from Repo Assistant into live SIEM workflows.

## Production Completion Gate

This change follows `docs/anakin-production-acceptance-policy.md`. Automated tests, builds, and offline acceptance are necessary but not sufficient. Until deployed browser-path verification through `/siem/` is performed, completion wording must be:

```text
Implementation complete; production behavior unverified.
```
