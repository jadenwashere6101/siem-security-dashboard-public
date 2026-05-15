# SOAR Slack Staging Smoke-Test Runbook

**Scope: STAGING ONLY. This runbook must not be followed in any other environment.**

Before editing this file or any referenced integration code, inspect nearby `# spec:` tags
and `openspec/spec-index.md` to understand which OpenSpec changes govern the behavior being
tested. Active changes at time of writing:

- `openspec/changes/add-soar-real-slack-smoke-test-checklist/`
- `openspec/changes/add-soar-real-slack-readiness/`
- `openspec/changes/add-soar-real-notification-delivery-tracking/`

---

## 1. Purpose

This runbook governs the first controlled, manual Slack notification from the SOAR simulation
layer in a staging environment. Its goal is to verify that the four-guard real-mode path
works as designed — one message sent, delivery record created, circuit breaker healthy, all
other adapters untouched — and that the system returns to simulation mode immediately after.

This document is **documentation only**. It does not modify code, tests, schema, queues,
adapters, or any integration behavior. It does not send a Slack message by itself.

**Default mode must return to simulation immediately after the test is complete.**

---

## 2. Preconditions

All of the following must be true before starting. Stop and resolve any item that is not met.

| # | Precondition | Required state |
|---|---|---|
| 1 | Environment identity | Host, deployment target, database connection, and app URL are confirmed staging. No production Slack channel is attached to the webhook. |
| 2 | Approval | A super_admin or operator has explicitly approved this single controlled test. Approver name, operator name, timestamp, and staging environment label are recorded (without secrets). |
| 3 | Playbook prepared | A test-only playbook exists in the staging database containing **exactly one step**: `notify_slack`. No `block_ip`, `block_firewall`, `notify_email`, `notify_webhook`, `notify_teams`, or any remediation step is present. Message text is non-sensitive (e.g. `SOAR staging Slack smoke test`). |
| 4 | No active duplicate execution | No `pending`, `running`, or `awaiting_approval` execution exists for the same playbook/alert pair before the test starts. |
| 5 | Automated tests are no-network | All automated tests continue to mock or block the outbound Slack HTTP path. No test sets `SOAR_REAL_SLACK_ENABLED=true` with a real webhook URL. |
| 6 | Rollback procedure understood | The operator has read Section 6 (Rollback) before starting. |
| 7 | Secret delivery method confirmed | The staging `SLACK_WEBHOOK_URL` is available through the approved secret manager (Vault, AWS Secrets Manager, or runtime injection). It will not be pasted into a terminal, ticket, prompt, or log. |

---

## 3. Required Environment Variables (Placeholders Only)

Set **all four** simultaneously in the staging runtime. If any one is absent or wrong, the
adapter falls back to simulation and no real message is sent.

```bash
INTEGRATION_MODE=real
SOAR_ENV=staging
SOAR_REAL_SLACK_ENABLED=true
SLACK_WEBHOOK_URL=<retrieve-from-approved-secret-manager-do-not-paste>
```

**Rules that apply to `SLACK_WEBHOOK_URL` at all times:**

- Retrieve only through approved secret manager (Vault, AWS Secrets Manager, K8s secret mount, or equivalent).
- Never print, echo, or log the value.
- Never paste into a terminal that keeps history, a ticket, a chat message, a prompt, or a commit.
- Never store in the database, `steps_log`, delivery records, or any API response.
- If the value appears anywhere unexpected, treat it as a secret exposure incident.
- Operators may record `SLACK_WEBHOOK_URL configured: yes` — never the value itself.

**Optional tuning (safe defaults apply if unset):**

```bash
SLACK_TIMEOUT_SECONDS=3   # default: 3 — do not increase for smoke test
```

**Never set for this test:**

```bash
# These must remain unset or false during a Slack-only smoke test:
SOAR_REAL_TEAMS_ENABLED    # must be unset or false
TEAMS_WEBHOOK_URL          # must be unset
```

---

## 4. Preflight Checks

Run these in order before injecting real env vars. All must pass.

### 4.1 Confirm Staging Identity

Verify that the following all point to staging resources, not production:

- Application host / base URL
- Database host and database name
- Slack webhook destination channel (should be a staging/test channel, not a live SOC channel)

### 4.2 Confirm Default Simulation Mode

With `INTEGRATION_MODE` unset or set to `simulation` (before injecting real vars):

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/integrations/status | jq .
```

Expected response (abbreviated):

```json
{
  "configured_mode": "simulation",
  "mode": "simulation",
  "real_mode_enabled": false,
  "adapters": [
    { "name": "slack", "mode": "simulation", "real_mode_ready": false },
    { "name": "teams", "mode": "simulation" },
    { "name": "email", "mode": "simulation" },
    { "name": "firewall", "mode": "simulation" },
    { "name": "webhook", "mode": "simulation" }
  ]
}
```

**Stop if:** `real_mode_enabled` is `true`, any non-Slack adapter shows `mode: real`, or any
webhook URL value appears anywhere in the response.

### 4.3 Confirm Slack Circuit Breaker is `closed`

From the same `/integrations/status` response, check the Slack adapter entry:

```json
{
  "name": "slack",
  "circuit_breaker": {
    "state": "closed",
    "consecutive_failures": 0
  }
}
```

**Stop if:** Circuit breaker state is `open`, `half_open`, or absent. Resolve the circuit
breaker state explicitly (see Section 6, step CB-1) before proceeding.

### 4.4 Confirm Test Playbook Shape

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/playbooks/<TEST_PLAYBOOK_ID> | jq '{id, steps}'
```

Verify:

- Exactly one step with `"action": "notify_slack"`.
- No `block_ip`, `block_firewall`, `notify_email`, `notify_webhook`, `notify_teams`, or
  `require_approval` step is present.
- `enabled: true`.
- Message text is non-sensitive.

### 4.5 Confirm No Active Duplicate Execution

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     "https://$STAGING_APP_HOST/playbook-executions?playbook_id=<TEST_PLAYBOOK_ID>&status=pending" | \
     jq '.executions | length'
```

Must return `0`. Stop if any `pending`, `running`, or `awaiting_approval` execution exists.

### 4.6 Record Pre-Test Approval Evidence

Record the following **without recording any secrets**:

```
Approver:              <name>
Operator:              <name>
Timestamp (ISO 8601):  <e.g. 2026-05-15T14:30:00Z>
Staging env label:     <e.g. staging-us-west-2>
Git revision:          <output of: git rev-parse --short HEAD>
SLACK_WEBHOOK_URL:     configured (yes/no) — value not recorded
```

---

## 5. Exact Smoke-Test Steps

Execute in order. Do not skip steps. Do not proceed if any step fails.

### Step 1 — Inject Real-Mode Environment Variables

Load the webhook URL from the approved secret manager. Example using HashiCorp Vault:

```bash
export SLACK_WEBHOOK_URL=$(vault kv get -field=webhook_url secret/soar/staging/slack)
export INTEGRATION_MODE=real
export SOAR_ENV=staging
export SOAR_REAL_SLACK_ENABLED=true
```

Do not `echo $SLACK_WEBHOOK_URL`. Do not print or log it.

### Step 2 — Reload Runtime (if Required)

If the staging runtime caches environment variables at startup, perform the minimum required
reload (e.g. rolling pod restart, gunicorn reload signal, or uvicorn restart). Skip if the
runtime picks up env changes without restart.

### Step 3 — Verify Slack Real-Mode Readiness

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/integrations/status | jq .
```

Check the Slack adapter entry. All of the following must be true:

```json
{
  "name": "slack",
  "mode": "real",
  "configured_mode": "real",
  "slack_configured": true,
  "real_mode_allowed": true,
  "real_mode_ready": true,
  "webhook_configured": true,
  "circuit_breaker": { "state": "closed" },
  "supported_actions": ["notify_channel", "send_message"]
}
```

Also verify:

- No webhook URL value appears anywhere in the response body.
- All non-Slack adapters (teams, email, firewall, webhook) still show `"mode": "simulation"`.
- `real_mode_enabled: true` appears at the top level (expected when `INTEGRATION_MODE=real`).

**Stop if** any check fails. Do not proceed to execution.

### Step 4 — Trigger One Manual Playbook Execution

**Option A — Manual executor script (preferred for controlled one-shot runs):**

```bash
# From the repo root on the staging host:
python3 scripts/run_playbook_executor_once.py --batch-size 1
```

This processes exactly one eligible `pending` execution row and exits.

**Option B — Resume an approved `awaiting_approval` execution via API:**

```bash
curl -s -X POST \
     -H "Authorization: Bearer $STAGING_TOKEN" \
     -H "Content-Type: application/json" \
     https://$STAGING_APP_HOST/playbook-executions/<EXECUTION_ID>/resume
```

Record the `execution_id` returned or used.

### Step 5 — Poll Until Terminal Status

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/playbook-executions/<EXECUTION_ID> | \
     jq '{id, status, last_completed_step}'
```

Repeat until `status` is one of: `success`, `failed`, `abandoned`. Do not loop indefinitely —
if status does not reach a terminal state within a reasonable window (e.g. 2 minutes), stop
and treat as a failure.

### Step 6 — Confirm Exactly One Slack Message

Check the staging Slack channel manually:

- Exactly **1** message received.
- Message text matches the expected test content (e.g. `SOAR staging Slack smoke test`).
- No sensitive content in the message body.

**Stop and mark FAILED if:** 0 messages, >1 message, or unexpected content.

### Step 7 — Capture Evidence (see Section 8 for full checklist)

Capture all evidence listed in Section 8 before rolling back. Evidence must not contain any
webhook URL value, request headers, tokens, or raw HTTP response bodies.

### Step 8 — Roll Back to Simulation Immediately

Follow Section 6 (Rollback) in full before closing the session.

---

## 6. Rollback Steps

Perform these immediately after evidence capture, regardless of pass or fail.

### Standard Rollback

```bash
# Remove real-mode variables:
unset INTEGRATION_MODE
unset SLACK_WEBHOOK_URL
unset SOAR_REAL_SLACK_ENABLED

# Or set explicitly to simulation:
export INTEGRATION_MODE=simulation
export SOAR_REAL_SLACK_ENABLED=false
```

Reload the runtime if required (same procedure as Step 2 above).

Verify rollback:

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/integrations/status | jq '{mode, real_mode_enabled}'
```

Expected:

```json
{
  "mode": "simulation",
  "real_mode_enabled": false
}
```

Also confirm Slack adapter shows `"mode": "simulation"` and `"real_mode_ready": false`.

Clear shell history lines that may contain the webhook URL:

```bash
history -d <line-number>   # zsh: use fc -p and edit ~/.zsh_history manually
# Or clear full session history if the URL was echoed:
history -c
```

### Emergency Rollback (Unexpected Slack Behavior)

If more than one message is sent, unexpected content appears, or the adapter behaves
unexpectedly, perform in this order:

**CB-1 — Force-open the Slack circuit breaker** (blocks all further Slack calls immediately):

```bash
curl -s -X POST \
     -H "Authorization: Bearer $STAGING_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Emergency rollback: unexpected smoke test behavior"}' \
     https://$STAGING_APP_HOST/integrations/slack/circuit-breaker/force-open
```

**CB-2 — Remove real-mode variables and reload** (standard rollback above).

**CB-3 — Verify simulation restored** (standard rollback verification above).

**CB-4 — Reset circuit breaker after simulation is confirmed:**

```bash
curl -s -X POST \
     -H "Authorization: Bearer $STAGING_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Post-rollback reset after emergency force-open"}' \
     https://$STAGING_APP_HOST/integrations/slack/circuit-breaker/reset
```

---

## 7. Evidence Checklist

Capture the following immediately after Step 7 and before rollback (or immediately after
rollback if capturing post-rollback state). Store evidence without any secrets.

| # | Evidence item | How to capture | Key fields to verify |
|---|---|---|---|
| E1 | Test metadata | Record manually | Approver, operator, timestamp (ISO 8601), staging env label, git SHA |
| E2 | Integration status — before real-mode injection | Save `/integrations/status` response | `mode: simulation`, `real_mode_enabled: false`, all adapters simulation |
| E3 | Integration status — after real-mode injection | Save `/integrations/status` response | Slack `real_mode_ready: true`, `webhook_configured: true`, no URL value, all other adapters `mode: simulation` |
| E4 | Circuit breaker state — before test | From E3 response `.adapters[slack].circuit_breaker` | `state: closed`, `consecutive_failures: 0` |
| E5 | Playbook execution record | `GET /playbook-executions/<EXECUTION_ID>` | `status: success`, `playbook_id`, `execution_id` |
| E6 | `steps_log` excerpt | From E5 response `.steps_log[0]` | `action: notify_slack`, `success: true`, `simulated: false`, `mode: real`, no webhook URL |
| E7 | Notification delivery attempt record | `GET /notification-deliveries?playbook_execution_id=<ID>` | `provider: slack`, `mode: real`, `status: success`, `correlation_id`, no webhook URL in metadata |
| E8 | Notification delivery metrics | `GET /metrics/notifications` | Counts updated, no secrets |
| E9 | Circuit breaker state — after test | From post-execution `/integrations/status` | `state: closed` (success keeps it closed) |
| E10 | Slack channel confirmation | Screenshot or text note | Exactly 1 message, expected content, timestamp |
| E11 | Rollback verification | Save `/integrations/status` after unset | `mode: simulation`, `real_mode_enabled: false`, Slack `real_mode_ready: false` |

**Do not capture:**

- `SLACK_WEBHOOK_URL` value.
- Request headers or tokens.
- Raw Slack webhook HTTP response body if it echoes request metadata.
- Shell command history lines containing the webhook URL.
- Production Slack channel identifiers if considered sensitive.

---

## 8. Pass / Fail Criteria

### Pass — All of the following must be true

- [ ] Test ran in a confirmed staging environment.
- [ ] All four required env vars were set via approved runtime configuration only.
- [ ] Preflight checks passed in full before execution (Sections 4.1–4.6).
- [ ] Integration status showed Slack `real_mode_ready: true` with safe booleans only; no webhook URL in response.
- [ ] All non-Slack adapters showed `mode: simulation` throughout the test.
- [ ] Playbook execution reached `status: success`.
- [ ] Exactly **one** Slack message arrived in the expected staging channel.
- [ ] `steps_log` shows `notify_slack` step completed with `success: true`, `simulated: false`, `mode: real`, no webhook URL.
- [ ] At least one `notification_delivery_attempts` record exists for the execution with `status: success` and no webhook URL in metadata.
- [ ] Circuit breaker remained `closed` before and after the test.
- [ ] No real firewall, email, generic webhook, Teams, or PagerDuty call was made.
- [ ] No subprocess call, `blocked_ips` mutation, queue redesign, scheduler, daemon, or autonomous retry behavior occurred.
- [ ] Rollback to simulation was completed and verified (E11 captured).
- [ ] No webhook URL appeared in logs, UI, status output, audit output, evidence, or prompts.

### Fail — Stop immediately if any of the following is true

- [ ] Environment identity is not clearly staging.
- [ ] Any required env var is missing at execution time.
- [ ] Integration status shows `real_mode_ready: false` for Slack when all four vars are set.
- [ ] Webhook URL value appears in any log, API response, `steps_log`, delivery record, or terminal output.
- [ ] Any non-Slack adapter shows `mode: real` at any point.
- [ ] Slack circuit breaker is `open`, `half_open`, or absent before execution.
- [ ] Zero Slack messages received (delivery silently dropped).
- [ ] More than one Slack message received (deduplication failure).
- [ ] Unexpected Slack message content or destination.
- [ ] Any real firewall, email, webhook, Teams, or PagerDuty action occurred.
- [ ] Rollback to simulation cannot be verified.
- [ ] Shell history cannot be cleared of the webhook URL.

---

## 9. Safety Warnings

> **STAGING ONLY.** This runbook must never be used against a production environment,
> local development, CI, or any environment where the Slack destination is a live SOC channel
> or production workspace.

> **ONE CONTROLLED SEND.** The smoke test covers exactly one playbook execution with exactly
> one `notify_slack` step. Do not loop, retry manually, replay, or trigger additional
> executions during the same session.

> **WEBHOOK URL IS A SECRET.** Treat `SLACK_WEBHOOK_URL` with the same care as a database
> password. Never echo, print, log, paste, or commit it. If it appears unexpectedly anywhere,
> treat it as a secret exposure and rotate the webhook immediately.

> **NO NETWORK CALLS IN AUTOMATED TESTS.** Do not run the automated test suite with
> `SOAR_REAL_SLACK_ENABLED=true`. Tests mock or block outbound Slack HTTP. Using a real
> webhook in tests would send messages on every test run and introduce environment coupling.

> **ROLLBACK IS MANDATORY.** Default simulation mode must be restored and verified before
> the session ends, regardless of whether the test passed or failed.

> **CIRCUIT BREAKER MUST BE `closed` BEFORE EXECUTION.** If the breaker is `open` or
> `half_open` before the test starts, an outbound call may be blocked or produce unexpected
> behavior. Resolve circuit breaker state before proceeding (see Preflight 4.3).

> **DO NOT SKIP PREFLIGHT CHECKS.** Each preflight check prevents a specific failure mode.
> Skipping any check removes a safety layer that was deliberately designed into the system.

---

## 10. Out-of-Scope Integrations

The following integrations remain **simulation-only** and are out of scope for this runbook
and for any test session following it. They must not be real-enabled, connected to real
endpoints, or invoked with live credentials under any circumstances, regardless of what
`INTEGRATION_MODE` is set to.

| Integration | Status | Constraint |
|---|---|---|
| Real firewall / `block_ip` (live) | Out of scope | `LinuxFirewallDryRunAdapter` is dry-run only; no subprocess, no real firewall API |
| Email (SMTP / SendGrid) | Out of scope | `email_adapter.py` simulation-only; no SMTP host or credentials configured |
| Generic webhook | Out of scope | `webhook_adapter.py` simulation-only regardless of `INTEGRATION_MODE` |
| PagerDuty | Out of scope | Not implemented; no adapter or credentials exist |
| Microsoft Teams | Out of scope for this runbook | Covered by a separate runbook (`add-soar-real-teams-smoke-test-checklist`); Slack and Teams readiness are independent |

Enabling any of the above for real execution requires a separate approved design and its own
staged runbook. They must not be enabled as a side effect of this Slack smoke test.

The `integration_registry.py` module enforces simulation-only mode for email, firewall, and
webhook adapters at the code level (`routes/integration_routes.py:50–62`), regardless of
`INTEGRATION_MODE`. This is a code-level safety constraint, not just operational policy.

---

## Quick Reference

```
Preflight API:   GET  /integrations/status
Execution:       python3 scripts/run_playbook_executor_once.py --batch-size 1
                 POST /playbook-executions/<id>/resume
Execution poll:  GET  /playbook-executions/<id>
Delivery record: GET  /notification-deliveries?playbook_execution_id=<id>
Metrics:         GET  /metrics/notifications
CB force-open:   POST /integrations/slack/circuit-breaker/force-open   { "reason": "..." }
CB reset:        POST /integrations/slack/circuit-breaker/reset         { "reason": "..." }
CB half-open:    POST /integrations/slack/circuit-breaker/enable-half-open { "reason": "..." }

All circuit breaker control endpoints: super_admin only, require non-empty reason field.
```
