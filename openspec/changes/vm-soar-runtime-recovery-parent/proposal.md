## Why

Production SOAR runtime operations are degraded by a crash-looping legacy worker, a stuck response action, ineffective systemd safety overrides, and unmanaged dead-letter and approval backlogs. These conditions require a controlled VM maintenance plan that restores health without violating the Mac-as-source-of-truth boundary or changing intentionally simulated integrations.

## What Changes

- Repair the VM-only secret/configuration defect that makes `soar-response-action-worker.service` fail while keeping secrets out of logs and source control.
- Establish and test an authoritative, observable incident kill-switch for real notification delivery; do not claim safety from ineffective unit overrides.
- Restore worker health, safely classify and drain queue item 77, and verify that no response action remains indefinitely pending.
- Triage open/retrying dead letters and pending/expired approvals using documented disposition rules, evidence preservation, bounded retries, and explicit escalation.
- Produce before/after runtime evidence, rollback instructions, and a Mac-AI handoff for every durable source/template change discovered.
- Preserve Slack, Email, and Webhook real-mode intent and preserve Teams, firewall/block_ip, monitor, and flag_high_priority simulation-only behavior.

## Capabilities

### New Capabilities

- `soar-runtime-recovery-operations`: Controlled recovery, queue draining, backlog triage, kill-switch validation, rollback, and evidence requirements for the production VM.

### Modified Capabilities

- `soar-worker-orchestration`: Workers must have a verified configuration precedence model, health criteria, and an operationally trustworthy real-delivery kill-switch.
- `response-action-queue-worker-rollout`: Pending legacy queue work must be explicitly classified and terminally dispositioned rather than remaining indefinitely pending.

## Impact

This parent change governs the deployment VM, systemd effective configuration, the runtime `.env`, worker/timer state, PostgreSQL queue/dead-letter/approval records, journals, and smoke-test evidence. It authorizes VM runtime/configuration and data operations only; source changes belong to `mac-soar-mode-accuracy-parent`. No commit, push, VM source edit, Teams activation, or firewall enforcement is included.
