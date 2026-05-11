## Why

The SOAR response path already gates `block_ip` behind approval and the Linux firewall adapter is dry-run only, but the system still needs an explicit protected-target policy before any real blocking path exists. Current IP validation blocks private, loopback, reserved, and otherwise unsafe address classes; it does not protect public admin, server, developer, home, or allowlisted IPs that must never be blocked.

This change adds a safety layer now, while execution is still simulated, so protected-target behavior is tested and enforced before real firewall integration work begins.

## What Changes

- Add a central protected-target policy helper for SOAR remediation targets.
- Support protected IPs and CIDRs from configuration, starting with `SOAR_PROTECTED_IPS` as a comma-separated list of IP addresses and CIDR ranges.
- Treat configured admin IPs, server/current VM IPs, developer/home IPs, and known-safe CIDRs as protected targets.
- Integrate protected-target checks into the `block_ip` path at the safest point before approval creation and adapter execution.
- Make protected `block_ip` actions skip safely without requiring approval and without calling any adapter.
- Make the dry-run firewall adapter independently respect protected-target policy.
- Add tests for exact IP matches, CIDR matches, invalid config handling, non-protected public IPs, worker skip behavior, dry-run adapter rejection, and unchanged non-block actions.

No real firewall execution, playbook engine, Slack/email integration, frontend work, daemon, scheduler, ingest changes, detection changes, or correlation changes are included.

## Capabilities

### New Capabilities

- `soar-protected-target-policy`: Defines how SOAR identifies remediation targets that must never be blocked and how protected matches affect approval and execution behavior.

### Modified Capabilities

- None.

## Impact

- Backend SOAR execution safety: `block_ip` approval and execution flow must consult the protected-target policy before creating approvals or invoking adapters.
- Adapter safety: the Linux firewall dry-run adapter must reject protected targets even though it does not execute firewall commands.
- Configuration: add documented environment/config support for `SOAR_PROTECTED_IPS` as comma-separated IP/CIDR entries.
- Tests: add focused backend tests for helper parsing/matching, worker behavior, dry-run adapter behavior, and non-block action regression coverage.
