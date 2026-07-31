## Why

The scheduled SOC briefing runtime assumes the Azure VM is available often enough for autonomous schedules, but this deployment is intentionally powered on only when needed to control cost. Analysts need a manual-first briefing workflow that still uses the existing read-only investigation and history stack without requiring 24/7 scheduling.

## What Changes

- Add a SOC briefing control surface with two modes: `manual_only` and `scheduled_autonomous`.
- Add a "Run Anakin Briefing Now" path that creates one bounded briefing job and keeps manual runs available in either mode.
- Add schedule pause/resume state so automatic enqueueing can be stopped without blocking manual runs.
- Surface last successful run, next scheduled run, catch-up policy/status, local model readiness, and local-only/no-paid-fallback status.
- Persist manually generated briefings into the existing briefing history and mark their trigger as manual in safe metadata.
- Preserve the existing scheduler, worker, job, run, briefing history, AI Gateway, RBAC, audit, and read-only advisory boundaries.
- Do not add automatic production actions, paid fallback, provider reconfiguration, or duplicate scheduler/runtime architecture.

## Capabilities

### New Capabilities
- `manual-soc-briefing-mode`: Manual-first SOC briefing controls, status, pause, and run-now behavior using the existing briefing runtime.

### Modified Capabilities

## Impact

- Backend: SOC briefing routes, runtime store, worker materialization behavior, and focused tests.
- Frontend: SOC Briefings service, panel controls/status, and component tests.
- Database: additive persistence only if existing runtime tables cannot safely represent global briefing mode and pause state.
- Runtime/deployment: source-only Mac change; VM runtime config, provider settings, schedules, and services are not changed by this implementation.
