## Context

The legacy response-action worker is timer-invoked and simulation-only, but currently exits 127 because its wrapper shell-sources a non-shell-safe SMTP secret. One queue row is stranded, while dead-letter and approval tables contain substantial operational backlog. Separately, live worker environments prove that source-controlled unit-level `Environment=` values do not provide the advertised safety override. The VM is deployment/runtime only; durable files must be changed on the Mac and deployed normally.

## Goals / Non-Goals

**Goals:**

- Recover worker health without exposing secrets or changing intended execution modes.
- Make the real-delivery kill-switch empirically testable and document its authoritative configuration layer.
- Terminally disposition stuck queue work and operational backlogs with auditable evidence.
- Preserve data, provide rollback checkpoints, and hand durable changes to the Mac AI.

**Non-Goals:**

- Editing source-controlled files on the VM, merging a dirty VM, or committing/pushing.
- Enabling Teams, firewall enforcement, or real behavior for advisory legacy actions.
- Blindly replaying all dead letters or deleting history.

## Decisions

1. **Preflight before mutation.** Capture VM git cleanliness, effective unit definitions, service/timer state, sanitized process environment, journal failure, and DB counts/record details. Secret values are never printed. This creates rollback evidence and catches drift.
2. **Repair the runtime secret at its authoritative secret store.** Replace the malformed assignment using a shell-safe representation compatible with the current launcher, validate parsing without echoing values, then restart one bounded worker invocation. The alternative—editing the wrapper on the VM—is prohibited.
3. **Treat kill-switch behavior as unproven until observed.** Determine whether `.env`, `EnvironmentFile`, explicit unit values, or the wrapper wins at exec time. Test in a maintenance window using non-delivering readiness checks and sanitized `/proc`/service evidence. If source changes are needed, stop that branch and create a precise Mac handoff.
4. **Disposition records individually and idempotently.** Inspect queue item 77 and each backlog cohort before retry. Retry only transient, still-relevant, safe work within a bounded batch; dismiss/expire obsolete or permanent failures with recorded reasons. Never mass-delete or manufacture success.
5. **Approval backlog is operational work.** Resolve the single pending request according to age/policy, analyze expiry causes, and recommend notification/SLA/runbook improvements; historical expired rows remain evidence.

## Risks / Trade-offs

- [Secret repair changes email authentication] → validate syntax and worker startup without sending or logging the secret; retain a protected backup/rollback method.
- [Retry duplicates an external side effect] → verify idempotency and delivery history before retrying; default uncertain records to manual review.
- [Kill-switch test interrupts real notifications] → use a maintenance window, bounded duration, explicit restore, and end-to-end post-restore smoke checks.
- [Legacy worker recovery creates confidence in a frozen path] → document that the playbook engine remains authoritative and the queue worker remains simulation-only.

## Migration Plan

1. Record preflight evidence and confirm the VM repository is clean before any sync; no sync is required for this spec-only change.
2. Correct runtime secret syntax, validate parsing, restart the response worker/timer, and observe multiple timer intervals.
3. Validate configuration precedence and kill-switch behavior; restore intended real values after the test.
4. Classify and disposition item 77, then dead-letter and approval cohorts in bounded batches.
5. Record postflight counts, service health, real/simulation guard state, and unresolved handoffs.
6. Roll back by restoring the protected config value and prior effective service configuration, daemon-reloading if required, restarting services, and confirming the intended mode. Never roll back by deleting DB evidence.

## Open Questions

- Which exact launcher behavior causes unit values to lose to `.env` at exec time?
- Which dead-letter failure classes are demonstrably transient and idempotent on the live dataset?
- What operational SLA and ownership should govern approvals and dead letters after cleanup?
