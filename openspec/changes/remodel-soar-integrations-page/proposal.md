## Why

The current SOAR Integrations page exposes backend implementation details before it answers operational questions. Analysts and reviewers see terms like circuit breaker state, half-open probe, force open, retry eligible, cooldown, and simulation controls before they can tell whether Slack, Teams, Email, Firewall, or Webhook is real, configured, used, or safe to send external traffic.

The backend registry and adapter model already provide most of the needed status data. The problem is the frontend presentation. This change remodels the page around operational status first and keeps engineering internals available behind an Advanced disclosure.

## What Changes

- Remodel the SOAR Integrations page into status-first integration cards.
- Keep the existing dark SOC dashboard visual language.
- Show operational fields first for each integration:
  - Current Mode: Simulation, Real, or Disabled.
  - Health: Healthy, Warning, or Error.
  - Used By: count of core/default playbooks, or "Not used by default".
  - External Delivery: Enabled or Disabled.
  - Ready for Real Mode: Yes or No.
  - Missing env variable names when real mode is not ready.
  - Last successful delivery when already available from existing frontend/backend data.
  - Last tested when already available; otherwise clearly show Not tested / Not available.
  - Supported actions.
  - Short explanation of what the integration does.
- Move circuit breaker state, thresholds, cooldowns, retry eligibility, half-open probes, manual controls, and other internal adapter data into a collapsible Advanced section.
- Rename or supplement implementation-heavy labels with operational language, while preserving exact backend semantics.
- Preserve existing backend behavior, adapter behavior, auth/RBAC behavior, routes, env guards, and real/simulation safety boundaries.

## Capabilities

### New Capabilities
- `soar-integrations-operational-status-ui`: presents SOAR integrations in an operational status-first UI while retaining advanced engineering details behind a collapsed section.

### Modified Capabilities
- Existing SOAR integration status frontend behavior is reorganized for clarity without changing backend integration execution behavior.

## Impact

- **Affected frontend:** `frontend/src/components/IntegrationStatusPanel.js`, `frontend/src/components/IntegrationStatusPanel.test.js`, and possibly small presentational helpers if extracted.
- **Affected backend:** none for this v1 remodel.
- **Affected database/migrations:** none.
- **Affected integrations:** none; this change must not send notifications, execute webhooks, send email, call Teams/Slack, or mutate firewall state.
- **Affected tests:** frontend component/service tests only, plus existing backend tests should continue to pass if run.
- **Future backend work:** durable last-tested state, richer last-delivery summaries, and backend-supplied playbook usage counts can be specified separately if existing data is insufficient.
