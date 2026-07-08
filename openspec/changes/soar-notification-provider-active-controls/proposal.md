## Why

The parent roadmap `soar-notification-integration-controls-roadmap` separates provider state into Configured, Tested, Active, Delivered, and Simulation. The current codebase can report adapter readiness and delivery attempts, but it has no durable "Active" control that lets a super-admin decide which notification providers playbooks are allowed to use.

This child spec defines the second implementation step in that roadmap: durable Active/Inactive controls for Slack, Teams, Email, and Webhook. It does not add manual test-send buttons, playbook enforcement, delivery history dashboards, or any new real delivery behavior.

## What Changes

- Define durable backend provider status for Slack, Teams, Email, and Webhook.
- Add database-backed Active/Inactive state, not localStorage.
- Plan backend APIs for reading provider control state and updating Active/Inactive state.
- Plan RBAC so only super-admins can toggle Active/Inactive state.
- Plan audit logging for activation/deactivation changes.
- Plan frontend Active/Inactive toggles on the SOAR Integrations page.
- Keep activation visibly tied to Configured and Tested state so a provider does not appear production-ready just because code exists.
- Exclude Firewall from Active controls and keep it simulation/dry-run only.

## Capabilities

### New Capabilities
- `soar-notification-provider-active-controls`: stores and displays durable provider Active/Inactive state for notification providers and exposes super-admin controls to update that state.

### Modified Capabilities
- Existing SOAR Integrations status UI and service will later include provider Active/Inactive controls, while preserving existing adapter readiness and circuit-breaker behavior.

## Impact

- **Affected backend:** new provider-control storage helper/module, migration, read/update routes under the existing integrations area, RBAC and audit logging for updates.
- **Affected frontend:** SOAR Integrations panel/service tests and UI controls for provider Active/Inactive state.
- **Affected database:** likely new table or equivalent durable storage for provider active state and tested-status metadata.
- **Affected playbook behavior:** none in this child spec. Playbook enforcement belongs to `soar-playbook-notification-enforcement`.
- **Affected external systems:** none. This spec must not configure or contact Slack, Teams, Email, Webhook, Firewall, VM, or Azure.
- **Parent roadmap:** this child belongs under `soar-notification-integration-controls-roadmap`; no parent-roadmap file changes are required by this spec.
