## Why

The SOAR Integrations page currently mixes several unrelated concepts in one view: per-adapter real-mode readiness (`INTEGRATION_MODE`/`SOAR_ENV`/`SOAR_REAL_<PROVIDER>_ENABLED`/credential guards), an in-memory, per-process, simulated circuit breaker (`_SimulatedCircuitBreakerState` in `integrations/base_integration.py`, not DB-persisted), and general integration status — all surfaced through one combined `/integrations/status` response and one panel (`frontend/src/components/IntegrationStatusPanel.js`). None of this distinguishes "the adapter code exists and is guard-ready" from "a human has actually confirmed delivery works." The only provider with a confirmed real delivery is Slack (one prior manual test notification received). Teams was attempted and did not work. Email and Webhook have never been proven. Nothing in the current system prevents a playbook from being treated as production-ready for a provider that has never actually delivered anything.

This roadmap plans a professional Integration Delivery Controls system that makes that distinction explicit — Configured, Tested, Active, Last delivery — before any further notification work is implemented, and keeps Firewall permanently simulation/dry-run only.

## What Changes

- Add a coordination-only parent roadmap for `soar-notification-integration-controls-roadmap`.
- Record an accurate, code-verified audit of current notification/firewall adapter capability (see `design.md`).
- Define the terminology that all future child specs must use consistently: Configured, Tested, Active, Delivered, Simulation.
- Track the future child specs:
  - `soar-notification-readiness-test-buttons`
  - `soar-notification-provider-active-controls`
  - `soar-playbook-notification-enforcement`
  - `soar-notification-delivery-history`
- Record scope boundaries: no real external notifications from this roadmap, no firewall real-execution path ever introduced by this initiative, no VM/Azure work, no secrets exposed, no credentials configured, no child specs created yet.
- Record findings about what backend/database work is likely required per child spec, and what the current UI can already show without backend changes.
- Do not implement code, create child specs, modify application source files, modify tests, touch the VM, commit, or push.

## Capabilities

### New Capabilities
- `soar-notification-integration-controls-roadmap`: tracks the parent coordination plan, current-adapter-reality audit, terminology, child-spec sequencing, database/migration findings, current-UI findings, and risks/unknowns for the SOAR notification Integration Delivery Controls initiative.

### Modified Capabilities
(none — this parent roadmap does not change existing runtime behavior)

## Impact

- **Affected code:** none. This change must not touch application source files under `integrations/`, `engines/`, `routes/`, `core/`, `frontend/`, `migrations/`, or tests.
- **Affected artifacts:** adds `openspec/changes/soar-notification-integration-controls-roadmap/`.
- **Runtime behavior:** none. No notification adapter, playbook executor, or Integrations UI behavior changes as a result of this roadmap.
- **External systems:** none contacted. No Slack, Teams, Email, Webhook, or firewall call of any kind is made by creating this roadmap.
- **Downstream work:** four child implementation specs will be created later and will own implementation details, testing, migrations, and UI changes.
