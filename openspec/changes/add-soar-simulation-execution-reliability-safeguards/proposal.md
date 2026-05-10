# Proposal: SOAR Simulation Execution Reliability Safeguards

## Problem
SOAR playbook execution is currently simulation-only and manually invoked through the one-shot executor path. That is the correct safety posture before real integrations, but the execution model still needs stronger reliability safeguards before any future autonomous execution path is considered.

Simulation failures, stale `running` rows, repeated manual retries, and unclear attempt history can hide unsafe behavior until the system later gains schedulers or real integrations. Reliability controls should be designed while all actions are still simulated, because they can be tested without network calls, firewall mutation, or production side effects.

## Goal
Design simulation-only reliability safeguards for SOAR playbook executions.

## Scope
- Track execution attempt counters for playbook execution attempts.
- Surface retry or attempt count visibility in read APIs and metrics.
- Define `max_attempts` limits that fail closed when exhausted.
- Define a dead-letter style terminal state such as `permanently_failed`.
- Detect stale `running` playbook executions using metadata and explicit operator action.
- Add timeout metadata only, without background timers or automatic scheduling.
- Add metrics visibility for retries, failures, stale executions, and permanently failed executions.
- Preserve safe idempotent retry behavior and immutable execution history.
- Provide operator visibility only; no autonomous recovery or background processing.
- Add backend tests for attempt accounting, terminal limits, stale-running handling, and read-only visibility.

## Out of scope
- No implementation code in this change.
- No daemon workers.
- No automatic background retries.
- No cron, systemd, Celery, APScheduler, or scheduler integration.
- No real integrations.
- No real remediation.
- No queue redesign.
- No SOAR queue behavior changes.
- No ingest, detection, or correlation changes.
- No autonomous execution.
- No external messaging systems.
- No network calls.
- No subprocess execution.
- No mutation of `blocked_ips`.

## Why before autonomous execution
Reliability safeguards must exist before autonomous execution because autonomous workers amplify small mistakes. Without attempt limits, a stuck or repeatedly failing execution can turn into a retry storm. Without stale-running detection, crashed or interrupted runs can remain invisible or be retried unsafely. Without dead-letter style handling, permanently failing executions blend into ordinary failures and operators cannot tell which items need review rather than another retry.

Building these controls in simulation mode lets the system prove bounded retries, safe terminal states, and clear operator visibility before any path can make real Slack, email, webhook, firewall, or blocklist changes.

## Success criteria
- Playbook execution attempts are counted and visible without changing real-world state.
- Manual retries are bounded by `max_attempts`.
- Exhausted executions move to a clearly terminal dead-letter style state such as `permanently_failed`.
- Stale `running` executions are detectable and can be surfaced safely for operator review.
- Timeout data is metadata only and does not create timers, daemons, or automatic execution.
- Metrics can report retry/failure/stale/permanently-failed state.
- Existing immutable execution history is preserved.
- Tests prove no network calls, subprocess execution, queue enqueueing, `blocked_ips` writes, or ingest/detection/correlation changes are introduced.
