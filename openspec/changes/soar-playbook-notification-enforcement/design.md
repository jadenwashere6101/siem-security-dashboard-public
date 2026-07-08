## Overview

`soar-playbook-notification-enforcement` consumes the durable Active/Inactive state planned by `soar-notification-provider-active-controls` and applies it at playbook execution time. The executor must check policy before notification adapter execution for Slack, Teams, Email, and Webhook. Active providers follow the current delivery path. Inactive providers are skipped by policy with explicit evidence and without pretending a notification was Delivered.

## Terminology

Use the parent roadmap terms exactly:

- **Configured**: required env vars/secrets for a provider are present.
- **Tested**: a manual test notification through that provider succeeded.
- **Active**: a human has explicitly allowed playbooks to use this provider for real delivery.
- **Delivered**: a real notification was actually sent successfully.
- **Simulation**: no external call was made at all.

Code existing for a provider is not evidence that the provider is Configured, Tested, Active, or Delivered.

## Audit Summary

- `engines/playbook_step_executor.py` defines `_NOTIFICATION_ACTIONS` for `notify_slack`, `notify_teams`, `notify_email`, and `notify_webhook`, with `_PROVIDER_FOR_ACTION` mapping those actions to `slack`, `teams`, `email`, and `webhook`.
- `_simulate_adapter_step()` currently checks `_existing_active_delivery()` before adapter execution. That helper is an idempotency check for existing `success`/`pending` delivery rows, not provider Active state.
- Notification steps call `execute_playbook_simulated_adapter()`, which resolves the registered adapter. In real integration mode, Slack/Teams/Email/Webhook can execute guarded real sends; in simulation mode they return simulated no-send results.
- Slack, Teams, Email, and Webhook adapters all preserve the existing fail-closed real-mode guard model: deployment mode, `SOAR_ENV`, per-provider enable flag, required configuration, rate limiting, timeout handling, failure classification, and real-attempt audit logging.
- `_record_notification_delivery_attempt()` appends delivery rows after notification adapter execution when the step was not skipped. It maps adapter success/failure to `success`, `failed`, `timeout`, or `blocked`.
- `notification_delivery_attempts` currently allows `pending`, `success`, `failed`, `timeout`, and `blocked`; it has no `skipped` status.
- Playbook step entries already support `status: "skipped"` for approval-gate skips, and `PlaybooksPanel.js` renders `steps_log` timeline cards plus notification delivery history.
- `response_actions_queue` is separate from playbook notification delivery. It already has `skipped` queue status and retry accounting for response actions, but notification steps do not enqueue queue rows.
- Playbook execution retry/recovery is lease/stale-execution based through `playbook_executions.attempt_count`, `max_attempts`, and stale running recovery. Adapter-level notification failures do not create an endless per-step retry loop.
- The prior Active-controls child spec plans `notification_provider_controls` with providers `slack`, `teams`, `email`, and `webhook`; all providers default inactive and missing rows are treated inactive.

## Active-State Lookup

Implementation should add a small backend helper in the provider-control ownership area from `soar-notification-provider-active-controls` and call it from the executor. The executor should request policy for the canonical provider key before resolving params or calling the adapter, after duplicate-delivery idempotency has been checked.

Expected lookup behavior:

- Return `active=true|false` for `slack`, `teams`, `email`, and `webhook`.
- Treat missing provider-control rows as inactive.
- Reject or ignore `firewall`; firewall is not in notification enforcement scope.
- Return a safe structured error if the provider-control table cannot be read.

## Executor Behavior

### Active Provider

When provider Active state is true:

- Continue the existing adapter execution path.
- Preserve `_existing_active_delivery()` idempotency behavior.
- Preserve param binding, adapter env guards, real-mode fail-closed behavior, rate limits, timeout handling, delivery attempt logging, response-outcome logging, and dead-letter behavior.
- Keep existing failure semantics: adapter failure remains a failed step unless the playbook step explicitly uses `on_failure: "continue"`.

### Inactive Provider

When provider Active state is false:

- Do not resolve provider delivery params if doing so is not needed for policy evidence.
- Do not call Slack, Teams, SMTP, generic Webhook, or adapter execution code.
- Append a step entry with `status: "skipped"`, `event: "notification_skipped_by_policy"`, `skipped: true`, `mode: "simulation"`, `simulated: true`, `executed: false`, `output.skip_reason: "provider_inactive"`, and provider metadata that contains no secrets.
- Record a response outcome event with an execution state such as `skipped`, reason code `provider_inactive`, `external_executed=false`, and `simulated=true`.
- Record delivery evidence if the implementation adds a supported `skipped` delivery status; otherwise rely on the step log and response outcome event until `notification_delivery_attempts` can represent skipped policy outcomes honestly.
- Do not mark the step as `success`.
- Do not create a retryable failure or dead letter for the inactive policy path.
- Continue unrelated later steps by default. If a playbook explicitly requires the notification, it may use a future/explicit contract such as `required: true` or existing failure/branch semantics, but this spec should not invent broad coupling that blocks unrelated steps.

### Provider Status Cannot Be Read

If Active state cannot be read because storage is unavailable, schema is missing, or the helper raises an unexpected error:

- Fail closed by not attempting external delivery.
- Record a skipped or failed-safe policy outcome distinct from Inactive, for example `notification_policy_unavailable`.
- The recommended step status is `skipped` with `output.skip_reason: "provider_policy_unavailable"` and an operator-visible message, because this is a control-plane failure rather than a provider delivery failure.
- Do not retry the notification step in a tight loop. Existing execution-level retry/recovery must not turn policy-read failure into endless delivery attempts.
- Do not log secrets.

## Delivery Logging

Preferred implementation is to extend `notification_delivery_attempts.status` and `core.notification_delivery_store._VALID_STATUSES` with `skipped`, then create an append-only delivery row for inactive providers:

- `mode="simulation"` because no external call was made.
- `status="skipped"`.
- `failure_code="provider_inactive"` for inactive providers, or `failure_code="provider_policy_unavailable"` when status cannot be read.
- `metadata` includes safe fields such as `provider_active=false`, `skip_reason`, `policy_source`, `adapter_mode`, `simulated=true`, and `executed=false`.
- `idempotency_key` should continue to identify the execution/step/provider so repeated executor runs do not create unbounded duplicate skip rows.

If migration risk is judged too high during implementation, the minimum acceptable fallback is a step-log entry plus response-outcome event only. The implementation must not force inactive policy skips into `success`, `failed`, `timeout`, or `blocked`.

## Frontend Display

`frontend/src/components/PlaybooksPanel.js` already renders execution `steps_log` timeline cards and notification delivery history. Implementation should update this only if current rendering cannot clearly communicate skipped-by-policy.

Expected display:

- Show `skipped-by-policy` or equivalent clear wording for `notification_skipped_by_policy`.
- Show provider and reason without secret values.
- Do not render provider Active/Inactive toggles here; those belong to `soar-notification-provider-active-controls`.
- Do not add manual test-send buttons.

## Database Changes

This spec should not create the provider Active-state table. It must read the durable state created by the prior Active-controls child.

Potential database change:

- Add `skipped` to `notification_delivery_attempts.status` check constraint if delivery attempts are used for policy skips.

No delivery-history dashboard schema should be added here.

## Firewall Boundary

Firewall remains simulation/dry-run only. This spec must not add real firewall execution, real firewall Active/Inactive enforcement, subprocess calls, API calls, blocklist mutation, or firewall provider controls.

## Testing Strategy

- Backend executor tests for Active provider path preserving existing delivery behavior and adapter calls.
- Backend executor tests for Inactive Slack, Teams, Email, and Webhook paths ensuring no adapter/network/send function is called.
- Tests that inactive policy creates a skipped step entry and response outcome without fake success.
- Tests that inactive policy does not create dead letters or retry loops.
- Tests that unrelated subsequent steps continue after an inactive notification skip.
- Tests for provider-policy-read failure fail-closed behavior.
- Store/migration tests if `notification_delivery_attempts.status` gains `skipped`.
- Frontend tests only if PlaybooksPanel rendering is updated, covering skipped-by-policy display and secret safety.

All tests must mock external providers; no test may contact Slack, Teams, SMTP, generic webhook endpoints, Firewall, VM, or Azure.
