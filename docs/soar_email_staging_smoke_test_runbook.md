# SOAR Email Staging Smoke Test Runbook

This runbook validates guarded Email real mode in staging only. It must not be used for
production enablement without a separate approval and captured staging evidence.

## Safety Gates

- `INTEGRATION_MODE=real`
- `SOAR_ENV=staging`
- `SOAR_REAL_EMAIL_ENABLED=true`
- `SMTP_HOST` and `SMTP_USERNAME` configured
- `SMTP_PASSWORD` stored only in environment or secret manager, never in git, logs, audit output,
  delivery metadata, or screenshots
- `SMTP_FROM_EMAIL` and `SMTP_TO_EMAIL` set to staging-only addresses
- Test playbook contains exactly one `notify_email` step and no remediation actions

## Preflight

1. Confirm the VM/live environment is staging, not production.
2. Confirm no Slack, Teams, webhook, firewall, ingest, detection, or correlation changes are part
   of the test.
3. Confirm `/integrations/status` reports Email `real_mode_ready=true` and does not expose
   `SMTP_HOST`, `SMTP_USERNAME`, or `SMTP_PASSWORD`.
4. Confirm `EMAIL_MAX_SENDS_PER_MINUTE` is conservative. Default is 10.
5. Confirm `EMAIL_TIMEOUT_SECONDS` is set or accept the default 10 seconds.

## Execution

1. Create or select a staging-only playbook with one step:

   ```json
   [{"action": "notify_email", "params": {"subject": "SOAR staging Email smoke test", "body": "staging validation only"}}]
   ```

2. Run exactly one pending playbook execution through the normal executor path.
3. Confirm exactly one email arrives at `SMTP_TO_EMAIL`.
4. Confirm `notification_delivery_attempts` has exactly one Email row for the execution.
5. Confirm the row status is `success`, mode is `real`, and metadata contains no SMTP values.
6. Confirm the audit event is `SOAR_REAL_ADAPTER_ATTEMPT` and contains safe metadata only.

## Rollback

1. Unset `SOAR_REAL_EMAIL_ENABLED`.
2. Remove `SMTP_HOST`, `SMTP_USERNAME`, `SMTP_PASSWORD`, `SMTP_FROM_EMAIL`, and `SMTP_TO_EMAIL`
   from the runtime environment.
3. Recheck `/integrations/status`; Email must return to simulation/fail-closed mode.

## Abort Conditions

- More than one email is sent for one execution.
- Any SMTP credential, host, username, password, or raw payload appears in logs, audit details,
  API output, steps log, or delivery metadata.
- Any non-Email adapter performs a real outbound action.
- Any schema, frontend, VM, ingest, detection, or correlation change is required.
