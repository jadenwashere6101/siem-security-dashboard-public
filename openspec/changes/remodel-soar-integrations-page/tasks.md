## 1. Audit and Planning

- [x] 1.1 Reconfirm current `IntegrationStatusPanel` data shape from `getIntegrationStatus()`.
- [x] 1.2 Map each adapter to an operational description and default/core playbook usage label.
- [x] 1.3 Identify which requested fields can be derived from existing status data and which must show `Not available` pending future backend work.
- [x] 1.4 Confirm no backend endpoint, adapter execution, database, migration, Azure, VM, or real delivery changes are needed for v1.

## 2. UI Remodel

- [x] 2.1 Replace the current implementation-detail-first layout with one operational status card per adapter.
- [x] 2.2 Add primary fields for Current Mode, Health, Used By, External Delivery, Ready for Real Mode, Last Delivery, and Last Tested.
- [x] 2.3 Add missing-configuration display that shows env variable names only and never values.
- [x] 2.4 Add concise adapter descriptions for Slack, Teams, Email, Firewall, and Webhook.
- [x] 2.5 Keep supported actions visible as compact tags.
- [x] 2.6 Reduce explanatory paragraphs and use badges/status rows for the primary view.
- [x] 2.7 Preserve the existing dark theme and visual style.

## 3. Advanced Section

- [x] 3.1 Move circuit breaker details into a collapsed Advanced section per adapter.
- [x] 3.2 Keep raw internal fields available inside Advanced for debugging.
- [x] 3.3 Keep super-admin simulation controls inside Advanced only.
- [x] 3.4 Rename simulation control labels to operational wording while preserving current API calls and semantics.
- [x] 3.5 Ensure analysts retain read-only access and do not see privileged controls.

## 4. Frontend Safety and Compatibility

- [x] 4.1 Preserve the existing `/integrations/status` service contract.
- [x] 4.2 Preserve loading, empty, and error states.
- [x] 4.3 Ensure missing or partial adapter fields do not crash the page.
- [x] 4.4 Ensure the page does not create, test, execute, or trigger any real integration traffic.
- [x] 4.5 Ensure firewall is clearly shown as dry-run/simulation-only.

## 5. Tests

- [x] 5.1 Update `IntegrationStatusPanel` tests for operational fields and badges.
- [x] 5.2 Add tests for missing env variable names without secret values.
- [x] 5.3 Add tests that Advanced sections are collapsed by default and contain internals when expanded.
- [x] 5.4 Add tests that renamed super-admin controls still call existing circuit breaker service functions.
- [x] 5.5 Add tests that no test-connection, run-adapter, real-delivery, or execute controls appear.
- [x] 5.6 Keep existing integration service tests passing.

## 6. Validation

- [x] 6.1 Run relevant frontend tests for the Integration Status panel and service.
- [x] 6.2 Run backend integration tests only if implementation unexpectedly touches backend code.
- [x] 6.3 Run `openspec validate remodel-soar-integrations-page --strict`.
- [x] 6.4 Run `git diff --check`.

## 7. Deferred Backend Enhancements

- [x] 7.1 Defer dynamic playbook usage counts to a future backend/API spec if static default usage is insufficient.
- [x] 7.2 Defer durable Last Tested support and test-action APIs to a future backend spec.
- [x] 7.3 Defer durable Last Delivery summaries to a future backend/query spec if existing data cannot be reused safely.
- [x] 7.4 Defer real firewall execution to a separate future spec only if explicitly approved.
