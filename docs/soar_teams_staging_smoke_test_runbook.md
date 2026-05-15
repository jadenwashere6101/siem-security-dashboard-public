# SOAR Teams Staging Smoke-Test Runbook

**Scope: STAGING ONLY. This runbook must not be followed in any other environment.**

**Teams and Slack are independent integrations.** This runbook governs Teams only.
Enabling Teams real mode does not affect Slack readiness. Completing a Slack smoke test
does not satisfy the requirements of this runbook, and vice versa.

Before editing this file or any referenced integration code, inspect nearby `# spec:` tags
and `openspec/spec-index.md` to understand which OpenSpec changes govern the behavior being
tested. Active changes at time of writing:

- `openspec/changes/add-soar-real-teams-smoke-test-checklist/`
- `openspec/changes/add-soar-real-teams-readiness/`
- `openspec/changes/add-soar-real-notification-delivery-tracking/`

---

## 1. Purpose

This runbook governs the first controlled, manual Teams notification from the SOAR simulation
layer in a staging environment. Its goal is to verify that the Teams four-guard real-mode
path works as designed — one message sent, delivery record created, circuit breaker healthy,
Slack and all other adapters untouched — and that the system returns to simulation mode
immediately after.

This document is **documentation only**. It does not modify code, tests, schema, queues,
adapters, or any integration behavior. It does not send a Teams message by itself.

**Default mode must return to simulation immediately after the test is complete.**

**Completing a Slack smoke test does not satisfy this runbook.** Teams readiness is checked
independently via `SOAR_REAL_TEAMS_ENABLED` and `TEAMS_WEBHOOK_URL`. Setting Slack guards
has no effect on Teams readiness. Setting Teams guards has no effect on Slack readiness.

---

## 2. Preconditions

All of the following must be true before starting. Stop and resolve any item that is not met.

| # | Precondition | Required state |
|---|---|---|
| 1 | Environment identity | Host, deployment target, database connection, and app URL are confirmed staging. No production Teams channel, production workflow, or production alert route is attached to the webhook. |
| 2 | Teams destination confirmed | The `TEAMS_WEBHOOK_URL` points to a staging or test Teams channel, not a live SOC channel or production workspace. Ownership of the destination channel is confirmed by the operator or approver. |
| 3 | Approval | A super_admin or operator has explicitly approved this single controlled test. Approver name, operator name, timestamp, and staging environment label are recorded without secrets. |
| 4 | Playbook prepared | A test-only playbook exists in the staging database containing **exactly one step**: `notify_teams`. No `block_ip`, `block_firewall`, `notify_email`, `notify_slack`, `notify_webhook`, or any remediation step is present. Message text is non-sensitive (e.g. `SOAR staging Teams smoke test`). |
| 5 | No active duplicate execution | No `pending`, `running`, or `awaiting_approval` execution exists for the same playbook/alert pair before the test starts. Only one operator will invoke the manual path. No daemon, scheduler, or run loop is active. |
| 6 | Slack independence confirmed | Slack readiness is not affected by Teams env vars. Verify `SOAR_REAL_SLACK_ENABLED` and `SLACK_WEBHOOK_URL` remain at their pre-test state. This test must not trigger a Slack send. |
| 7 | Automated tests are no-network | All automated tests continue to mock or block the outbound Teams HTTP path. No test sets `SOAR_REAL_TEAMS_ENABLED=true` with a real webhook URL. Slack and Teams tests do not share real webhook configuration. |
| 8 | Rollback procedure understood | The operator has read Section 6 (Rollback) before starting. |
| 9 | Secret delivery method confirmed | The staging `TEAMS_WEBHOOK_URL` is available through the approved secret manager (Vault, AWS Secrets Manager, or runtime injection). It will not be pasted into a terminal, ticket, prompt, screenshot, or log. |

---

## 3. Required Environment Variables (Placeholders Only)

Set **all four** simultaneously in the staging runtime. If any one is absent, wrong, or not
simultaneously satisfied, the adapter falls back to simulation and no real message is sent.

```bash
INTEGRATION_MODE=real
SOAR_ENV=staging
SOAR_REAL_TEAMS_ENABLED=true
TEAMS_WEBHOOK_URL=<retrieve-from-approved-secret-manager-do-not-paste>
```

### Teams Webhook URL Validation

The adapter (`integrations/teams_adapter.py:37–52`) validates `TEAMS_WEBHOOK_URL` at runtime.
The URL must be an `https://` URL with a non-empty host matching one of:

- `webhook.office.com` (in host)
- `office.com` (in host) **and** `webhook` (in path)
- `logic.azure.com` (in host)

The adapter **explicitly rejects Slack webhook URLs** (`hooks.slack.com` → validation fails).
A Slack URL set as `TEAMS_WEBHOOK_URL` will cause the Teams adapter to fail closed; it will
not fall back to sending via Slack.

**Webhook URL rules that apply at all times:**

- Retrieve only through the approved secret manager (Vault, AWS Secrets Manager, K8s secret mount, or equivalent).
- Never print, echo, or log the value.
- Never paste into a terminal that keeps history, a ticket, a chat message, a prompt, a commit, or a screenshot.
- Never store in the database, `steps_log`, delivery records, any API response, or any documentation file including this one.
- If the value appears anywhere unexpected, treat it as a secret exposure incident and rotate the webhook immediately.
- Operators may record `TEAMS_WEBHOOK_URL configured: yes` — never the value itself.
- Do not use a Slack webhook URL as a placeholder; the adapter will reject it.

**Must remain unset or false during a Teams-only smoke test:**

```bash
# These must not be changed or enabled during this test session:
SOAR_REAL_SLACK_ENABLED    # must remain at pre-test state (unset or false)
SLACK_WEBHOOK_URL          # must remain at pre-test state (unset or unchanged)
```

**Optional tuning (safe defaults apply if unset):**

```bash
TEAMS_TIMEOUT_SECONDS=3   # default: 3 — do not increase for smoke test
```

---

## 4. Preflight Checks

Run these in order before injecting real env vars. All must pass. Do not skip any check.

### 4.1 Confirm Staging Identity

Verify that the following all point to staging resources, not production:

- Application host / base URL
- Database host and database name
- Teams webhook destination channel (must be a staging/test channel, not a live SOC channel,
  production Teams workspace, production alert workflow, or production routing target)

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
    { "name": "teams", "mode": "simulation", "real_mode_ready": false },
    { "name": "slack", "mode": "simulation" },
    { "name": "email", "mode": "simulation" },
    { "name": "firewall", "mode": "simulation" },
    { "name": "webhook", "mode": "simulation" }
  ]
}
```

**Stop if:** `real_mode_enabled` is `true`, any adapter shows `mode: real`, any webhook URL
value appears in the response, or Slack readiness has changed unexpectedly.

### 4.3 Confirm Teams Circuit Breaker is `closed`

From the same `/integrations/status` response, check the Teams adapter entry:

```json
{
  "name": "teams",
  "circuit_breaker": {
    "state": "closed",
    "consecutive_failures": 0
  }
}
```

**Stop if:** Circuit breaker state is `open`, `half_open`, absent, or ambiguous. Do not use
`half_open` as the entry state for a first real Teams send. Resolve the circuit breaker
state explicitly (see Section 6, step CB-1) before proceeding.

### 4.4 Confirm Slack Remains Independent

Verify that Slack adapter state has not changed from its baseline:

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/integrations/status | \
     jq '.adapters[] | select(.name=="slack")'
```

Expected: Slack adapter shows its baseline state. If a prior Slack smoke test was run, Slack
should still be in simulation mode unless separately re-enabled. Confirm that enabling Teams
env vars has not altered Slack readiness in either direction.

**Stop if:** Slack `real_mode_ready` becomes `true` as a side effect of Teams configuration.
The adapters are independent by design; this state change would indicate an unexpected
coupling that must be investigated before proceeding.

### 4.5 Confirm Test Playbook Shape

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/playbooks/<TEST_PLAYBOOK_ID> | jq '{id, steps}'
```

Verify:

- Exactly one step with `"action": "notify_teams"`.
- No `block_ip`, `block_firewall`, `notify_email`, `notify_slack`, `notify_webhook`,
  `require_approval`, or any remediation step is present.
- `enabled: true`.
- Message text is non-sensitive.

### 4.6 Confirm No Active Duplicate Execution

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     "https://$STAGING_APP_HOST/playbook-executions?playbook_id=<TEST_PLAYBOOK_ID>&status=pending" | \
     jq '.executions | length'
```

Must return `0`. Stop if any `pending`, `running`, or `awaiting_approval` execution exists.
Confirm that no other operator or session will invoke the executor during the test window.

### 4.7 Record Pre-Test Approval Evidence

Record the following **without recording any secrets**:

```
Approver:              <name>
Operator:              <name>
Timestamp (ISO 8601):  <e.g. 2026-05-15T16:00:00Z>
Staging env label:     <e.g. staging-us-west-2>
Git revision:          <output of: git rev-parse --short HEAD>
Teams destination:     <staging channel name or label — not the webhook URL>
TEAMS_WEBHOOK_URL:     configured (yes/no) — value not recorded
Slack state:           <unchanged / simulation — confirm it was not altered>
```

---

## 5. Exact Smoke-Test Steps

Execute in order. Do not skip steps. Do not proceed if any step fails. Stop after one result —
do not retry, loop, or invoke the executor a second time without separate explicit approval.

### Step 1 — Inject Real-Mode Environment Variables

Load the webhook URL from the approved secret manager. Example using HashiCorp Vault:

```bash
export TEAMS_WEBHOOK_URL=$(vault kv get -field=webhook_url secret/soar/staging/teams)
export INTEGRATION_MODE=real
export SOAR_ENV=staging
export SOAR_REAL_TEAMS_ENABLED=true
```

Do not `echo $TEAMS_WEBHOOK_URL`. Do not print or log it. Do not modify Slack env vars.

### Step 2 — Reload Runtime (if Required)

If the staging runtime caches environment variables at startup, perform the minimum required
reload (e.g. rolling pod restart, gunicorn reload signal, or uvicorn restart). Skip if the
runtime picks up env changes without restart.

### Step 3 — Verify Teams Real-Mode Readiness

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/integrations/status | jq .
```

Check the Teams adapter entry. All of the following must be true:

```json
{
  "name": "teams",
  "mode": "real",
  "configured_mode": "real",
  "teams_configured": true,
  "real_mode_allowed": true,
  "real_mode_ready": true,
  "webhook_configured": true,
  "circuit_breaker": { "state": "closed" },
  "supported_actions": ["send_message", "notify_channel", "notify_teams"]
}
```

Also verify:

- No webhook URL value, URL fragment, host path, or request token appears anywhere in the response body.
- All non-Teams adapters (slack, email, firewall, webhook) still show `"mode": "simulation"`.
- Slack adapter readiness is unchanged from its preflight baseline (see Preflight 4.4).
- `real_mode_enabled: true` appears at the top level (expected when `INTEGRATION_MODE=real`).

**Stop if** any check fails. If Slack `real_mode_ready` has become `true` unexpectedly, stop,
do not send, investigate, and escalate before proceeding.

### Step 4 — Trigger One Manual Playbook Execution

**Option A — Manual executor script (preferred for controlled one-shot runs):**

```bash
# From the repo root on the staging host:
python3 scripts/run_playbook_executor_once.py --batch-size 1
```

This processes exactly one eligible `pending` execution row and exits. It does not loop,
retry, or spawn a background process.

**Option B — Resume an approved `awaiting_approval` execution via API:**

```bash
curl -s -X POST \
     -H "Authorization: Bearer $STAGING_TOKEN" \
     -H "Content-Type: application/json" \
     https://$STAGING_APP_HOST/playbook-executions/<EXECUTION_ID>/resume
```

Record the `execution_id` used. Invoke exactly once. Do not invoke a second time.

### Step 5 — Poll Until Terminal Status

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/playbook-executions/<EXECUTION_ID> | \
     jq '{id, status, last_completed_step}'
```

Repeat until `status` is one of: `success`, `failed`, `abandoned`. If status does not reach
a terminal state within a reasonable window (e.g. 2 minutes), stop and treat as a failure.
Do not trigger another execution while waiting.

### Step 6 — Handle Timeout or Outage (if Applicable)

If the execution ends with `failed` due to a Teams timeout or outage:

- Do **not** retry manually unless a separate explicit approval is granted for a second attempt.
- Treat the timeout as a failed smoke test, not a reason to loop.
- Confirm the adapter result classifies the failure safely (e.g. `failure_classification: timeout`) without exposing the webhook URL.
- Check circuit breaker state — a timeout may increment `consecutive_failures`.
- Capture safe evidence of the failure metadata (see Section 7, items E5–E7).
- Proceed directly to rollback (Section 6).

### Step 7 — Confirm Exactly One Teams Message

Check the staging Teams channel manually:

- Exactly **1** message received.
- Message text matches the expected test content (e.g. `SOAR staging Teams smoke test`).
- No sensitive content (webhook URL fragment, token, header value) visible in the message body.

**Stop and mark FAILED if:** 0 messages, >1 message, unexpected content, or message arrived
in an unexpected destination. If >1 message arrived, force-open the circuit breaker
immediately (see Section 6, step CB-1) before proceeding to rollback.

### Step 8 — Capture Evidence

Capture all evidence listed in Section 7 before rolling back. Evidence must not contain any
webhook URL value, request headers, tokens, URL fragments, or raw HTTP response bodies.

### Step 9 — Roll Back to Simulation Immediately

Follow Section 6 (Rollback) in full before closing the session. Rollback is mandatory
regardless of whether the test passed or failed.

---

## 6. Rollback Steps

Perform these immediately after evidence capture, regardless of pass or fail.

### Standard Rollback

```bash
# Remove real-mode variables:
unset INTEGRATION_MODE
unset TEAMS_WEBHOOK_URL
unset SOAR_REAL_TEAMS_ENABLED

# Or set explicitly to simulation:
export INTEGRATION_MODE=simulation
export SOAR_REAL_TEAMS_ENABLED=false
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

Also verify:

- Teams adapter shows `"mode": "simulation"` and `"real_mode_ready": false`.
- Slack adapter state is unchanged from its pre-test baseline.
- Firewall, email, and webhook adapters still show `"mode": "simulation"`.

Clear shell history lines that may contain the webhook URL:

```bash
history -d <line-number>   # zsh: use fc -p and edit ~/.zsh_history manually
# Or clear full session history if the URL was echoed:
history -c
```

### Post-Test Cleanup

After pass or fail, before closing the session:

- Confirm `TEAMS_WEBHOOK_URL` is removed from local shells and any temporary runtime
  configuration where it is no longer needed.
- Confirm no webhook value was written to shell history, logs, evidence, docs, commits,
  tickets, or prompts.
- Confirm no duplicate execution remains active for the test case.
- Confirm automated test and CI environments remain no-network.

### Emergency Rollback (Unexpected Teams Behavior)

If more than one message is sent, unexpected content appears, or the adapter behaves
unexpectedly, perform in this order:

**CB-1 — Force-open the Teams circuit breaker** (blocks all further Teams calls immediately):

```bash
curl -s -X POST \
     -H "Authorization: Bearer $STAGING_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Emergency rollback: unexpected Teams smoke test behavior"}' \
     https://$STAGING_APP_HOST/integrations/teams/circuit-breaker/force-open
```

**CB-2 — Remove real-mode variables and reload** (standard rollback above).

**CB-3 — Verify simulation restored and Slack unaffected**:

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/integrations/status | \
     jq '.mode, (.adapters[] | {name, mode})'
```

Confirm `mode: simulation` and all adapters show `mode: simulation`.

**CB-4 — Reset circuit breaker after simulation is confirmed:**

```bash
curl -s -X POST \
     -H "Authorization: Bearer $STAGING_TOKEN" \
     -H "Content-Type: application/json" \
     -d '{"reason": "Post-rollback reset after emergency force-open"}' \
     https://$STAGING_APP_HOST/integrations/teams/circuit-breaker/reset
```

---

## 7. Evidence Checklist

Capture the following immediately after Step 8 and before rollback (or immediately after
rollback for post-rollback state items). Store all evidence without any secrets.

| # | Evidence item | How to capture | Key fields to verify |
|---|---|---|---|
| E1 | Test metadata | Record manually | Approver, operator, timestamp (ISO 8601), staging env label, git SHA, Teams channel label (not URL) |
| E2 | Integration status — before real-mode injection | Save `/integrations/status` response | `mode: simulation`, `real_mode_enabled: false`, all adapters simulation |
| E3 | Integration status — after real-mode injection | Save `/integrations/status` response | Teams `real_mode_ready: true`, `webhook_configured: true`, no URL value, Slack adapter unchanged, all other adapters `mode: simulation` |
| E4 | Circuit breaker state — before test | From E3 response `.adapters[teams].circuit_breaker` | `state: closed`, `consecutive_failures: 0` |
| E5 | Playbook execution record | `GET /playbook-executions/<EXECUTION_ID>` | `status: success` (or `failed` with safe reason), `playbook_id`, `execution_id` |
| E6 | `steps_log` excerpt | From E5 response `.steps_log[0]` | `action: notify_teams`, `success: true` (or safe failure classification), `simulated: false`, `mode: real`, no webhook URL or URL fragment |
| E7 | Notification delivery attempt record | `GET /notification-deliveries?playbook_execution_id=<ID>` | `provider: teams`, `mode: real`, `status: success` (or `timeout`/`failed`), `correlation_id`, no webhook URL in metadata |
| E8 | Notification delivery metrics | `GET /metrics/notifications` | Counts updated, no secrets |
| E9 | Circuit breaker state — after test | From post-execution `/integrations/status` | `state: closed` (success keeps it closed); if `open`, record `consecutive_failures` and reason |
| E10 | Teams channel confirmation | Screenshot or text note | Exactly 1 message, expected content, timestamp, no webhook URL fragment visible |
| E11 | Slack state — unchanged | From E3 or post-test `/integrations/status` | Slack adapter unchanged from pre-test baseline; Slack `real_mode_ready` not altered |
| E12 | Rollback verification | Save `/integrations/status` after unset | `mode: simulation`, `real_mode_enabled: false`, Teams `real_mode_ready: false`, Slack unchanged |

**Do not capture:**

- `TEAMS_WEBHOOK_URL` value or any URL fragment.
- `SLACK_WEBHOOK_URL` value.
- Request headers or tokens.
- Raw Teams webhook HTTP response body if it echoes request metadata.
- Shell command history lines containing the webhook URL.
- Screenshots or logs that reveal webhook URL fragments.
- Production Teams channel identifiers if considered sensitive.

---

## 8. Pass / Fail Criteria

### Pass — All of the following must be true

- [ ] Test ran in a confirmed staging environment with a confirmed staging Teams destination.
- [ ] Manual operator approval was recorded before the send.
- [ ] All four required env vars were set via approved runtime configuration only.
- [ ] Preflight checks passed in full before execution (Sections 4.1–4.7).
- [ ] Integration status showed Teams `real_mode_ready: true` with safe booleans only; no webhook URL or URL fragment in any response.
- [ ] Slack adapter state was unchanged by Teams env var changes (independence confirmed).
- [ ] All non-Teams adapters showed `mode: simulation` throughout the test.
- [ ] Playbook execution reached `status: success`.
- [ ] Exactly **one** Teams message arrived in the expected staging channel.
- [ ] `steps_log` shows `notify_teams` step completed with `success: true`, `simulated: false`, `mode: real`, no webhook URL.
- [ ] At least one `notification_delivery_attempts` record exists for the execution with `status: success` and no webhook URL in metadata.
- [ ] Circuit breaker remained `closed` before and after the test.
- [ ] No real firewall, Slack, email, generic webhook, or PagerDuty call was made.
- [ ] No subprocess call, `blocked_ips` mutation, queue redesign, scheduler, daemon, or autonomous retry behavior occurred.
- [ ] Rollback to simulation was completed and verified (E12 captured).
- [ ] Post-test cleanup completed (webhook URL removed from shells, history cleared).
- [ ] No webhook URL appeared in logs, UI, status output, audit output, evidence, prompts, docs, commits, or tickets at any point.

### Fail — Stop immediately if any of the following is true

- [ ] Environment identity is not clearly staging.
- [ ] Teams channel destination is unclear, production-linked, or unconfirmed.
- [ ] Manual approval is missing or ambiguous.
- [ ] Any required env var is missing at execution time.
- [ ] Integration status shows `real_mode_ready: false` for Teams when all four vars are set.
- [ ] Teams webhook URL validation fails (e.g. Slack URL was supplied as `TEAMS_WEBHOOK_URL`).
- [ ] Webhook URL value appears in any log, API response, `steps_log`, delivery record, screenshot, or terminal output.
- [ ] Slack adapter `real_mode_ready` becomes `true` as a side effect of Teams configuration.
- [ ] Any non-Teams adapter shows `mode: real` at any point.
- [ ] Teams circuit breaker is `open`, `half_open`, or absent before execution.
- [ ] Zero Teams messages received (delivery silently dropped).
- [ ] More than one Teams message received (duplicate prevention failure).
- [ ] Unexpected Teams message content, unexpected destination, or sensitive content visible in message.
- [ ] Any real firewall, Slack, email, generic webhook, or PagerDuty action occurred.
- [ ] A second executor invocation was triggered without separate approval.
- [ ] Rollback to simulation cannot be verified.
- [ ] Shell history cannot be cleared of the webhook URL.

---

## 9. Safety Warnings

> **STAGING ONLY.** This runbook must never be used against a production environment,
> local development, CI, or any environment where the Teams destination is a live SOC channel,
> a production workspace, a production alert workflow, or any channel where unexpected messages
> would cause operational impact.

> **TEAMS AND SLACK ARE INDEPENDENT.** Enabling Teams real mode does not enable or affect
> Slack. Slack env vars (`SOAR_REAL_SLACK_ENABLED`, `SLACK_WEBHOOK_URL`) must not be modified
> during this session. Completing a Slack smoke test does not satisfy this runbook's
> requirements. Confirm at Preflight 4.4 and Step 3 that Slack readiness is unchanged.

> **TEAMS URL VALIDATION IS STRICT.** The Teams adapter (`integrations/teams_adapter.py:37–52`)
> validates the webhook URL against known Office 365 and Azure Logic App host patterns. It
> explicitly rejects Slack URLs (`hooks.slack.com`). Supplying a Slack URL as
> `TEAMS_WEBHOOK_URL` will not fall back to sending via Slack — it will fail closed. Use only
> a valid `https://webhook.office.com/...`, `https://*.office.com/.../webhook/...`, or
> `https://*.logic.azure.com/...` URL for the Teams adapter.

> **ONE CONTROLLED SEND.** The smoke test covers exactly one playbook execution with exactly
> one `notify_teams` step. Stop after one result, whether success or failure. Do not retry,
> loop, replay, or trigger additional executions without separate explicit approval.

> **WEBHOOK URL IS A SECRET.** Treat `TEAMS_WEBHOOK_URL` with the same care as a database
> password. Never echo, print, log, paste, commit, or screenshot it. If it appears anywhere
> unexpectedly, treat it as a secret exposure incident and rotate the webhook immediately.
> The adapter (`integrations/teams_adapter.py:62`) explicitly documents that readiness
> metadata must never include the webhook value.

> **NO NETWORK CALLS IN AUTOMATED TESTS.** Do not run the automated test suite with
> `SOAR_REAL_TEAMS_ENABLED=true`. Tests mock or block outbound Teams HTTP. Slack tests and
> Teams tests must not share real webhook configuration.

> **ROLLBACK IS MANDATORY.** Default simulation mode must be restored and verified before
> the session ends, regardless of whether the test passed or failed. Post-test cleanup
> (webhook URL removed from shells, history cleared) must also be completed.

> **CIRCUIT BREAKER MUST BE `closed` BEFORE EXECUTION.** If the breaker is `open` or
> `half_open` before the test starts, an outbound call may be blocked or produce unexpected
> behavior. Do not use `half_open` as the entry state for a first real Teams send. Resolve
> circuit breaker state explicitly (Preflight 4.3) before proceeding.

> **TIMEOUT OR OUTAGE IS A FAILED TEST, NOT A REASON TO RETRY.** If the Teams send times
> out or Teams is unavailable, capture safe failure evidence, record the timeout classification
> from the adapter result, check circuit breaker state, and proceed directly to rollback.
> Do not trigger a second execution without separate approval.

---

## 10. Out-of-Scope Integrations

The following integrations remain **simulation-only** and are out of scope for this runbook
and for any test session following it. They must not be real-enabled, connected to live
endpoints, or invoked with live credentials regardless of what `INTEGRATION_MODE` is set to.

| Integration | Status | Constraint |
|---|---|---|
| Real firewall / `block_ip` (live) | Out of scope | `LinuxFirewallDryRunAdapter` is dry-run only; no subprocess, no real firewall API |
| Email (SMTP / SendGrid) | Out of scope | `email_adapter.py` simulation-only; no SMTP host or credentials configured |
| Generic webhook | Out of scope | `webhook_adapter.py` simulation-only regardless of `INTEGRATION_MODE` |
| PagerDuty | Out of scope | Not implemented; no adapter or credentials exist |
| Microsoft Slack | Not applicable | See separate Slack runbook (`docs/soar_slack_staging_smoke_test_runbook.md`); Slack and Teams readiness are independent; this runbook must not trigger a Slack send |

Enabling any of the above for real execution requires a separate approved design and its own
staged runbook. They must not be enabled as a side effect of this Teams smoke test.

The `integration_registry.py` module enforces simulation-only mode for email, firewall, and
webhook adapters at the code level, regardless of `INTEGRATION_MODE`. This is a code-level
safety constraint, not just operational policy.

---

## Quick Reference

```
Preflight API:   GET  /integrations/status
Execution:       python3 scripts/run_playbook_executor_once.py --batch-size 1
                 POST /playbook-executions/<id>/resume
Execution poll:  GET  /playbook-executions/<id>
Delivery record: GET  /notification-deliveries?playbook_execution_id=<id>
Metrics:         GET  /metrics/notifications
CB force-open:   POST /integrations/teams/circuit-breaker/force-open   { "reason": "..." }
CB reset:        POST /integrations/teams/circuit-breaker/reset         { "reason": "..." }
CB half-open:    POST /integrations/teams/circuit-breaker/enable-half-open { "reason": "..." }

All circuit breaker control endpoints: super_admin only, require non-empty reason field.

Teams webhook URL valid hosts:   webhook.office.com | *.office.com + /webhook/ path | *.logic.azure.com
Teams webhook URL rejected host: hooks.slack.com (adapter fails closed if supplied)
```
