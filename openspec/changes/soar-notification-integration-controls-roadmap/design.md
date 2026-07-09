## Overview

This parent roadmap is a coordination artifact only. It records a code-verified audit of the current SOAR notification/firewall integration adapters, defines shared terminology, and sequences four future child specs that together build an Integration Delivery Controls system distinguishing "code exists" from "proven to work" from "allowed to run in production playbooks."

## Terminology

These definitions are authoritative for this roadmap and every child spec under it:

- **Configured** — required env vars/secrets for a provider are present (e.g. `SLACK_WEBHOOK_URL`, `SMTP_HOST` + `SMTP_USERNAME`).
- **Tested** — a manual test notification through that provider succeeded.
- **Active** — a human has explicitly allowed playbooks to use this provider for real delivery.
- **Delivered** — a real notification was actually sent successfully (an HTTP 2xx from the provider, an accepted SMTP send, etc.).
- **Simulation** — no external call was made at all; the adapter returned a simulated success without contacting Slack/Teams/SMTP/webhook.

A provider can be Configured without being Tested, and Tested without being Active. Code existing for a provider is never, by itself, evidence of any of the above.

## Current Adapter Reality (Code-Verified Audit)

| Provider | Real-mode code path exists | Guard model | Proven to deliver | Source |
| --- | --- | --- | --- | --- |
| Slack | Yes | Four-guard: `INTEGRATION_MODE=real`, `SOAR_ENV` in `{staging}`, `SOAR_REAL_SLACK_ENABLED`, `SLACK_WEBHOOK_URL` configured and shaped like `https://hooks.slack.com/services/...` | **Yes** — one confirmed manual test notification received previously (per user account; not independently re-verified by this roadmap) | `integrations/slack_adapter.py` |
| Teams | Yes | Same four-guard model: `SOAR_REAL_TEAMS_ENABLED`, `TEAMS_WEBHOOK_URL` validated against `webhook.office.com`/`office.com` webhook paths/`logic.azure.com` (explicitly rejects Slack-shaped URLs) | **No** — previously attempted, did not work; root cause not established | `integrations/teams_adapter.py` |
| Email | Yes | Same four-guard model: `SOAR_REAL_EMAIL_ENABLED`, `SMTP_HOST`+`SMTP_USERNAME` as credential guards, plus `SMTP_FROM_EMAIL`/`SMTP_TO_EMAIL` required for a ready state; sends via `smtplib` | **No** — never proven | `integrations/email_adapter.py` |
| Webhook | Yes | Same four-guard model: `SOAR_REAL_WEBHOOK_ENABLED`, `WEBHOOK_URL`/`WEBHOOK_BASE_URL`; allowlisted payload key set; HTTPS POST | **No** — never proven | `integrations/webhook_adapter.py` |
| Firewall | **No** — `FirewallSimulationAdapter` has no `allow_real_mode` flag and no real-execution branch at all; `_simulate` is its only code path | N/A | N/A — simulation is the intended permanent state | `integrations/firewall_adapter.py`; the file's own comment states any real firewall execution "requires a separate future approved OpenSpec before API calls, subprocesses, or blocklist mutation" |

All four notification adapters share one canonical fail-closed guard function, `_validate_real_mode_guards()` in `integrations/base_integration.py`: real mode requires `INTEGRATION_MODE=real` **and** `SOAR_ENV` in an explicit allowlist (`staging` by default) **and** a per-adapter `SOAR_REAL_<PROVIDER>_ENABLED` flag **and** all required credential env vars present. Missing any guard fails closed with a safe, secret-free `real_mode_status` string. All four also share per-adapter rate limiting (`check_adapter_rate_limit`), timeout handling, HTTP/URL error classification (transient vs non-transient), and audit logging of every real-mode attempt via `core.integration_audit.log_integration_execution_attempt`. This confirms the user's framing precisely: the code for all four is structurally identical and equally guarded, but only Slack has actual human-confirmed delivery evidence.

## Live Runtime Readiness Evidence

After implementing `soar-notification-readiness-test-buttons`, live runtime validation produced the following production-readiness evidence:

| Provider | Live readiness evidence | Current readiness |
| --- | --- | --- |
| Slack | Successfully configured, real-mode enabled, manual readiness test succeeded, and a real Slack notification was received. | `Configured=true`, `Tested=Passed`, `Ready=true` |
| Email | Successfully configured using Gmail SMTP with an App Password; manual readiness test succeeded and SMTP authentication succeeded. | `Configured=true`, `Tested=Passed`, `Ready=true` |
| Webhook | Successfully configured; manual readiness test succeeded and a real outbound POST completed successfully. | `Configured=true`, `Tested=Passed`, `Ready=true` |
| Teams | Not yet configured; no real readiness test has been performed. Current blocker is the absence of a Microsoft Teams Workflows webhook. Deferred intentionally until a personal Teams environment or supported Workflows webhook is available. | Not ready; intentionally deferred |
| Firewall | Remains simulation-only by design; no real execution attempted. | N/A |

This evidence proves three notification providers in a live runtime: Slack, Email, and Webhook. It does **not** mean every integration is complete; Teams remains intentionally deferred, and Firewall remains permanently excluded from real execution by this roadmap.

## Current Playbook Notification Actions

`engines/playbook_step_executor.py` already defines four notification step types — `notify_slack`, `notify_teams`, `notify_email`, `notify_webhook` — mapped via `_PROVIDER_FOR_ACTION` to the corresponding adapter. The executor already has an `_existing_active_delivery()` idempotency check that prevents duplicate delivery attempts for the same playbook execution/step, and already maps adapter results to a delivery status (`success`/`timeout`/`blocked`/etc.) for storage. **No provider active/inactive gate exists anywhere in the executor today** — a playbook step will attempt delivery through whatever mode/guards are currently configured, with no durable, human-controlled "this provider is allowed in production" switch. This is exactly the gap `soar-playbook-notification-enforcement` (child spec 3) must fill.

Note for that child spec: the executor's existing `_existing_active_delivery` name refers to an in-flight/already-attempted delivery record for idempotency purposes — a different concept from the new "provider Active/Inactive" state this roadmap defines. Naming must not collide when child spec 3 is implemented.

## Current Delivery Evidence

A `notification_delivery_attempts` table already exists (`migrations/0008_soar_notification_delivery.sql`), with columns including `provider`, `mode` (`simulation`/`real`), `status` (`pending`/`success`/`failed`/`timeout`/`blocked`), `correlation_id`, `idempotency_key`, `playbook_execution_id`/`playbook_step_index`, `incident_id`/`approval_request_id`/`alert_id` linkage, `failure_code`/`failure_message`, `circuit_breaker_state`, and a redacted `metadata` JSONB column. `core/notification_delivery_store.py` (393 lines) already provides `create_notification_delivery_attempt`, `get_notification_delivery_attempt`, and `list_notification_delivery_attempts`, plus a secret-redaction denylist (`_METADATA_KEY_DENYLIST`/`_METADATA_KEY_SUBSTRING_DENY`) that strips tokens, passwords, webhook URLs, and headers before anything is persisted. The table is explicitly append-only — no update helpers exist, only create/read/list — and callers own their own transaction boundaries.

This means `soar-notification-delivery-history` (child spec 4) is substantially de-risked: "last successful delivery," "last failed delivery," and "error reason without secrets" can likely be built as new read/aggregation queries against the existing table, without a new migration for delivery history itself.

## What Does Not Exist Yet

- **No durable per-provider Configured/Tested/Active state.** Nothing in the schema or codebase stores "a human tested Slack and it worked" or "a human turned Teams on for production" as a persisted fact. This is genuinely new and will very likely require a new migration (child spec 2) — this roadmap does not pre-decide that table's shape.
- **No manual test-send endpoint or UI control.** `routes/integration_routes.py` currently exposes `GET /integrations/status` (combined readiness across all adapters, built by `integrations/integration_registry.py#get_integration_status`) and circuit-breaker control routes (`reset`, `force-open`, `enable-half-open`) — nothing that lets an operator trigger one deliberate test notification and see a clear pass/fail. This is new work for child spec 1.
- **No provider active/inactive enforcement in the playbook executor.** Confirmed above.
- **No consolidated "what actually happened" delivery evidence view in the UI**, even though the backing data (`notification_delivery_attempts`) already exists.

## Current UI Reality

`frontend/src/components/IntegrationStatusPanel.js` and `frontend/src/services/integrationService.js` already render per-adapter descriptions, derive "missing config" from the same `/integrations/status` response fields the backend already returns (`real_mode_ready`, `real_mode_allowed`, `real_mode_status`, per-adapter config booleans), and render inline circuit-breaker controls. The circuit breaker shown here is `_SimulatedCircuitBreakerState` in `integrations/base_integration.py` — an **in-memory, per-process, simulated** structure, not DB-persisted — displayed alongside real-mode readiness and general status in the same panel. This is precisely the "mixes simulation/real mode, readiness, circuit breaker internals, and integration status" confusion described in this roadmap's motivation.

- **Can be shown today without backend changes:** current per-provider configured/missing-config state, current real-mode readiness/guard status, current in-memory circuit breaker state — all already returned by the existing `/integrations/status` endpoint.
- **Requires backend changes:** manual test-send trigger + result (child spec 1), durable Configured/Tested/Active state and its toggle endpoints (child spec 2), playbook-executor enforcement outcomes (child spec 3), and any new delivery-history read/aggregation endpoints (child spec 4).

## Child Spec Plan

### 1. `soar-notification-readiness-test-buttons`

Owns proving what actually works:

- Audit existing Slack/Teams/Email/Webhook adapters in detail (beyond this roadmap's summary) before adding UI.
- Add safe manual test-send buttons/endpoints, reusing the existing guarded real-mode adapter code paths and rate limiting rather than duplicating send logic.
- Show missing config per provider (largely already possible from existing `/integrations/status` fields).
- Show last test result per provider (new).
- Re-prove Slack. Prove or clearly fail Teams, Email, and Webhook.
- Do not wire Active/Inactive enforcement yet — this spec only proves Tested state.

Implementation status: completed. Live runtime validation proved Slack, Email, and Webhook. Teams remains intentionally deferred because no Microsoft Teams Workflows webhook is available yet.

### 2. `soar-notification-provider-active-controls`

Owns durable production authorization:

- Backend durable provider status (new table/migration likely required).
- UI toggles for Slack, Teams, Email, Webhook Active/Inactive.
- Firewall explicitly excluded from any real-enablement control — it has no real-mode code path and none is added here.
- Activation should require or clearly warn based on current Configured/Tested state (exact enforcement strictness is that child spec's decision).
- State stored in the database, not localStorage — this is operator-facing production policy, not a personal UI preference.

### 3. `soar-playbook-notification-enforcement`

Owns playbook-time behavior:

- Playbook executor checks provider Active state before attempting a notification step.
- Active provider: attempt delivery through the existing guarded adapter path.
- Inactive provider: skip the step by policy — do not attempt delivery.
- Record a clear skipped-by-policy outcome (e.g. "Skipped: Teams integration inactive") distinct from a failed delivery.
- No fake success for a skipped or failed step.
- No endless retry loop — respect the existing rate-limit/transient-vs-non-transient failure classification already built into the adapters.
- Skipping a notification step must not block unrelated playbook steps unless a future spec explicitly requires that coupling.

### 4. `soar-notification-delivery-history`

Owns operational evidence, largely by querying the existing `notification_delivery_attempts` table:

- Last successful delivery per provider.
- Last failed delivery per provider.
- Last tested (per child spec 1's test-send records).
- Error reason shown without secrets, reusing the existing redaction helpers in `core/notification_delivery_store.py`.
- Clear UI evidence of what actually happened, replacing ambiguity with a factual timeline.

## Implementation Sequencing

1. Create and validate this parent roadmap.
2. Create and implement `soar-notification-readiness-test-buttons` first — nothing else should claim a provider is trustworthy before it can be manually proven or disproven.
3. Create and implement `soar-notification-provider-active-controls` second — production authorization should be informed by real Tested evidence from step 2, not introduced blind.
4. Create and implement `soar-playbook-notification-enforcement` third — playbook behavior should only change once a durable Active state exists to check.
5. Create and implement `soar-notification-delivery-history` fourth — evidence display is most valuable once test sends (1) and real playbook attempts (3) are actually producing delivery records, though the underlying table already exists today.
6. Keep each child implementation separately validated before starting the next.

## Validation Direction

Child specs should include focused backend tests for guard enforcement, test-send endpoints, active/inactive persistence and enforcement, skip-by-policy outcomes, and delivery-history queries, plus frontend tests for the redesigned Integrations UI. Any child spec touching real external calls must keep tests fully mocked — no test suite may contact a real Slack/Teams/SMTP/webhook endpoint. Any child spec adding a migration must include migration validation and rollback consideration consistent with this project's existing migration conventions (see `migrations/0008_soar_notification_delivery.sql` for the existing pattern).

## Deployment / Rebuild Direction

This parent roadmap requires no VM sync and no deployment of any kind — it is planning-only. Future child specs that add backend routes, database migrations, or frontend changes will require normal backend/frontend deployment, migration application, and — per this project's Mac-source-of-truth policy — VM sync only after code is pushed and the VM working tree is confirmed clean. No child spec in this roadmap should require Azure work.

## Risks And Unknowns

- Teams' prior failure has no established root cause (invalid/expired webhook URL, wrong channel/connector configuration, network/proxy issue). Child spec 1 must capture a real, current test result rather than assuming the existing code is broken or working.
- Firewall must never gain a real-execution path through this initiative; every child spec must repeat that boundary explicitly.
- The new "provider Active/Inactive" concept has no current DB representation and must not be confused with the executor's existing, differently-scoped `_existing_active_delivery` idempotency check — child spec 3 must resolve this naming carefully.
- Whether manual test sends (child spec 1) reuse the existing `notification_delivery_attempts` table (e.g., with a new marker distinguishing "test" from "playbook-triggered") or use a separate mechanism is an open design question for that child spec, not decided here.
- Any new fields introduced by later child specs must extend, not bypass, the existing secret-redaction denylist in `core/notification_delivery_store.py`.
- The in-memory/simulated circuit breaker must not be conflated with the new durable provider-active state; they answer different questions (transient adapter health vs. human production authorization) and child specs must keep them visibly distinct in the UI.
- Real (and test) sends must continue to respect the existing per-adapter rate limiter (`check_adapter_rate_limit`) so a test-send feature cannot become a way to spam a real Slack channel or inbox.
- Activation strictness in child spec 2 (whether Active requires Tested, or only warns) is a product decision not made by this roadmap and must be resolved explicitly when that spec is written.
