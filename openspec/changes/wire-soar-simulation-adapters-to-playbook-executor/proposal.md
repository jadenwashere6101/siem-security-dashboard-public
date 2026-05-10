# Proposal: Wire SOAR Simulation Adapters To Playbook Executor

## Problem

The playbook step executor can simulate generic playbook steps and approval gates, and the
simulation-only integration adapter foundation now exists. However, playbook execution does
not yet route integration-shaped steps through the adapter registry.

This means actions such as Slack notification, email notification, firewall blocking, and
webhook notification cannot exercise the adapter boundary in simulation. Without this wiring,
future real-mode work has no proven executor-to-adapter contract.

## Goal

Wire supported playbook step actions to the simulation adapter registry so the executor can
simulate integration behavior through the same boundary that future real integrations will
use, while still performing no real execution.

## Scope

- Map playbook step actions to simulation adapters:
  - `notify_slack` -> `slack`
  - `notify_email` -> `email`
  - `block_ip` -> `firewall`
  - `notify_webhook` -> `webhook`
- Spec executor behavior for calling the adapter registry in simulation mode only.
- Include adapter output in `steps_log`.
- Preserve existing approval gate behavior.
- Add tests proving adapter-backed steps are simulated, real mode fails closed, no network
  calls occur, and no firewall/blocklist/SOAR queue mutation occurs.

## Out of Scope

- No implementation code in this change.
- No real Slack, email, webhook, or firewall calls.
- No real mode implementation.
- No secrets or credential handling.
- No daemon, systemd worker, scheduler, or background process.
- No SOAR queue changes.
- No frontend changes unless existing execution detail rendering already displays the
  adapter output.
- No schema changes.
- No ingest, detection, or correlation changes.
- No approval behavior changes.

## Success Criteria

- Supported integration-shaped playbook steps are simulated through the adapter registry.
- `steps_log` entries clearly include adapter result details with `simulated: true` and
  `executed: false`.
- Unknown or unsupported adapter actions fail safely as simulated failures.
- Real mode remains disabled and fails closed.
- Tests prove no network calls, no real provider clients, no firewall/blocklist mutation, no
  SOAR queue mutation, and no approval gate regression.
