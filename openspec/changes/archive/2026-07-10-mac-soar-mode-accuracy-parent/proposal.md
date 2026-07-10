## Why

The Playbooks UI contradicts actual execution state by describing real Slack, Email, and Webhook executions as simulations, while deployed service templates contain safety claims that the audit proved ineffective. Durable code and deployment-template corrections must be made and tested in the Mac source-of-truth repository.

## What Changes

- Make Playbooks status summaries, approval-paused messaging, subtitle/help text, and Retry/Resume actions derive terminology from normalized execution mode.
- Make timeline `approval_resumed` copy mode-aware and ensure unknown or missing mode is represented conservatively rather than falsely asserting simulation or real execution.
- Align Teams copy with the conditional real-mode language used by other notification providers without enabling Teams.
- Correct backend presentation metadata for genuine read-only enrichment work so it is not represented as fake/no-op simulation, while preserving truthful execution semantics.
- Investigate wrapper and systemd configuration precedence in source; implement a tested durable solution for shell-safe environment loading and an effective, documented notification kill-switch, or remove misleading overrides and descriptions.
- Add automated coverage and deployment/runbook handoff instructions for the VM AI.

## Capabilities

### New Capabilities

- `soar-mode-aware-presentation`: A single truthful UI vocabulary and normalization contract for real, simulation, read-only, paused, resumed, retry, and unknown execution states.
- `soar-runtime-configuration-contract`: Source-controlled worker launch and systemd templates provide deterministic environment precedence, safe secret loading, accurate descriptions, and verifiable kill-switch behavior.

### Modified Capabilities

- `playbook-engine-correctness-hardening`: Read-only enrichment outcomes expose truthful execution metadata without implying that genuine work was skipped.

## Impact

Expected source scope includes `frontend/src/components/PlaybooksPanel.js`, `PlaybookExecutionTimeline.js`, `IntegrationStatusPanel.js`, related frontend tests, backend execution metadata where required, worker launch wrappers, `deploy/systemd` unit templates, and documentation/tests. Work occurs only in the Mac repository; deployment, live `.env` edits, service restarts, and backlog mutation remain in `vm-soar-runtime-recovery-parent`. No commit or push is authorized.
