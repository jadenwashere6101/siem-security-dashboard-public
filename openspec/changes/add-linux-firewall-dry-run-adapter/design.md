# Design: Linux Firewall Dry-Run Adapter

---

## 1. Problem

Firewall actions have a much higher blast radius than simulated SOAR actions.
Even a single malformed or overly broad rule can interrupt service or lock out
operators. The first firewall adapter must therefore prove adapter wiring,
configuration, validation, and audit behavior without touching host firewall
state.

The dry-run Linux firewall adapter is the first concrete adapter that plugs into
the SOAR adapter interface. It supports `block_ip` only and returns the command
plan it would run in a later real-execution phase.

---

## 2. Goal

Design a Linux firewall adapter that:

- implements the existing SOAR adapter interface
- supports `block_ip`
- is dry-run only
- validates IP safety before producing a plan
- integrates through the adapter registry and `AdapterBackedExecutor`
- returns worker-compatible `{code, message, details}` results
- never executes firewall commands or system calls

---

## 3. Why Dry-Run First

Dry-run mode is the safe proving ground for firewall automation.

It confirms:

- adapter package placement
- action selection via registry/config
- result shape expected by the worker
- safety validation behavior
- future command-plan shape
- tests that prevent accidental side effects

It avoids:

- needing `sudo`
- mutating `ufw`, `iptables`, or `nftables`
- depending on distro-specific firewall tooling
- requiring rollback/unblock logic before the architecture is stable

---

## 4. Architecture Placement

Recommended file:

```text
integrations/
  soar_adapters/
    linux_firewall.py
```

Related existing/foundation files:

```text
integrations/soar_adapters/base.py       # BaseSoarActionAdapter
integrations/soar_adapters/registry.py   # adapter selection
integrations/soar_adapters/config.py     # env/config parsing
engines/soar_executor.py                 # AdapterBackedExecutor
engines/soar_action_worker.py            # unchanged worker
```

The adapter must not live in:

- `engines/soar_action_worker.py`
- `core/`
- `routes/`
- frontend code

The worker stays vendor-agnostic. It calls an executor. The executor selects the
adapter. The adapter returns a result or raises a SOAR exception.

---

## 5. Adapter Contract

Class name:

```python
class LinuxFirewallDryRunAdapter(BaseSoarActionAdapter):
    adapter_name = "linux_firewall_dry_run"
    supported_actions = {"block_ip"}
```

Public method:

```python
def execute(self, row: dict, context: dict | None = None) -> dict:
    ...
```

Input:

- `row["action"]` must be `block_ip`
- `row["source_ip"]` must be a safe public IP
- `row["alert_id"]` may be `None`
- `row["id"]` is used as queue context in details

Output:

```python
{
    "code": "linux_firewall_dry_run_plan",
    "message": "DRY RUN: would block 203.0.113.10 using ufw",
    "details": {
        "adapter": "linux_firewall_dry_run",
        "action": "block_ip",
        "source_ip": "203.0.113.10",
        "alert_id": 42,
        "queue_id": 123,
        "simulated": True,
        "dry_run": True,
        "firewall_tool": "ufw",
        "command_plan": ["ufw", "deny", "from", "203.0.113.10"],
        "executed": False,
    },
}
```

The command plan is data only. It must not be passed to a process runner in this
phase.

---

## 6. Adapter Behavior

### Supported action

Only `block_ip` is supported.

If the row action is anything else, raise:

```python
SkippedAction("Linux firewall dry-run adapter only supports block_ip", code="unsupported_action")
```

### IP validation

The adapter parses `source_ip` using Python `ipaddress.ip_address()`.

Reject with `SkippedAction` when:

- `source_ip` is missing or `None`
- IP parsing fails
- IP is private
- IP is loopback
- IP is link-local
- IP is multicast
- IP is reserved
- IP is unspecified

Only public unicast IPs can produce a dry-run plan.

### Plan generation

The adapter should support a configured firewall tool value, but only as plan
text. Initial allowed values:

- `ufw`
- `iptables`
- `nft`

Default:

- `ufw`

Example plans:

```python
["ufw", "deny", "from", "203.0.113.10"]
["iptables", "-A", "INPUT", "-s", "203.0.113.10", "-j", "DROP"]
["nft", "add", "rule", "inet", "filter", "input", "ip", "saddr", "203.0.113.10", "drop"]
```

These arrays are not executable in this phase. They are returned for review,
audit, and future implementation planning only.

---

## 7. Configuration Requirements

The adapter is disabled unless explicitly configured.

Recommended config:

| Setting | Required | Example | Purpose |
|---|---:|---|---|
| `SOAR_EXECUTION_MODE` | yes | `real` | Adapter-backed execution must be explicit |
| `SOAR_ADAPTER_BLOCK_IP` | yes | `linux_firewall_dry_run` | Selects this adapter |
| `SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED` | yes | `true` | Enables dry-run adapter |
| `SOAR_LINUX_FIREWALL_TOOL` | no | `ufw` | Plan style: `ufw`, `iptables`, or `nft` |

If not enabled, adapter construction or execution should fail closed with
`SkippedAction` or a registry configuration error. It must never silently run.

Dry-run adapter configuration must not include credentials or privilege settings.
Those belong to a later real-execution phase.

---

## 8. Safety Rules

Mandatory safety controls:

- reject all non-public IPs
- reject invalid IP strings
- reject unsupported actions
- require explicit dry-run enablement
- return `simulated=True`
- return `dry_run=True`
- return `executed=False`
- include "DRY RUN" in the message
- never import or call `subprocess`, `os.system`, `shlex`, `requests`, socket
  clients, cloud SDKs, or firewall libraries
- never require `sudo`
- never inspect host firewall state

The adapter should fail closed: when uncertain, skip or fail rather than produce
a plan.

---

## 9. Failure Classification

Use existing SOAR errors.

### SkippedAction

Use for:

- adapter disabled
- unsupported action
- missing source IP
- invalid IP
- private/loopback/link-local/multicast/reserved/unspecified IP
- unsupported firewall tool value

These are not retryable because retrying does not change input/config safety.

### RetryableActionError

Dry-run should rarely raise retryable errors because it performs no external I/O.
Only use retryable classification for transient config-source access if future
config loading depends on an external provider. With env-only config, no retryable
failure is expected.

### Terminal failure

Use a terminal exception only for programmer/configuration defects that indicate
the adapter cannot operate safely, such as malformed internal plan generation.

---

## 10. Logging Expectations

Use `logging.getLogger(__name__)`.

Log:

- INFO when a dry-run plan is created
- WARNING when a safety rule skips execution

Include non-sensitive fields:

- queue ID
- alert ID
- source IP
- adapter name
- firewall tool
- dry-run flag

Do not log:

- shell strings intended for execution
- credentials
- environment dumps
- host firewall state

Worker audit logging remains unchanged. The adapter returns details; the worker
continues to write `response_actions_log`.

---

## 11. Test Strategy

No test may execute a real command.

### Unit tests

Cover:

- adapter disabled by default
- enabled adapter supports `block_ip`
- valid public IPv4 returns dry-run plan
- valid public IPv6 returns dry-run plan if IPv6 support is included
- invalid IP raises `SkippedAction`
- missing IP raises `SkippedAction`
- private IP raises `SkippedAction`
- loopback IP raises `SkippedAction`
- link-local IP raises `SkippedAction`
- multicast IP raises `SkippedAction`
- reserved IP raises `SkippedAction`
- unsupported action raises `SkippedAction`
- unsupported firewall tool raises `SkippedAction`

### Result shape tests

Assert:

- `code == "linux_firewall_dry_run_plan"`
- `message` contains `"DRY RUN"`
- `details["simulated"] is True`
- `details["dry_run"] is True`
- `details["executed"] is False`
- `details["command_plan"]` is a list of args, not a shell string
- no secrets or environment dumps are present

### Registry/executor tests

Assert:

- adapter can be registered for `block_ip`
- `AdapterBackedExecutor` can invoke it
- worker marks the queue row `success` for a valid public IP dry-run
- worker marks the queue row `skipped` for unsafe IPs
- worker writes existing audit log rows through current worker logging

### No external action tests

Assert source code for `linux_firewall.py` does not import or reference:

- `subprocess`
- `os.system`
- `pty`
- `shlex` for shell construction
- `requests`
- `socket`
- `boto3`
- Azure SDK modules

Where possible, monkeypatch common command runners to fail if called and prove
they are never invoked.

---

## 12. Future Real-Execution Phase

A later real-execution Linux firewall adapter must be a separate change.

It must define:

- exact supported firewall backend (`ufw`, `iptables`, or `nft`) instead of all
  at once
- privilege model
- staging/VM-only rollout plan
- lockout prevention
- allowlist/denylist policy
- idempotency check against existing firewall state
- unblock/rollback strategy
- command timeout behavior
- stderr/stdout redaction
- rate limits
- operational runbook

The real phase should start with one backend, preferably `ufw`, on a disposable
VM. It must not be implemented as an expansion of dry-run without a new spec.

---

## 13. Stop Conditions

Stop implementation and re-plan if:

- any implementation needs `subprocess`, shell execution, `sudo`, or system calls
- tests require a Linux firewall to be installed
- tests require elevated privileges
- the adapter needs to inspect or mutate real firewall state
- adapter config requires secrets
- registry integration requires changing worker public contracts
- queue schema changes appear necessary
- a real cloud/SaaS adapter becomes part of the patch

