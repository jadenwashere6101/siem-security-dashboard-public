# Proposal: Linux Firewall Dry-Run Adapter

## Problem

The SOAR adapter interface is ready for real integrations, but the first
firewall-facing adapter must not jump straight to real blocking. A firewall
adapter is inherently dangerous: a bad rule can lock out administrators, disrupt
production traffic, or block the wrong target.

The project needs a first concrete adapter that exercises the real adapter
architecture while proving safety controls, configuration gates, registry
integration, result shape, and worker behavior without changing the host
firewall.

## Goal

Design a Linux firewall adapter for `block_ip` in dry-run mode only.

The adapter will validate the target IP and return a structured plan describing
the firewall command it would execute later. It must not run `ufw`, `iptables`,
`nft`, `subprocess`, shell commands, system calls, or network calls.

## Why Dry-Run First

Dry-run gives the project a safe bridge between simulation and real execution:

- validates the adapter interface with a concrete action
- tests registry/config wiring without host side effects
- proves safety rules before any `sudo` or firewall command exists
- lets worker queue/log behavior run end-to-end
- gives reviewers a stable command-plan format to inspect before real execution

The dry-run adapter is not a mock hidden in tests. It is a production-safe adapter
mode that can be enabled explicitly to show what the system would do.

## Scope

In scope:

- Linux firewall adapter design under `integrations/soar_adapters/`
- support for `block_ip` only
- dry-run plan generation only
- public-IP validation
- explicit configuration gate
- result format compatible with `AdapterBackedExecutor`
- tests proving no external action happens

Out of scope:

- no real blocking
- no `sudo`
- no `subprocess`
- no shell commands
- no firewall state changes
- no Azure/AWS/cloud adapters
- no frontend
- no playbooks/incidents
- no scheduler/systemd worker
- no distributed workers

## Success Criteria

- Adapter supports only `block_ip`.
- Adapter is disabled unless explicitly configured.
- Invalid, private, loopback, link-local, multicast, reserved, and missing IPs are
  rejected before a plan is produced.
- Public IPs return a dry-run result with `simulated=True` and clear dry-run
  language.
- The dry-run output includes the command plan but does not execute it.
- Tests prove no `subprocess`, shell, firewall, or network imports are used.
- The existing worker/executor contract remains unchanged.

