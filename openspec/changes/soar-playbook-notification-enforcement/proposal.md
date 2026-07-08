## Why

The parent roadmap `soar-notification-integration-controls-roadmap` defines Active as the human authorization that allows playbooks to use a notification provider, but the current playbook executor does not check that state before notification steps run. This child spec defines the third implementation step: make Slack, Teams, Email, and Webhook playbook notifications respect provider Active/Inactive policy without weakening existing adapter guards or treating policy skips as successful delivery.

## What Changes

- Plan executor-side Active-state lookup for `notify_slack`, `notify_teams`, `notify_email`, and `notify_webhook` before any adapter delivery attempt.
- Preserve existing adapter/env/fail-closed behavior, delivery logging, idempotency checks, rate limits, and transient/non-transient failure classification when a provider is Active.
- Define clean Inactive-provider behavior: skip by policy, record an explicit skipped-by-policy outcome, do not fake success, do not retry endlessly, and do not treat Inactive as a system failure.
- Define behavior when provider Active state cannot be read, with a fail-closed policy that avoids external sends and records an operator-visible policy-read failure.
- Plan any minimal delivery-attempt status/schema adjustment needed to represent skipped-by-policy without overloading `success`, `failed`, `timeout`, or `blocked`.
- Keep Firewall simulation/dry-run only and do not apply real Active/Inactive enforcement to firewall blocking.
- Do not add provider toggles, manual test-send buttons, delivery-history dashboards, real provider configuration, real firewall execution, VM/Azure work, commits, or pushes.

## Capabilities

### New Capabilities
- `soar-playbook-notification-enforcement`: enforces provider Active/Inactive policy for playbook notification steps and records clear delivery/step outcomes for Active, Inactive, and provider-status-read-failure paths.

### Modified Capabilities
(none)

## Impact

- **Affected backend:** planned changes to `engines/playbook_step_executor.py`, provider-control storage reads from the prior `soar-notification-provider-active-controls` child, notification delivery persistence if a skipped status is needed, and response-outcome event creation for skipped-by-policy.
- **Affected frontend:** possible updates to playbook execution/timeline display in `frontend/src/components/PlaybooksPanel.js` so skipped-by-policy is visibly distinct from success/failure.
- **Affected database:** no new provider-control table should be introduced here; this spec consumes the prior child state. A small migration may be needed only if `notification_delivery_attempts.status` must support `skipped`.
- **External systems:** no Slack, Teams, SMTP, Webhook, Firewall, VM, or Azure calls are made by this spec creation. Future implementation must keep tests mocked and must not add real firewall execution.
