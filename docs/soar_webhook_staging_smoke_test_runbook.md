# SOAR Webhook Staging Smoke-Test Runbook

**Scope: STAGING ONLY. This runbook must not be followed in any other environment.**

Before editing this file or any referenced integration code, inspect nearby `# spec:` tags
and `openspec/spec-index.md`. Active changes at time of writing:

- `openspec/changes/add-real-soar-integrations-safety/`

---

## 1. Purpose

This runbook governs the first controlled, manual generic webhook notification from the SOAR
integration layer in staging. It verifies the four-guard real-mode path, HTTPS-only outbound
target policy, bounded payload handling, delivery evidence, and immediate rollback to simulation.

This document is **documentation only**. It does not send HTTP traffic by itself.

**Default mode must return to simulation immediately after the test is complete.**

---

## 2. Preconditions

| # | Precondition | Required state |
|---|---|---|
| 1 | Environment identity | Host, deployment target, database, and app URL are confirmed staging. |
| 2 | Approval | A super_admin or operator approved this single test. Record approver, operator, timestamp, and environment label without secrets. |
| 3 | Playbook prepared | Test-only playbook with **exactly one** `notify_webhook` step. No remediation steps. Message/payload fields are non-sensitive. |
| 4 | No active duplicate execution | No `pending`, `running`, or `awaiting_approval` execution exists for the same playbook/alert pair. |
| 5 | Automated tests are no-network | Tests mock `_post_webhook_request`; no test enables real outbound HTTP. |
| 6 | Rollback understood | Operator has read Section 6 before starting. |
| 7 | Secret delivery method confirmed | `WEBHOOK_URL` (or `WEBHOOK_BASE_URL`) and optional `WEBHOOK_AUTH_TOKEN` come from an approved secret manager only. |

---

## 3. Required Environment Variables (Placeholders Only)

Set **all four** guards simultaneously. Any missing guard fails closed to simulation.

```bash
INTEGRATION_MODE=real
SOAR_ENV=staging
SOAR_REAL_WEBHOOK_ENABLED=true
WEBHOOK_URL=<retrieve-from-approved-secret-manager-do-not-paste>
```

Optional alias when your platform stores a base URL separately:

```bash
WEBHOOK_BASE_URL=<retrieve-from-approved-secret-manager-do-not-paste>
```

Optional auth (never log or store in DB/API responses):

```bash
WEBHOOK_AUTH_TOKEN=<retrieve-from-approved-secret-manager-do-not-paste>
```

**Rules for webhook URL and token values:**

- Retrieve only through approved secret manager.
- Never print, echo, or log values.
- Never paste into shell history, tickets, chat, prompts, or commits.
- Never store in `steps_log`, delivery records, audits, or API responses.
- Operators may record `WEBHOOK_URL configured: yes` — never the value itself.

**Target policy (enforced by adapter):**

- HTTPS only (`http://`, `file://`, and other schemes are rejected).
- Localhost, loopback, link-local, and private-network targets are rejected.
- Payload size is bounded; oversized payloads fail before outbound call.

**Optional tuning:**

```bash
WEBHOOK_TIMEOUT_SECONDS=5   # default: 5
```

**Never set for a webhook-only smoke test:**

```bash
SOAR_REAL_SLACK_ENABLED
SOAR_REAL_TEAMS_ENABLED
SOAR_REAL_EMAIL_ENABLED
SOAR_REAL_FIREWALL_ENABLED
```

---

## 4. Preflight Checks

### 4.1 Confirm staging identity

Verify application host, database host/name, and webhook destination are staging resources.

### 4.2 Confirm default simulation mode

With real guards unset:

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/integrations/status | jq .
```

Expected: `real_mode_enabled` is `false` and adapter `webhook.mode` is `simulation`.

### 4.3 Confirm target URL policy

The configured URL must:

- use `https://`
- resolve to a public staging endpoint (not `127.0.0.1`, `localhost`, `10.x`, `192.168.x`, etc.)

`GET /integrations/status` should report `webhook_url_configured: true` and
`real_mode_ready: true` without revealing the URL value.

---

## 5. Controlled Execution

1. Inject the four required guards (and optional token) through approved runtime secret injection.
2. Re-check `GET /integrations/status` — `adapters[]` entry for `webhook` should show `mode: real`.
3. Run **one** playbook execution with the test playbook (`notify_webhook` only).
4. Use the manual executor path unless an approved daemon procedure exists.
5. Capture evidence (Section 5.1) before rollback.

### 5.1 Evidence to capture

- `GET /integrations/status` — webhook readiness booleans only
- `GET /playbook-executions/<id>` — execution status and safe `steps_log` fields
- `GET /notification-deliveries` (if delivery row created for webhook notification steps)
- Audit event `SOAR_REAL_ADAPTER_ATTEMPT` — confirm no URL/token/header material

Confirm:

- exactly one outbound attempt
- `failure_classification` absent on success
- circuit breaker remains `closed` unless a real failure occurred

---

## 6. Rollback (Mandatory)

Unset or disable all real webhook guards:

```bash
INTEGRATION_MODE=simulation
SOAR_REAL_WEBHOOK_ENABLED=false
unset WEBHOOK_URL WEBHOOK_BASE_URL WEBHOOK_AUTH_TOKEN
```

Re-check:

```bash
curl -s -H "Authorization: Bearer $STAGING_TOKEN" \
     https://$STAGING_APP_HOST/integrations/status | jq '.adapters[] | select(.name=="webhook")'
```

Expected: `mode: simulation`, `real_mode_ready: false`, `webhook_url_configured: false`.

---

## 7. Abort Conditions

Stop immediately if:

- URL or token appears in application logs, API output, `steps_log`, or delivery metadata
- more than one HTTP attempt occurs for the same execution/step
- target validation errors reference a disallowed host but still attempt outbound traffic
- any non-webhook adapter enters real mode unintentionally

Treat unexpected secret exposure as a security incident.
