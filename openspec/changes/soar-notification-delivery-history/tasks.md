## 1. Audit and Planning

- [ ] 1.1 Reconfirm `notification_delivery_attempts` schema in `schema.sql`, `migrations/0008_soar_notification_delivery.sql`, and response-outcome linkage from `migrations/0012_soar_response_outcomes.sql`.
- [ ] 1.2 Reconfirm `core/notification_delivery_store.py` append-only behavior, existing filters, redaction denylist, and `sanitize_failure_message()` behavior.
- [ ] 1.3 Reconfirm integration adapter logging for Slack, Teams, Email, and Webhook is secret-free but not the primary query source for delivery history.
- [ ] 1.4 Reconfirm playbook notification delivery records from `engines/playbook_step_executor.py` include provider, mode, status, timestamps, failure details, and safe metadata.
- [ ] 1.5 Reconfirm `/integrations/status`, `/notification-deliveries`, and `/metrics/notifications` current contracts before adding any summary endpoint.
- [ ] 1.6 Reconfirm SOAR Integrations UI fields in `IntegrationStatusPanel.js`, including existing last-delivery placeholders.
- [ ] 1.7 Reconfirm existing tests for delivery attempts, integration routes, notification metrics, playbook delivery records, and frontend integration status.
- [ ] 1.8 Reconfirm manual test-send rows from `soar-notification-readiness-test-buttons` use the same table and identify the implemented manual-test marker.

## 2. Backend Queries

- [ ] 2.1 Add or reuse store-level query support for latest successful real delivery per provider.
- [ ] 2.2 Add or reuse store-level query support for latest failed real delivery per provider.
- [ ] 2.3 Add or reuse store-level query support for latest manual test per provider.
- [ ] 2.4 Add recent-attempt query support per provider with bounded limits.
- [ ] 2.5 Add or reuse an `action` filter when needed for manual test rows.
- [ ] 2.6 Classify attempts as `test`, `real_delivery`, or `simulation`.
- [ ] 2.7 Ensure all failure reasons use sanitized stored fields or safe generic formatting.

## 3. Backend APIs

- [ ] 3.1 Add a provider-level delivery summary endpoint if existing routes cannot cleanly serve the UI.
- [ ] 3.2 Return Slack, Teams, Email, and Webhook in every summary response, including empty states.
- [ ] 3.3 Include last successful delivery, last failed delivery, last tested, delivery status, and recent attempts per provider.
- [ ] 3.4 Preserve existing `/notification-deliveries` as read-only attempt history.
- [ ] 3.5 Preserve existing `/integrations/status` behavior unless extended backward-compatibly.
- [ ] 3.6 Verify no API response includes webhook URLs, SMTP credentials, tokens, headers, raw payloads, raw responses, or secret values.

## 4. Frontend

- [ ] 4.1 Add frontend service function(s) for the delivery summary API.
- [ ] 4.2 Show Last successful delivery for Slack, Teams, Email, and Webhook.
- [ ] 4.3 Show Last failed delivery with a secret-free reason.
- [ ] 4.4 Show Last tested from manual test rows.
- [ ] 4.5 Show provider-level delivery status.
- [ ] 4.6 Show recent attempts in a collapsed or secondary detail area.
- [ ] 4.7 Label Simulation as no external call made.
- [ ] 4.8 Keep Firewall excluded from real delivery evidence and label it simulation/dry-run only if displayed nearby.

## 5. Tests

- [ ] 5.1 Add store tests for last success, last failure, last tested, recent attempts, empty providers, and ordering.
- [ ] 5.2 Add route tests for RBAC, payload shape, empty states, secret safety, failure reason formatting, and attempt classification.
- [ ] 5.3 Add tests proving Simulation successes do not count as Delivered.
- [ ] 5.4 Add tests proving manual test failures do not count as last failed playbook delivery.
- [ ] 5.5 Add frontend service tests for delivery summary fetch/error handling.
- [ ] 5.6 Add SOAR Integrations UI tests for visible evidence, collapsed recent attempts, Simulation labeling, empty states, and secret-free failure reasons.
- [ ] 5.7 Confirm existing delivery-route, metrics, integration-route, playbook-executor, and frontend integration-status tests continue passing.

## 6. Validation

- [ ] 6.1 Run relevant backend tests.
- [ ] 6.2 Run relevant frontend tests.
- [ ] 6.3 Run `openspec validate soar-notification-delivery-history --strict`.
- [ ] 6.4 Run `git diff --check`.

## 7. Explicitly Deferred

- [ ] 7.1 Manual test-send button implementation remains in `soar-notification-readiness-test-buttons`.
- [ ] 7.2 Provider Active/Inactive toggles remain in `soar-notification-provider-active-controls`.
- [ ] 7.3 Playbook enforcement changes remain in `soar-playbook-notification-enforcement`.
- [ ] 7.4 Real notification configuration is out of scope.
- [ ] 7.5 New notification providers are out of scope.
- [ ] 7.6 Real firewall execution is out of scope and requires a separate explicitly approved OpenSpec.
- [ ] 7.7 VM and Azure work are out of scope.
