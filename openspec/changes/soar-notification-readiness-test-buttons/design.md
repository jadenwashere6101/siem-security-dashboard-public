## Overview

`soar-notification-readiness-test-buttons` is the first child implementation spec under `soar-notification-integration-controls-roadmap`. Its sole purpose is proving whether each notification provider actually works — not enabling it for production use, not changing playbook behavior, not building a delivery-history dashboard. Those are explicitly later child specs.

This spec plans work only for Slack, Teams, Email, and Webhook. Firewall is out of scope entirely: it has no real-mode code path today (`integrations/firewall_adapter.py` is simulate-only) and this spec introduces no test button, no test endpoint, and no real-mode path for it.

## Detailed Adapter Audit

All four notification adapters (`integrations/slack_adapter.py`, `integrations/teams_adapter.py`, `integrations/email_adapter.py`, `integrations/webhook_adapter.py`) share one structure:

- A `get_<provider>_real_mode_readiness(configured_mode)` function returning secret-free readiness metadata, built on the shared `_validate_real_mode_guards()` helper in `integrations/base_integration.py`. That helper checks four guards together: `INTEGRATION_MODE == "real"`, `SOAR_ENV` in an allowlist (`staging` by default), a per-adapter `SOAR_REAL_<PROVIDER>_ENABLED` flag, and presence of the provider's credential env var(s). Missing any guard fails closed.
- A `<Provider>SimulationAdapter(BaseIntegration)` class whose `_execute_supported_action` simulates unless `self.mode == REAL_MODE`, in which case it calls a private `_execute_real_<provider>()` method that re-validates readiness, checks the shared per-adapter rate limiter (`check_adapter_rate_limit`), attempts the real call (HTTPS POST for Slack/Teams/Webhook, SMTP send for Email), classifies failures (`transient`/`non_transient`/`timeout`/`provider_rate_limited`/etc.), and logs every real-mode attempt via `core.integration_audit.log_integration_execution_attempt` (which redacts secrets before logging).
- Each provider's own `<provider>_configured` (or `smtp_configured`/`webhook_configured`) boolean, computed independently of the deployment-mode guards (`INTEGRATION_MODE`/`SOAR_ENV`/`SOAR_REAL_<X>_ENABLED`) — this is the correct basis for this spec's "Configured" concept, not the combined `real_mode_allowed`/`real_mode_ready` fields, which conflate "credentials present" with "deployment mode currently permits a real send."

Provider-specific required env vars, per the existing readiness functions:

| Provider | Credential env var(s) checked for "Configured" | Real-send mechanism |
| --- | --- | --- |
| Slack | `SLACK_WEBHOOK_URL` (must also match `https://hooks.slack.com/services/...`) | HTTPS POST via `urllib.request` |
| Teams | `TEAMS_WEBHOOK_URL` (must match `office.com`/`webhook.office.com`/`logic.azure.com`, explicitly rejects Slack-shaped URLs) | HTTPS POST via `urllib.request` |
| Email | `SMTP_HOST`, `SMTP_USERNAME` (guard credentials) plus `SMTP_FROM_EMAIL`, `SMTP_TO_EMAIL` (required for `payload_defaults_configured`) | SMTP send via `smtplib` |
| Webhook | `WEBHOOK_URL` or `WEBHOOK_BASE_URL` (either satisfies) | HTTPS POST via `urllib.request` |

Note for implementation: the existing email readiness function does not include `SMTP_PASSWORD` in its own "configured" checks even though the adapter uses it for SMTP auth. This spec does not assume that is a bug or fix it — it is flagged here so the implementing child spec confirms and, if needed, corrects the "Missing Configuration" list for Email rather than silently reproducing a possible gap.

Firewall (`integrations/firewall_adapter.py`) has no `get_firewall_real_mode_readiness()`, no `_execute_real_firewall()`, and no `allow_real_mode` flag — its only code path is `_simulate()`. `integrations/integration_registry.py` additionally hard-codes firewall's real mode as permanently blocked ("blocked: firewall real mode requires a separate approved OpenSpec") regardless of env vars. This spec does not touch or extend that.

## Existing Endpoints, Tests, And UI

- **Endpoints today:** `GET /integrations/status` (`routes/integration_routes.py`, combined readiness + circuit breaker, `analyst_or_super_admin_required`), circuit-breaker `POST` controls (`reset`/`force-open`/`enable-half-open`, `super_admin_required`), and read-only `GET /notification-deliveries` + `GET /notification-deliveries/<id>` (`routes/notification_delivery_routes.py`, `analyst_or_super_admin_required`). That module's own docstring states it is "Read-only... does not create attempts, call adapters, or mutate delivery rows" — a new test-send endpoint must live elsewhere (in `routes/integration_routes.py`, alongside the existing adapter-scoped controls) rather than inside that read-only module, to keep its documented contract true.
- **Existing tests:** `tests/test_integration_adapters.py` (1546 lines) already extensively mocks and verifies guard enforcement, redaction, rate limiting, circuit-breaker interaction, and failure classification for all four real-mode adapters, plus explicitly confirms Firewall never gains a real-mode path (`test_real_mode_does_not_apply_to_firewall_adapter`). `tests/test_notification_delivery_store.py`, `tests/test_notification_delivery_routes.py`, and `tests/test_notification_delivery_metrics_routes.py` cover the existing delivery-attempt table and its read routes. None of this exercises a manual, standalone test-send trigger, because none exists yet.
- **Existing UI:** `frontend/src/components/IntegrationStatusPanel.js` (1050 lines) and `frontend/src/services/integrationService.js` already render per-adapter descriptions and a `missingConfigNames()` helper that extracts environment variable names by regex-parsing the human-readable `real_mode_status` string returned by `/integrations/status` (see `extractEnvNames()` in that file). This is a fragile, indirect way to get "missing configuration" today; this spec should replace it with a clean, structured list of env var names returned directly by the backend, rather than parsing free text.

## What Already Exists That This Spec Can Reuse

- The four-guard fail-closed real-mode model itself — a test send must invoke this exact model, not a weaker path.
- Per-adapter rate limiting (`check_adapter_rate_limit`) — a test send must go through it like any other real-mode attempt, so the test-send feature cannot become a way to spam a real channel or inbox.
- Secret-free audit logging (`log_integration_execution_attempt`) and metadata redaction (`redact_notification_delivery_metadata`, `sanitize_failure_message` in `core/notification_delivery_store.py`).
- The `notification_delivery_attempts` table and its `create_notification_delivery_attempt`/`get_notification_delivery_attempt`/`list_notification_delivery_attempts` functions (`core/notification_delivery_store.py`), including its existing `status` vocabulary (`pending`/`success`/`failed`/`timeout`/`blocked`), which already distinguishes an outright failure (`failed`/`timeout`) from a guard-blocked attempt (`blocked`) — this distinction maps directly onto this spec's Tested outcomes (see "Tested Outcome Mapping" below).
- The frontend's existing `postCircuitControl`-style fetch pattern in `integrationService.js` (POST with JSON body, shared error-message parsing via `getApiErrorMessage`/`parseJsonResponse`) as the template for a new test-send API call.

## What Does Not Exist Yet And Must Be Planned

- **A standalone test-send orchestration path.** Only `engines/playbook_step_executor.py` currently calls `create_notification_delivery_attempt()`; no code path executes an adapter and records the result outside of a playbook execution. A manual test send has no `playbook_execution_id`, `incident_id`, `approval_request_id`, or `alert_id` (all nullable on the table) and needs synthetic `correlation_id`/`idempotency_key` values (both `NOT NULL`) generated per test click.
- **A way to mark a delivery-attempt row as a manual test**, distinct from a playbook-triggered send. The `action` column already exists and is free text (validated only for non-empty); this spec should plan a new `action` value such as `test_notification` (added to each adapter's `supported_actions`, or handled by the new orchestration layer without requiring adapter changes — an explicit implementation-time decision, not pre-decided here) so that "last test" can be queried unambiguously.
- **An `action` filter on `list_notification_delivery_attempts`.** The function today filters by `provider`, `mode`, `status`, `correlation_id`, `idempotency_key`, `playbook_execution_id`, `incident_id`, `approval_request_id`, `alert_id`, and `adapter_name` — but not `action`. Adding an optional `action` parameter is a small, additive, backward-compatible change (no migration) that makes "most recent test for this provider" a simple, direct query.
- **A structured Missing Configuration list per provider** (env var names only), replacing the frontend's current regex-based extraction from a status string.
- **A test-send API route**, gated at minimum as strictly as the existing circuit-breaker `POST` controls (`super_admin_required`), since it is a real, externally-visible action even though its blast radius is one message.
- **A durable "Tested" read surface** distinct from `real_mode_ready`. This does not require a new table — it can be computed on read from the most recent `test_notification`-tagged `notification_delivery_attempts` row per provider.

## Readiness Model

```
Configured
  ↓ (credential/env vars present, independent of deployment guards)
Manual Test Passed
  ↓ (a test_notification attempt recorded status = "success")
Ready
```

- **Configured** = the provider's required credential/env vars are present and, where already validated (Slack/Teams webhook shape), well-formed. Reuses the existing `<provider>_configured` fields; does not require `INTEGRATION_MODE=real`, `SOAR_ENV=staging`, or `SOAR_REAL_<PROVIDER>_ENABLED` to be true.
- **Tested** = `Passed` (latest `test_notification` attempt has `status = "success"`), `Failed` (latest attempt has `status` in `{"failed", "timeout"}`), or `Never Tested` (no `test_notification` attempt exists yet for this provider).
- **Ready** = `Configured` **AND** `Tested = Passed`. This is a new, human-verified meaning of "ready," and is explicitly not the same field as the adapter layer's existing `real_mode_ready` (which only reflects deployment-guard state, not proof of delivery). Both must be documented side by side wherever they could be confused, and the implementing child spec must not rename or repurpose the existing `real_mode_ready` field — it is relied on elsewhere (`integrations/integration_registry.py#get_integration_status`).

## Tested Outcome Mapping

A test-send attempt can reach one of three outcomes, and they must not be conflated:

1. **Blocked before attempt** — one or more of `INTEGRATION_MODE=real`, `SOAR_ENV` allowlist, `SOAR_REAL_<PROVIDER>_ENABLED`, or credentials is not satisfied. No external call was made. Recorded with `status = "blocked"` (an existing valid value in the table's `CHECK` constraint). This should read as "Never Tested (blocked: <reason>)" or an equivalent clearly-worded state in the UI — not as "Failed" — because a missing deployment guard is an environment issue, not proof that the provider itself doesn't work.
2. **Attempted and failed** — the guarded real call was made and did not succeed (non-2xx HTTP, SMTP rejection, timeout, transient network error). Recorded with `status` in `{"failed", "timeout"}`. Reads as **Failed**.
3. **Attempted and succeeded** — the guarded real call succeeded. Recorded with `status = "success"`. Reads as **Passed**.

This distinction is exactly why Teams, Email, and Webhook must each be "proven or failed clearly" rather than assumed broken: today it is not known whether their prior lack of proof is a guard/config issue (outcome 1) or a genuine delivery failure (outcome 2).

## Test-Send Safety Constraints

- Restricted to exactly `slack`, `teams`, `email`, `webhook`. Any other adapter name, including `firewall`, is rejected (404 or 400, matching the existing `_resolved_adapter_or_404` precedent), not silently ignored.
- Must invoke the adapter's existing four-guard model unmodified — a test send that is not Configured or not deployment-guard-ready must fail closed exactly like a playbook-triggered send would, never send anyway, and never fabricate a passed result.
- Must go through the existing per-adapter rate limiter so repeated test clicks cannot become a spam vector against a real Slack channel, Teams channel, or inbox.
- Must send an unmistakable test payload (e.g., message text clearly marked as a manual readiness test, not a real security event) so a delivered test is never confused with a real alert notification by anyone reading the channel/inbox.
- Must record exactly one `notification_delivery_attempts` row per test click (no silent retries), consistent with the "no fake success, no endless retry" principle this whole roadmap is built on, even though playbook-specific retry/skip behavior itself is out of scope for this spec.
- Must never log or return the underlying webhook URL, SMTP credentials, or webhook auth token, reusing the existing redaction helpers rather than adding a new, separately-maintained redaction path.

## Desired UI (Per Provider)

For each of Slack, Teams, Email, and Webhook, a card or row showing:

- **Configured:** Yes / No
- **Tested:** Passed / Failed / Never Tested
- **Ready:** Yes / No
- **Missing Configuration:** list of env var names only (e.g., `SLACK_WEBHOOK_URL`) — empty when Configured is Yes
- **Last Test:** timestamp, or "Never" when no test has been recorded
- **Test button:** triggers one manual test send; disabled (or clearly explained) when not Configured, since an unconfigured provider cannot be meaningfully tested

No Firewall card and no Firewall test button appear anywhere in this UI. This surface should be new/separate from the existing `IntegrationStatusPanel.js` circuit-breaker-and-mixed-status view, not an additional set of fields bolted onto it — directly addressing the roadmap's founding complaint that the current page mixes too many concepts, rather than adding a fifth concept to the same page.

## Backend Work (Planned, Not Implemented Here)

1. A per-provider readiness helper that returns `configured`, `missing_configuration` (list of env var names), independent of deployment-mode guards, for each of Slack/Teams/Email/Webhook.
2. A new orchestration function (e.g. in a new module such as `core/notification_test_service.py`) that: validates the adapter name against the four allowed providers; checks `Configured`; if not Configured, returns a clear "not configured" result without attempting a send and without writing a `blocked`/`failed` row (nothing to test yet, so no attempt exists); if Configured, executes the adapter's existing real-mode path with a `test_notification` action and a synthetic `correlation_id`/`idempotency_key`; records the outcome via `create_notification_delivery_attempt`.
3. A new `POST /integrations/<adapter_name>/test-send` route in `routes/integration_routes.py`, `login_required` + `super_admin_required`, rejecting `firewall` and unknown adapter names.
4. A new `GET` readiness surface (e.g. `GET /integrations/notification-readiness`) returning, for each of the four providers, `configured`, `missing_configuration`, `tested` (`passed`/`failed`/`never_tested`), `ready`, and `last_test_at` — built from (1) plus a query against `notification_delivery_attempts` filtered by `provider` and the new `action = "test_notification"` marker.
5. An additive `action` filter parameter on `list_notification_delivery_attempts` (`core/notification_delivery_store.py`).
6. A `test_notification` supported action added to each of the four adapters' `supported_actions` sets (or an equivalent test-marking approach decided during implementation) — not added to `FirewallSimulationAdapter`.

## Frontend Work (Planned, Not Implemented Here)

1. A new readiness panel (or a clearly separated section) rendering the per-provider card described above for Slack/Teams/Email/Webhook only.
2. A new `integrationService.js` function calling the new `GET` readiness endpoint.
3. A new `integrationService.js` function calling the new `POST /integrations/<adapter>/test-send` endpoint, mirroring the existing `postCircuitControl` fetch pattern (`buildSiemPath`, `parseJsonResponse`, `getApiErrorMessage`).
4. A confirmation step before sending (e.g., a confirm dialog stating a real test message will be sent), since this is a real, singular external action, not a passive read.
5. Clear, honest rendering of all three Tested outcomes (Passed / Failed / Never Tested — including the "blocked before attempt" case reading as a form of Never Tested with a guard reason, per "Tested Outcome Mapping" above), never collapsing "blocked by missing guard" into a bare "Failed."

## Database Changes

None expected. The existing `notification_delivery_attempts` table (`migrations/0008_soar_notification_delivery.sql`) already has every column this spec needs: `provider`, `mode`, `status` (including the `blocked` value already needed for the guard-blocked case), `adapter_name`, `action` (to carry the new `test_notification` marker), `failure_code`/`failure_message` (already redacted at write time), and `created_at`/`requested_at`/`completed_at` (source of "Last Test"). `playbook_execution_id`, `incident_id`, `approval_request_id`, and `alert_id` are already nullable and are simply left `NULL` for a manual test row.

## Explicitly Out Of Scope For This Spec

- Active/Inactive provider toggles or any durable "allowed in production" state (`soar-notification-provider-active-controls`).
- Playbook executor changes, notification skipping, or skip-by-policy outcomes (`soar-playbook-notification-enforcement`).
- Delivery-history dashboards, aggregate views, or "last successful/failed delivery across all sends" reporting beyond this spec's own Last Test field (`soar-notification-delivery-history`).
- Any Firewall real-mode work of any kind.
- Any Azure work.
- Any VM work.
