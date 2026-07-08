## Overview

`soar-notification-delivery-history` is the fourth child implementation spec under `soar-notification-integration-controls-roadmap`. It answers one operator question:

> What actually happened when this notification provider was tested or used?

This spec is evidence display only. It must not send notifications, add test buttons, toggle provider Active state, change playbook enforcement, configure providers, touch the VM, touch Azure, or introduce any real firewall behavior.

## Parent Roadmap Terminology

This child spec uses the parent roadmap definitions:

- **Configured**: required env vars/secrets for a provider are present.
- **Tested**: a manual test notification through that provider succeeded.
- **Active**: a human has explicitly allowed playbooks to use this provider for real delivery.
- **Delivered**: a real notification was actually sent successfully.
- **Simulation**: no external call was made.

Code existing for a provider is not evidence that the provider is Configured, Tested, Active, or Delivered.

## Audit Summary

- `notification_delivery_attempts` exists in `schema.sql` and `migrations/0008_soar_notification_delivery.sql`.
- The table stores `provider`, `mode`, `status`, playbook/incident/approval/alert linkage, `adapter_name`, `action`, `requested_at`, `started_at`, `completed_at`, `created_at`, `failure_code`, `failure_message`, `timeout_seconds`, `circuit_breaker_state`, and redacted `metadata`.
- `migrations/0012_soar_response_outcomes.sql` adds `decision_id` and `soar_correlation_id` to `notification_delivery_attempts`.
- The store module `core/notification_delivery_store.py` is append-only at the application layer. It provides `create_notification_delivery_attempt`, `get_notification_delivery_attempt`, and `list_notification_delivery_attempts`.
- Store redaction already removes unsafe metadata keys and scrubs URL-like values. `sanitize_failure_message()` removes URL-like segments from persisted failure text.
- Current store listing filters by provider, mode, status, correlation/idempotency identifiers, playbook/incident/approval/alert IDs, and adapter name. It does not currently filter by `action`.
- `engines/playbook_step_executor.py` records notification attempts for `notify_slack`, `notify_teams`, `notify_email`, and `notify_webhook`, maps adapter outcomes to delivery statuses, stores mode from adapter results, and records `metadata.simulated` and `metadata.executed`.
- Current playbook attempt rows can support last success and last failure per provider with no migration.
- `routes/notification_delivery_routes.py` exposes read-only `GET /notification-deliveries` and `GET /notification-deliveries/<id>`, returning persisted attempts plus latest response outcome data.
- `routes/metrics_routes.py` exposes aggregate notification metrics, but not provider-level last success/failure/tested evidence.
- `routes/integration_routes.py` exposes `GET /integrations/status` and circuit-breaker controls. It does not include delivery-history summary fields today.
- `integrations/slack_adapter.py`, `teams_adapter.py`, `email_adapter.py`, and `webhook_adapter.py` all log real-mode adapter attempts via `core.integration_audit.log_integration_execution_attempt`, but the delivery-history evidence should come from `notification_delivery_attempts` because it is queryable and already tied to playbook/test contexts.
- `frontend/src/components/IntegrationStatusPanel.js` already renders placeholders for `last_successful_delivery`, `last_delivery`, and `last_tested` if present on adapter rows, but `/integrations/status` does not populate those fields today.
- Existing tests cover delivery-store behavior (`tests/test_notification_delivery_store.py`), delivery read routes (`tests/test_notification_delivery_routes.py`), notification metrics (`tests/test_notification_delivery_metrics_routes.py`), integration routes (`tests/test_integration_routes.py`), adapter behavior (`tests/test_integration_adapters.py`), playbook delivery recording (`tests/test_playbook_step_executor.py`), and frontend integration status/service behavior (`frontend/src/components/IntegrationStatusPanel.test.js`, `frontend/src/services/integrationService.test.js`).

## Existing Data Sufficiency

No new migration is expected for this child. The existing table can answer:

- Last successful delivery: latest row per provider with `mode = "real"`, `status = "success"`, and a non-test delivery action.
- Last failed delivery: latest row per provider with `mode = "real"` and `status IN ("failed", "timeout", "blocked")`, excluding manual test rows when displaying playbook delivery failure.
- Recent attempts: newest rows per provider using existing timestamps and statuses.
- Secret-free error reason: existing `failure_code`, sanitized `failure_message`, and safe metadata fields such as failure classification.
- Simulation evidence: rows with `mode = "simulation"` or safe metadata where `simulated = true` and `executed = false`.

Last tested depends on child spec 1. `soar-notification-readiness-test-buttons` plans to write manual test-send results to `notification_delivery_attempts` with an `action` marker such as `test_notification`. This child should consume that convention. If implementation order reveals a different marker from child 1, this child must align to the implemented marker rather than invent a second source of truth.

## Attempt Classification

The read model should classify each row into an operator-facing attempt type:

- `test`: manual test-send attempt from the first child spec, expected marker `action = "test_notification"`.
- `real_delivery`: real playbook notification attempt, `mode = "real"` and not a test marker.
- `simulation`: no external call was made, `mode = "simulation"` or safe metadata shows `simulated = true` and `executed = false`.

The UI must not label a Simulation row as Delivered. Delivered requires a real successful send.

## Provider Summary Shape

Recommended summary shape per provider:

- `provider`
- `last_successful_delivery`
- `last_failed_delivery`
- `last_tested`
- `delivery_status`
- `recent_attempts`

Each attempt summary should include:

- `id`
- `provider`
- `attempt_type`
- `mode`
- `status`
- `action`
- `timestamp` from `completed_at`, then `started_at`, then `requested_at`, then `created_at`
- `failure_code`
- `failure_reason`
- `playbook_execution_id`
- `playbook_step_index`
- `alert_id`
- `incident_id`
- `approval_request_id`
- `simulated`
- `executed`

The response must not include secret metadata, webhook URLs, SMTP credentials, tokens, raw headers, raw payloads, or raw provider responses.

## Backend Work Planned

1. Add delivery-history query helpers, likely in `core/notification_delivery_store.py`, for:
   - latest success per provider
   - latest failure per provider
   - latest manual test per provider
   - recent attempts per provider
2. Add or reuse an `action` filter to support `test_notification` queries. If child spec 1 already added it, reuse it.
3. Add a provider-level read endpoint if existing routes cannot cleanly serve the SOAR Integrations UI. Likely endpoint:
   - `GET /integrations/notification-delivery-summary`
4. Keep existing `GET /notification-deliveries` as the lower-level attempt list. Do not convert it into a mutation route.
5. Format failure reasons with safe precedence:
   - `failure_code` plus sanitized `failure_message` when present
   - safe metadata failure classification when present
   - a generic status-derived reason when no safe details exist
6. Return all four providers (`slack`, `teams`, `email`, `webhook`) even when no attempts exist, with null last fields and empty recent attempts.
7. Clearly separate test attempts, real delivery attempts, and simulation attempts in the response.

## Frontend Work Planned

1. Add integration service function(s) for the provider delivery summary endpoint.
2. Extend the SOAR Integrations experience to show, for each Slack/Teams/Email/Webhook provider:
   - Last successful delivery
   - Last failed delivery
   - Last tested
   - Current provider delivery status
   - Secret-free failure reason
   - Recent attempts
3. Keep summary fields visible and advanced details collapsed.
4. Label Simulation clearly as no external call made.
5. Avoid implying a provider is Delivered when the only success is Simulation or when a manual test is blocked.
6. Exclude Firewall from real delivery history. If Firewall appears nearby, label it simulation/dry-run only and do not show real delivery evidence controls for it.

## Database Changes

No database changes are expected. A migration should only be introduced if implementation discovers the first child spec did not create a stable way to distinguish manual test rows and the existing `action` column cannot safely serve that purpose. The preferred path is no migration and no new provider-history table.

## Endpoint Options

Preferred:

- `GET /integrations/notification-delivery-summary`
  - Auth: analyst or super-admin.
  - Returns one summary per provider.
  - Backed by `notification_delivery_attempts`.

Alternative:

- Extend `GET /integrations/status` with a nested, backward-compatible `delivery_summary` object per adapter.

The preferred endpoint keeps delivery evidence separate from the already crowded integration status/circuit-breaker response, while still letting the SOAR Integrations UI compose both.

## Testing Strategy

- Store tests for latest success, latest failure, latest tested, recent attempts ordering, provider default rows, and action/test filtering.
- Route tests for auth/RBAC, empty-state payloads, provider summaries, no secret leakage, failure reason formatting, and distinction between Simulation/test/real delivery.
- Playbook executor regression tests confirming existing delivery attempt rows still support summary queries.
- Frontend service tests for the summary endpoint.
- Integration Status UI tests for visible summary fields, collapsed recent attempts, secret-free failure reason rendering, empty states, Simulation labeling, and Firewall exclusion.
- Existing notification delivery route, metrics, integration route, and frontend integration status tests should continue passing.

## Explicitly Out Of Scope

- Manual test-send button implementation.
- Provider Active/Inactive toggles.
- Playbook enforcement changes.
- Real notification configuration.
- New notification providers.
- Real firewall execution.
- VM or Azure work.
- Exposing secret values.
- Sending Slack, Teams, Email, Webhook, or Firewall notifications.
