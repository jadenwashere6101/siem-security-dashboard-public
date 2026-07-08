## 1. Audit and Planning

- [ ] 1.1 Reconfirm no durable provider Active/Inactive table or store exists.
- [ ] 1.2 Reconfirm `notification_delivery_attempts` is append-only delivery evidence and not a provider configuration table.
- [ ] 1.3 Reconfirm current `/integrations/status` readiness fields can feed Configured/Ready display.
- [ ] 1.4 Reconfirm prior readiness/test-buttons child state, if present, can feed Tested state; otherwise plan `Never Tested` fallback.
- [ ] 1.5 Reconfirm Firewall is excluded from Active controls and remains simulation/dry-run only.

## 2. Backend Storage

- [ ] 2.1 Add a migration for durable provider control storage, unless an equivalent durable table already exists by implementation time.
- [ ] 2.2 Store provider active state for `slack`, `teams`, `email`, and `webhook` only.
- [ ] 2.3 Default all providers to inactive.
- [ ] 2.4 Store or read Tested state consistently with the prior test-buttons child spec.
- [ ] 2.5 Ensure missing rows degrade to inactive and never-tested safely.
- [ ] 2.6 Keep all stored metadata secret-free.

## 3. Backend APIs

- [ ] 3.1 Add a read endpoint for provider controls and readiness summary.
- [ ] 3.2 Add a super-admin-only update endpoint for Active/Inactive state.
- [ ] 3.3 Reject unknown providers.
- [ ] 3.4 Reject Firewall as an activatable provider.
- [ ] 3.5 Implement configured/tested activation gating or warning behavior explicitly.
- [ ] 3.6 Allow deactivation regardless of Configured/Tested state.
- [ ] 3.7 Preserve the existing `/integrations/status` contract unless intentionally extended in a backward-compatible way.

## 4. RBAC and Audit

- [ ] 4.1 Allow analysts and super-admins to read provider controls.
- [ ] 4.2 Allow only super-admins to toggle Active/Inactive state.
- [ ] 4.3 Audit activation and deactivation with actor, provider, previous state, new state, and non-secret gating context.
- [ ] 4.4 Ensure audit records do not include webhook URLs, SMTP passwords, tokens, headers, or secret values.

## 5. Frontend

- [ ] 5.1 Add frontend service functions for reading and updating provider controls.
- [ ] 5.2 Add Active/Inactive toggles for Slack, Teams, Email, and Webhook on the SOAR Integrations page.
- [ ] 5.3 Show Configured, Tested, Active, and Ready labels with parent-roadmap terminology.
- [ ] 5.4 Show disabled or warning states when Configured is false or Tested is not passed.
- [ ] 5.5 Show missing config env variable names only.
- [ ] 5.6 Exclude Firewall from Active toggles and label it simulation/dry-run only.
- [ ] 5.7 Keep analysts read-only.
- [ ] 5.8 Do not add manual test-send buttons in this spec.

## 6. Tests

- [ ] 6.1 Add migration/store tests for defaults and persistence.
- [ ] 6.2 Add backend route tests for read/update success, RBAC, unknown provider rejection, Firewall rejection, activation gating, and audit behavior.
- [ ] 6.3 Add frontend service tests for provider-control endpoints.
- [ ] 6.4 Add Integration Status panel tests for toggles, disabled/warning states, analyst read-only behavior, firewall exclusion, and secret safety.
- [ ] 6.5 Confirm existing integration route and frontend integration tests still pass.

## 7. Validation

- [ ] 7.1 Run relevant backend tests.
- [ ] 7.2 Run relevant frontend tests.
- [ ] 7.3 Validate migrations against a test database using existing migration workflow.
- [ ] 7.4 Run `openspec validate soar-notification-provider-active-controls --strict`.
- [ ] 7.5 Run `git diff --check`.

## 8. Explicitly Deferred

- [ ] 8.1 Manual test-send implementation remains in `soar-notification-readiness-test-buttons`.
- [ ] 8.2 Playbook executor enforcement remains in `soar-playbook-notification-enforcement`.
- [ ] 8.3 Skipped-by-policy outcomes remain in `soar-playbook-notification-enforcement`.
- [ ] 8.4 Delivery history dashboards remain in `soar-notification-delivery-history`.
- [ ] 8.5 Real firewall execution remains out of scope and requires a separate explicitly approved OpenSpec.
