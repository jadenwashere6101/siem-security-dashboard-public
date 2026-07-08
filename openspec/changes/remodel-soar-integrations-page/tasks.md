## 1. Audit and Planning

- [ ] 1.1 Reconfirm current `IntegrationStatusPanel` data shape from `getIntegrationStatus()`.
- [ ] 1.2 Map each adapter to an operational description and default/core playbook usage label.
- [ ] 1.3 Identify which requested fields can be derived from existing status data and which must show `Not available` pending future backend work.
- [ ] 1.4 Confirm no backend endpoint, adapter execution, database, migration, Azure, VM, or real delivery changes are needed for v1.

## 2. UI Remodel

- [ ] 2.1 Replace the current implementation-detail-first layout with one operational status card per adapter.
- [ ] 2.2 Add primary fields for Current Mode, Health, Used By, External Delivery, Ready for Real Mode, Last Delivery, and Last Tested.
- [ ] 2.3 Add missing-configuration display that shows env variable names only and never values.
- [ ] 2.4 Add concise adapter descriptions for Slack, Teams, Email, Firewall, and Webhook.
- [ ] 2.5 Keep supported actions visible as compact tags.
- [ ] 2.6 Reduce explanatory paragraphs and use badges/status rows for the primary view.
- [ ] 2.7 Preserve the existing dark theme and visual style.

## 3. Advanced Section

- [ ] 3.1 Move circuit breaker details into a collapsed Advanced section per adapter.
- [ ] 3.2 Keep raw internal fields available inside Advanced for debugging.
- [ ] 3.3 Keep super-admin simulation controls inside Advanced only.
- [ ] 3.4 Rename simulation control labels to operational wording while preserving current API calls and semantics.
- [ ] 3.5 Ensure analysts retain read-only access and do not see privileged controls.

## 4. Frontend Safety and Compatibility

- [ ] 4.1 Preserve the existing `/integrations/status` service contract.
- [ ] 4.2 Preserve loading, empty, and error states.
- [ ] 4.3 Ensure missing or partial adapter fields do not crash the page.
- [ ] 4.4 Ensure the page does not create, test, execute, or trigger any real integration traffic.
- [ ] 4.5 Ensure firewall is clearly shown as dry-run/simulation-only.

## 5. Tests

- [ ] 5.1 Update `IntegrationStatusPanel` tests for operational fields and badges.
- [ ] 5.2 Add tests for missing env variable names without secret values.
- [ ] 5.3 Add tests that Advanced sections are collapsed by default and contain internals when expanded.
- [ ] 5.4 Add tests that renamed super-admin controls still call existing circuit breaker service functions.
- [ ] 5.5 Add tests that no test-connection, run-adapter, real-delivery, or execute controls appear.
- [ ] 5.6 Keep existing integration service tests passing.

## 6. Validation

- [ ] 6.1 Run relevant frontend tests for the Integration Status panel and service.
- [ ] 6.2 Run backend integration tests only if implementation unexpectedly touches backend code.
- [ ] 6.3 Run `openspec validate remodel-soar-integrations-page --strict`.
- [ ] 6.4 Run `git diff --check`.

## 7. Deferred Backend Enhancements

- [ ] 7.1 Defer dynamic playbook usage counts to a future backend/API spec if static default usage is insufficient.
- [ ] 7.2 Defer durable Last Tested support and test-action APIs to a future backend spec.
- [ ] 7.3 Defer durable Last Delivery summaries to a future backend/query spec if existing data cannot be reused safely.
- [ ] 7.4 Defer real firewall execution to a separate future spec only if explicitly approved.
