## 1. Preflight and Safety Evidence

- [ ] 1.1 Confirm the VM repository path, record `git status --short`, and stop any deployment/merge branch if the VM is dirty
- [ ] 1.2 Capture effective unit definitions, service/timer status, recent journals, restart counts, and sanitized process environments for both SOAR workers and the backend
- [ ] 1.3 Capture record-level evidence for queue item 77 and aggregate/status-age counts for response actions, dead letters, and approvals before mutation
- [ ] 1.4 Record current Slack, Email, Webhook, Teams, and firewall guard/readiness state without printing secrets or sending notifications

## 2. Response Worker Recovery

- [ ] 2.1 Back up the protected runtime configuration using permissions that do not expose secrets
- [ ] 2.2 Correct the VM SMTP password assignment using a representation compatible with the current launcher and validate parsing without echoing the value
- [ ] 2.3 Run one bounded simulation-only response worker invocation and verify no shell command is interpreted from any environment value
- [ ] 2.4 Restart/enable the approved service and timer state and verify successful health across at least two scheduled invocations
- [ ] 2.5 If a tracked wrapper/unit change is required, stop source editing and create a Mac-parent handoff with reproduction evidence and acceptance criteria

## 3. Configuration Precedence and Kill-Switch

- [ ] 3.1 Trace the effective environment precedence across systemd, `EnvironmentFile`, explicit `Environment=`, and launcher behavior
- [ ] 3.2 In a maintenance window, activate the documented candidate kill-switch and prove via sanitized effective process state that all real notification guards are disabled
- [ ] 3.3 Verify blocked/non-delivering readiness behavior without transmitting a real notification
- [ ] 3.4 Restore approved real mode for Slack, Email, and Webhook while verifying Teams and firewall remain disabled
- [ ] 3.5 Record the authoritative kill-switch procedure or hand source/template corrections to the Mac parent if the candidate cannot be made reliable through runtime configuration

## 4. Queue and Backlog Remediation

- [ ] 4.1 Classify queue item 77 for relevance, safety, idempotency, and expected simulation-only outcome
- [ ] 4.2 Process or explicitly terminally disposition item 77 and verify no anomalously old pending response action remains unexplained
- [ ] 4.3 Group open/retrying dead letters by failure class, source, age, retry count, and idempotency risk
- [ ] 4.4 Retry a small canary cohort of transient safe dead letters and verify replacement work plus preserved history
- [ ] 4.5 Boundedly process remaining safe cohorts and dismiss or escalate permanent/obsolete/unsafe records with reasons; do not delete history or manufacture success
- [ ] 4.6 Resolve or escalate current pending approvals according to policy and analyze the 105-expiry pattern by playbook/action/age
- [ ] 4.7 Document approval notification, ownership, SLA, and expiry-policy improvements for any durable Mac/backend follow-up

## 5. Postflight and Handoff

- [ ] 5.1 Capture postflight service/timer health, queue/dead-letter/approval counts, sanitized mode state, and recent error journals
- [ ] 5.2 Verify Slack, Email, and Webhook remain approved-real and Teams, firewall, monitor, and flag_high_priority remain simulation-only
- [ ] 5.3 Exercise and document rollback checkpoints without deleting database evidence
- [ ] 5.4 Deliver a completion report listing every record cohort disposition, unresolved exception, Mac-parent dependency, and acceptance result
