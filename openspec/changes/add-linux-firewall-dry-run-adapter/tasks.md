# Tasks: Linux Firewall Dry-Run Adapter

This change is dry-run only. Do not add real command execution.

---

## Completion Checklist

- [x] Task 1 — Confirm adapter foundation
- [x] Task 2 — Add dry-run adapter module
- [x] Task 3 — Implement configuration gate
- [x] Task 4 — Implement IP safety validation
- [x] Task 5 — Generate dry-run command plan
- [x] Task 6 — Register adapter
- [x] Task 7 — Unit tests
- [x] Task 8 — Integration tests
- [x] Task 9 — No external action guard tests

## Task 1 — Confirm adapter foundation

Inspect:

- `integrations/soar_adapters/base.py`
- `integrations/soar_adapters/registry.py`
- `integrations/soar_adapters/config.py`
- `engines/soar_executor.py`

Confirm:

- adapters can implement `execute(row, context=None)`
- registry can select an adapter for `block_ip`
- `AdapterBackedExecutor` can call an adapter without worker changes

Stop if the foundation is missing or incompatible; fix the foundation in its own
change rather than mixing it into this adapter.

---

## Task 2 — Add dry-run adapter module

Create:

```text
integrations/soar_adapters/linux_firewall.py
```

Define:

```python
class LinuxFirewallDryRunAdapter(BaseSoarActionAdapter):
    adapter_name = "linux_firewall_dry_run"
    supported_actions = {"block_ip"}
```

No imports of:

- `subprocess`
- `os.system`
- `pty`
- `requests`
- `socket`
- cloud SDKs

---

## Task 3 — Implement configuration gate

Adapter must be disabled unless explicitly configured.

Use config values equivalent to:

- `SOAR_LINUX_FIREWALL_DRY_RUN_ENABLED=true`
- `SOAR_LINUX_FIREWALL_TOOL=ufw|iptables|nft`

If disabled, raise `SkippedAction` before producing a plan.

Do not add credentials or privilege config.

---

## Task 4 — Implement IP safety validation

For `source_ip`, reject:

- missing/null
- invalid format
- private
- loopback
- link-local
- multicast
- reserved
- unspecified

Raise `SkippedAction` for all validation failures.

Only public IPs may proceed to plan generation.

---

## Task 5 — Generate dry-run command plan

For valid public IPs, return a result dict:

- `code="linux_firewall_dry_run_plan"`
- message includes `"DRY RUN"`
- details include:
  - adapter name
  - action
  - source IP
  - alert ID if present
  - queue ID
  - firewall tool
  - command plan list
  - `simulated=True`
  - `dry_run=True`
  - `executed=False`

Do not execute the plan.

---

## Task 6 — Register adapter

Register the adapter with the SOAR adapter registry for `block_ip` only when
explicitly configured.

Default behavior must remain simulation.

Do not change worker public interfaces.

---

## Task 7 — Unit tests

Add tests for:

- disabled adapter skips/fails closed
- public IP returns dry-run plan
- unsupported action skips
- missing IP skips
- invalid IP skips
- private IP skips
- loopback IP skips
- link-local IP skips
- multicast IP skips
- reserved IP skips
- unsupported firewall tool skips

---

## Task 8 — Integration tests

Add tests proving:

- registry selects the dry-run adapter for `block_ip`
- `AdapterBackedExecutor` invokes the dry-run adapter
- worker processes a valid dry-run `block_ip` action as success
- worker processes unsafe IP dry-run action as skipped
- worker audit logging still records terminal outcome

---

## Task 9 — No external action guard tests

Add tests proving:

- `linux_firewall.py` does not import `subprocess`
- no `os.system` usage
- no network/client imports
- no shell command string execution path
- no test requires Linux firewall tools installed
- no test requires elevated privileges

---

## Verification

Run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/*.py integrations/soar_adapters/*.py
```

Run:

```bash
python3 -m pytest tests/ -x --tb=short -v
```

No frontend build is required unless frontend files are touched, which they
should not be.

---

## Explicit Non-Tasks

Do not:

- run `ufw`
- run `iptables`
- run `nft`
- import or call `subprocess`
- call `sudo`
- execute shell commands
- inspect firewall state
- mutate firewall state
- add Azure/AWS/cloud adapters
- touch frontend
- add playbooks/incidents
- change scheduler/systemd worker behavior
- change queue schema
- change detection/correlation/ingest flow

