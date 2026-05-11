# Design: SOAR Protected Target Policy

## Current State

`block_ip` is approval-gated. A queue row requiring `block_ip` creates an approval request and pauses in `awaiting_approval` until approved, denied, or expired.

The Linux firewall adapter is dry-run only. It builds a command plan but does not shell out or mutate a firewall.

Current adapter validation blocks unsafe address classes such as private, loopback, reserved, multicast, and invalid IPs. This protects obvious unsafe targets but does not protect public IPs that belong to administrators, the current server, developers, home networks, or known-safe external services.

## Policy Model

Add a central helper module, proposed location:

```text
core/soar_protected_targets.py
```

The helper owns all protected-target parsing and matching. It should be pure and testable, with no Flask dependency.

Proposed public functions:

```python
class ProtectedTargetConfigError(ValueError):
    pass

def load_protected_targets(env=None):
    ...

def is_protected_target(ip_address, protected_networks=None):
    ...

def require_unprotected_target(ip_address, protected_networks=None):
    ...
```

`load_protected_targets()` reads `SOAR_PROTECTED_IPS`, parses comma-separated IP/CIDR entries with Python `ipaddress`, and returns normalized `ip_network` objects. Exact IP entries should be represented as `/32` for IPv4 or `/128` for IPv6.

`is_protected_target()` returns `True` when the candidate target IP falls inside any configured protected network.

`require_unprotected_target()` raises a classified skip-style error when the target is protected. The error should be suitable for worker/adapter paths to convert into a skipped outcome rather than a retryable or failed outcome.

## Configuration

Initial config:

```text
SOAR_PROTECTED_IPS=203.0.113.10,198.51.100.0/24
```

Supported entries:

- Exact IPv4 address, e.g. `203.0.113.10`
- Exact IPv6 address, e.g. `2001:db8::10`
- IPv4 CIDR, e.g. `198.51.100.0/24`
- IPv6 CIDR, e.g. `2001:db8:abcd::/48`

Whitespace around entries should be ignored. Empty entries from doubled commas should be ignored.

Invalid config should fail closed. If `SOAR_PROTECTED_IPS` contains an invalid IP or CIDR, protected-target loading should raise `ProtectedTargetConfigError`. Any `block_ip` path that cannot load the policy safely must skip execution with a clear message, not proceed as unprotected.

Rationale: a typo in a safety allowlist is safer as a visible skipped remediation than as an accidental block of a protected public IP.

## Integration Points

### Worker Approval Gate

The safest primary integration point is before approval creation for `block_ip`.

In the worker path, before `_handle_approval_gate()` creates or checks approval state for a `block_ip` queue row:

1. Validate the target with existing public-IP validation.
2. Load and evaluate protected-target policy.
3. If protected, mark the queue row `skipped`.
4. Do not create an approval request.
5. Do not invoke the executor or adapter.
6. Do not increment `retry_count`.

This satisfies the invariant that protected skips do not require approval.

### Executor / Adapter Path

The dry-run Linux firewall adapter should also enforce the same protected-target policy before returning a command plan. This is a defense-in-depth layer in case an adapter is invoked directly from tests, scripts, or future execution paths.

If a target is protected, the dry-run adapter should raise or return the same skip classification used by existing adapter validation. It must not produce a firewall command plan for protected targets.

### Non-Block Actions

The protected-target policy applies only to target-blocking actions, initially `block_ip`. Actions such as `monitor` and `flag_high_priority` should remain unchanged.

If future actions can block, quarantine, disable, or otherwise mutate a target, they should explicitly opt into the same policy before execution.

## Error and Result Semantics

Protected target match:

- Queue row outcome: `skipped`
- Error/message code: stable, e.g. `protected_target`
- Human-readable message: includes that the target is protected, but should not dump the full protected list.
- Retry count: unchanged
- Approval request: not created
- Adapter call: not executed

Invalid protected config:

- Queue row outcome: `skipped`
- Error/message code: stable, e.g. `protected_target_config_invalid`
- Retry count: unchanged
- Approval request: not created
- Adapter call: not executed

Non-protected public IP:

- Existing behavior continues.
- `block_ip` remains approval-gated.
- Dry-run adapter still returns a simulated command plan when invoked after approval.

## Test Strategy

Helper tests:

- Exact protected IP matches.
- Protected CIDR matches.
- Whitespace and empty entries are normalized safely.
- Invalid IP/CIDR config raises `ProtectedTargetConfigError`.
- Non-protected public IP returns allowed.

Worker tests:

- Protected `block_ip` queue row is skipped.
- No approval request is created.
- Executor/adapter mock is not called.
- `retry_count` is not incremented.
- Invalid protected config skips safely.
- Non-protected public `block_ip` still creates/uses approval as before.
- Non-block actions are unchanged.

Adapter tests:

- Dry-run firewall adapter rejects protected exact IP.
- Dry-run firewall adapter rejects protected CIDR member.
- Dry-run firewall adapter allows non-protected public IP and returns the existing dry-run command plan.

Regression tests:

- Existing private/loopback/reserved validation remains intact.
- Existing approval-gated behavior remains intact for non-protected public IPs.

## Safety Boundaries

- No real firewall execution.
- No playbook engine.
- No Slack/email notifications.
- No frontend changes unless implementation discovers unavoidable operator visibility needs.
- No worker daemon, scheduler, cron, systemd unit, or background thread.
- No ingest, detection, or correlation changes.
- No approval decision logic changes.

## Risks

Invalid config behavior must be strict and visible. Failing closed may temporarily skip legitimate blocks if the environment variable is malformed, but that is safer than accidentally treating protected targets as unprotected.

Configuration naming can expand later. `SOAR_PROTECTED_IPS` is sufficient for the first implementation, but future config may split categories such as admin IPs, server IPs, and business allowlists. The helper should keep the internal model generic enough to accept multiple sources later.

Protected-target checks must run before approval creation. If implemented only in the adapter, protected `block_ip` rows could still create unnecessary approvals, violating the goal that protected skips do not require approval.
