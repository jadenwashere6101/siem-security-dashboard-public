# Proposal: SOAR Integration Adapter Simulation Foundation

## Problem

SOAR playbook definitions, trigger matching, execution records, simulation execution,
approval gates, and execution controls now exist. The system can safely model playbook
execution, but it has no integration adapter boundary for actions that will eventually
target Slack, email, firewalls, or webhooks.

Without an adapter foundation, later work risks coupling playbook steps directly to real
network clients or remediation code. Phase 3 needs the adapter shape first, with simulation
as the default and only implemented mode, before any real execution is considered.

## Goal

Add a spec for a simulation-only integration adapter foundation that defines common adapter
interfaces, registry behavior, result formats, and safety rules. The foundation must allow
future playbook executor wiring to call adapters through a controlled boundary, while this
change itself performs no real integration work.

## Scope

- Add `integrations/base_integration.py` defining the common adapter contract.
- Add `integrations/integration_registry.py` for resolving adapters by integration name.
- Add simulation-only adapters for:
  - `slack`
  - `email`
  - `firewall`
  - `webhook` if it can be implemented without network behavior.
- Define `INTEGRATION_MODE`, defaulting to `simulation`.
- Define a stable `execute()` result shape for simulated adapter calls.
- Add tests proving simulation mode does not require secrets, instantiate real clients, make
  network calls, mutate firewall/blocklist state, enqueue SOAR queue items, or change
  playbook executor behavior.

## Out of Scope

- No implementation code in this change.
- No real Slack webhook calls.
- No SMTP, SendGrid, or email provider calls.
- No real firewall or blocklist mutation.
- No PagerDuty integration.
- No daemon, systemd worker, scheduler, cron, or background thread.
- No frontend changes.
- No schema changes unless a later approved implementation proves a tiny additive change is
  required.
- No ingest, detection, or correlation changes.
- No SOAR queue behavior changes.
- No playbook executor wiring to adapters yet; that must be a later explicit spec.

## Success Criteria

- The design clearly defines a simulation-only adapter interface and registry.
- `INTEGRATION_MODE` defaults to `simulation`.
- Simulation adapters return structured results with `simulated: true` and
  `executed: false`.
- Tests are planned to prove no network calls, no secrets, no real client construction, no
  blocklist/firewall mutation, and no SOAR queue mutation.
- The spec leaves future real mode documented as out of scope.
