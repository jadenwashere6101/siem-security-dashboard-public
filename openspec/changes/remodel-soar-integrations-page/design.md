## Overview

`remodel-soar-integrations-page` is a frontend-first redesign of the SOAR Integrations page. It keeps backend integration behavior unchanged and converts the current adapter registry view into an operational status view that an analyst can understand quickly.

The first screen should answer: what is real, what is simulated, what is configured, what is used, and what is safe. Engineering internals remain available, but they should not dominate the default card.

## Existing Context

- The current page is implemented by `frontend/src/components/IntegrationStatusPanel.js`.
- It fetches `/integrations/status` through `frontend/src/services/integrationService.js`.
- The backend status endpoint returns adapters from `integrations/integration_registry.py`.
- Registered adapters are `slack`, `teams`, `email`, `firewall`, and `webhook`.
- Slack, Teams, Email, and Webhook are real-capable only when their env guards pass.
- Firewall is explicitly dry-run/simulation-only in the integration status registry.
- Super-admin circuit breaker controls are currently shown per adapter and mutate only in-memory simulation state.
- Existing tests already cover the frontend panel and backend route/adapter readiness behavior.

## Scope Decision

This should be one implementation spec because the requested work is a coherent frontend remodel of one page/component. Splitting into multiple specs would create unnecessary coordination overhead while still touching the same component and tests.

Future backend-backed telemetry such as durable last-tested records or richer adapter usage metadata should be separate specs because those would change contracts, persistence, and possibly worker behavior.

## Data Mapping

The implementation should derive v1 operational fields from existing status data where possible:

- `Current Mode`
  - `Real` when adapter/status indicates real mode is ready and active.
  - `Simulation` when adapter/status is simulated or real mode is not ready.
  - `Disabled` only when existing data clearly indicates disabled/unavailable, otherwise prefer Simulation with a warning.
- `Health`
  - `Healthy` for simulation-ready adapters and real-ready adapters with no blocking state.
  - `Warning` when real mode is requested but missing configuration, adapter is unused by default, or external delivery is disabled.
  - `Error` when existing status/error data indicates the page could not load, adapter is blocked, or circuit/internal state indicates a blocking failure.
- `Used By`
  - For v1, use a frontend-owned static mapping for known core/default playbook usage based on the current core playbook pack audit.
  - Slack: used by default core playbooks.
  - Email: used by at least one default core playbook.
  - Firewall: used by default containment playbooks.
  - Teams and Webhook: not used by default unless future data proves otherwise.
  - If static mapping cannot be kept accurate, the UI should label it as default/core usage and defer dynamic backend usage counts.
- `External Delivery`
  - Enabled only when adapter real/external execution is ready according to existing status booleans.
  - Disabled for simulation, missing config, and firewall dry-run.
- `Ready for Real Mode`
  - Yes when existing adapter readiness indicates `real_mode_ready === true`.
  - No otherwise.
- `Missing`
  - Show env variable names only.
  - Never show env values, webhook URLs, tokens, passwords, SMTP host values, usernames, or secrets.
  - If the current status payload does not include all missing env names for an adapter, show only safe known required env names inferred from existing adapter rules and mark future richer backend status as deferred.
- `Last successful delivery`
  - Show only if existing data is already available to the component or a safe existing endpoint is already used.
  - If not available without backend changes, show `Not available` and defer durable delivery summary to future backend work.
- `Last tested`
  - Show `Not tested` or `Not available` unless an existing safe value is available.
  - Do not create test actions in this spec.

## UI Structure

The top of the page should contain a short summary, not a long explanation. The page should then render one card per adapter.

Each card should have:

- Adapter name and a concise description.
- Mode badge.
- Health badge.
- Compact status grid with Current Mode, Used By, External Delivery, Ready for Real Mode, Last Delivery, and Last Tested.
- Missing configuration section only when required.
- Supported actions displayed as compact tags.
- Advanced disclosure collapsed by default.

The Advanced section should contain:

- Circuit breaker state and raw state details.
- Failure threshold.
- Consecutive failures.
- Retry eligibility.
- Timeout.
- Cooldown.
- Half-open probe availability.
- Last manual action fields.
- Current super-admin simulation controls.
- Any internal adapter fields that are useful for debugging but not operationally primary.

## Terminology

The UI should prefer operational wording:

- `Real Integration Disabled` becomes `Simulation Mode` or `External Delivery Disabled`.
- `closed` becomes `Healthy` in the primary view while remaining visible as raw `closed` in Advanced.
- `Reset to closed` becomes `Restore Healthy State`.
- `Force open` becomes `Simulate Failure`.
- `Enable half-open probe` becomes `Simulate Recovery`.
- `Circuit breaker` becomes `Advanced reliability controls` or remains inside Advanced.

Implementation may keep raw backend labels inside Advanced where precision matters.

## Backend Boundary

No backend endpoint, schema, migration, adapter execution behavior, RBAC behavior, or environment guard behavior changes are in scope.

The remodel must not:

- Send Slack, Teams, Email, or Webhook traffic.
- Add test-connection buttons.
- Add notification delivery integration.
- Enable real firewall execution.
- Touch Azure, VM deployment, ingestion, detections, or SOAR runtime workers.

## Future Backend Enhancements

If desired later, create separate specs for:

- Dynamic backend-provided playbook usage counts per adapter/action.
- Durable last-tested records and safe test-action APIs.
- Last successful delivery summaries per adapter from notification delivery records.
- Adapter health probes that do not leak secrets.
- Real firewall execution, if ever approved.

## Validation

Implementation should validate through:

- Frontend component tests for status-first fields, missing env display, advanced collapsed/default behavior, and renamed controls.
- Existing integration service tests.
- Existing backend integration tests should continue passing because backend contracts are unchanged.
- `openspec validate remodel-soar-integrations-page --strict`.
- `git diff --check`.
