## Why

The parent roadmap `soar-notification-integration-controls-roadmap` defines delivery evidence as the fourth child because operators need factual proof of what actually happened after providers can be tested, activated, and enforced. The current codebase already records notification delivery attempts, but the SOAR Integrations UI does not yet surface clear provider-level evidence such as last success, last failure, last tested, secret-free error reasons, or recent attempts.

## What Changes

- Define provider-level delivery history for Slack, Teams, Email, and Webhook.
- Plan read-only backend summary behavior for last successful delivery, last failed delivery, last tested, recent attempts, and provider-level delivery status.
- Reuse the existing append-only `notification_delivery_attempts` table wherever possible.
- Treat manual test-send rows from `soar-notification-readiness-test-buttons` as the source for Last Tested when they are recorded with the agreed manual-test marker.
- Distinguish Simulation, manual test attempts, and real playbook delivery attempts in backend responses and UI labels.
- Show secret-free failure reasons using the existing delivery-store redaction and failure-message sanitization behavior.
- Add clear SOAR Integrations UI evidence without overwhelming the page, keeping detailed attempt lists collapsed where appropriate.
- Keep this spec read-oriented: it does not add test-send buttons, provider Active toggles, playbook enforcement, real provider configuration, or external notification behavior.

## Capabilities

### New Capabilities
- `soar-notification-delivery-history`: exposes and displays operational delivery evidence for Slack, Teams, Email, and Webhook from existing delivery-attempt records.

### Modified Capabilities
(none)

## Impact

- **Affected backend (future implementation only):** likely `core/notification_delivery_store.py` for summary/recent-attempt queries, `routes/integration_routes.py` or a focused delivery-history route for provider-level summaries, and existing delivery-history read contracts.
- **Affected frontend (future implementation only):** SOAR Integrations UI and integration service functions for provider evidence fields and recent attempts.
- **Affected database:** no new migration expected. Existing `notification_delivery_attempts` columns are sufficient for the planned evidence if manual test sends use the same table and a stable manual-test marker.
- **Runtime behavior:** none from this spec creation. Future implementation is read-only except for normal test/playbook attempts owned by prior child specs.
- **External systems:** none. This child must not configure or contact Slack, Teams, Email, Webhook, Firewall, VM, or Azure.
- **Parent roadmap:** this child belongs under `soar-notification-integration-controls-roadmap`; no parent-roadmap file changes are required by this spec.
