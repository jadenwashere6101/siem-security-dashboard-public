## Overview

`soar-notification-provider-active-controls` defines durable provider Active/Inactive controls for notification providers. It answers one operational question:

> Has a super-admin allowed playbooks to use this provider?

This spec does not make playbooks obey that state yet. It creates the durable state and UI/API controls that the later `soar-playbook-notification-enforcement` child spec will consume.

## Parent Roadmap Terminology

This child spec uses the parent roadmap definitions:

- **Configured**: required env vars/secrets for a provider are present.
- **Tested**: a manual test notification through that provider succeeded.
- **Active**: a human has explicitly allowed playbooks to use this provider for real delivery.
- **Delivered**: a real notification was actually sent successfully.
- **Simulation**: no external call was made.

Code existing for a provider is not evidence that the provider is Configured, Tested, Active, or Delivered.

## Audit Summary

- `notification_delivery_attempts` exists in `migrations/0008_soar_notification_delivery.sql`, but it is append-only attempt history. It should not be reused as the primary provider Active/Inactive configuration store.
- No durable per-provider Active/Inactive table or equivalent store was found.
- No current provider-status table was found.
- `/integrations/status` currently reports adapter readiness and in-memory simulated circuit state, but it does not expose durable provider Active state.
- Existing integration routes use `analyst_or_super_admin_required` for read status and `super_admin_required` for mutation-style circuit controls.
- Existing frontend integration service calls `/integrations/status` and circuit-breaker control endpoints only.
- Existing route tests cover integration status RBAC, safe readiness data, and circuit breaker controls.
- Existing frontend tests cover the Integration Status panel and integration service behavior.
- The parent roadmap lists `soar-notification-readiness-test-buttons` as the prior child. This Active-controls spec should consume Tested state from that prior child once implemented. If that prior child is not implemented yet, this spec should define a safe fallback of `Never Tested`.

## Storage Design

Implementation should add durable backend storage for Slack, Teams, Email, and Webhook only. Firewall must not be present as an activatable provider.

Recommended table shape:

- `notification_provider_controls`
  - `provider` text/varchar primary key, constrained to `slack`, `teams`, `email`, `webhook`.
  - `active` boolean not null default false.
  - `tested_status` text/varchar not null default `never_tested`, constrained to `never_tested`, `passed`, `failed`.
  - `tested_at` timestamptz nullable.
  - `last_test_error` text nullable, secret-redacted.
  - `updated_at` timestamptz not null default now.
  - `updated_by` text nullable.
  - optional `metadata` jsonb default `{}` for future non-secret fields.

If the prior test-buttons child creates a separate durable test-result table, this child may instead store only `provider` and `active` here and join/read latest test state from that table. The implementation must avoid duplicating conflicting sources of truth.

Defaults:

- All providers default to `active=false`.
- Missing rows should be treated as inactive and `tested_status=never_tested`.
- Implementations may seed four rows in the migration or synthesize defaults in the store layer and create rows on first update.

## API Design

Likely endpoints:

- `GET /integrations/provider-controls`
  - Auth: analyst or super-admin.
  - Returns Slack, Teams, Email, and Webhook provider control state.
  - Includes existing readiness/configured data where practical by combining with current integration readiness helpers.
  - Must not include secret values.

- `PATCH /integrations/provider-controls/<provider>`
  - Auth: super-admin only.
  - Body: `{ "active": true|false }`.
  - Reject unknown providers and reject `firewall`.
  - Return the updated provider control state.
  - Audit the actor, provider, previous active state, new active state, and non-secret readiness/tested context.

Activation gating decision:

- Preferred behavior: block activation when Configured is false.
- Preferred behavior: block activation when Tested is not `passed`, unless product explicitly chooses warning-based activation.
- This child spec should require the implementation to make the behavior explicit in code, UI copy, and tests.
- Deactivation should always be allowed by super-admins.

## Frontend Design

The SOAR Integrations page should add Active/Inactive controls for Slack, Teams, Email, and Webhook.

Each provider row/card should show:

- Configured: Yes/No.
- Tested: Passed/Failed/Never Tested.
- Active: On/Off.
- Ready: Yes/No.
- Missing config env names only.
- Toggle control for Active/Inactive visible to super-admins.
- Read-only state for analysts.

Firewall behavior:

- Firewall should show dry-run/simulation-only status.
- Firewall must not render an Active toggle.
- UI must avoid implying Firewall can be enabled for real execution.

No secret values should be rendered. The UI may show env variable names such as `SLACK_WEBHOOK_URL`, but never values.

## Backend Boundary

This spec must not:

- Send a Slack, Teams, Email, or Webhook notification.
- Add manual test-send endpoints.
- Change adapter real-mode guard behavior.
- Change playbook executor behavior.
- Add skipped-by-policy outcomes.
- Add delivery history dashboards.
- Add real firewall execution.
- Touch VM, Azure, pfSense, ingestion, detections, or response-action behavior.

## Future Child Integration

Later child specs should consume this state:

- `soar-playbook-notification-enforcement` will read provider Active state before notification steps and skip inactive providers by policy.
- `soar-notification-delivery-history` will show Delivered evidence and may combine it with Active state.

## Validation

Implementation should include:

- Migration validation for the new durable provider control storage.
- Backend tests for read/update endpoints, default inactive state, unknown provider rejection, firewall rejection, RBAC, gating behavior, and audit logging.
- Frontend tests for toggles, analyst read-only state, missing config display, not-tested warnings, firewall exclusion, and secret safety.
- Existing integration status tests should continue passing.
