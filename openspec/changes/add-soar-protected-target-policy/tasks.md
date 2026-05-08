# Tasks: SOAR Protected Target Policy

Read the relevant files before editing:

- `engines/soar_action_worker.py`
- `engines/soar_executor.py`
- `integrations/soar_adapters/base.py`
- `integrations/soar_adapters/linux_firewall.py`
- `integrations/soar_adapters/config.py`
- `core/approval_store.py`
- `core/response_action_queue_store.py`
- existing SOAR worker and adapter tests

Do not touch ingest, detection, correlation, frontend, scheduler, daemon, or real execution code.

## Step 1: Add Central Protected-Target Policy Helper

- [ ] Create `core/soar_protected_targets.py`.
- [ ] Add `ProtectedTargetConfigError`.
- [ ] Add a skip/error class or reuse an existing skip classification in a way that produces a skipped outcome, not retry/failure.
- [ ] Implement `load_protected_targets(env=None)` reading `SOAR_PROTECTED_IPS`.
- [ ] Parse comma-separated exact IPs and CIDRs with `ipaddress`.
- [ ] Normalize exact IPs to `/32` or `/128` networks.
- [ ] Ignore blank entries caused by whitespace or doubled commas.
- [ ] Fail closed on invalid entries by raising `ProtectedTargetConfigError`.
- [ ] Implement `is_protected_target(ip_address, protected_networks=None)`.
- [ ] Implement `require_unprotected_target(ip_address, protected_networks=None)`.

Verification:

- [ ] Add tests for exact protected IP matching.
- [ ] Add tests for protected CIDR matching.
- [ ] Add tests for whitespace and blank-entry normalization.
- [ ] Add tests for invalid config handling.
- [ ] Add tests for non-protected public IP allowed.
- [ ] Run focused helper tests.

## Step 2: Integrate Policy Before `block_ip` Approval Creation

- [ ] Locate the worker approval gate for `block_ip` in `engines/soar_action_worker.py`.
- [ ] Add protected-target check before creating an approval request.
- [ ] If the target is protected, transition the queue row to `skipped`.
- [ ] Use a stable skip code/message such as `protected_target`.
- [ ] If protected config is invalid, transition the queue row to `skipped`.
- [ ] Use a stable skip code/message such as `protected_target_config_invalid`.
- [ ] Ensure protected skip does not call the executor.
- [ ] Ensure protected skip does not create an approval request.
- [ ] Ensure protected skip does not increment `retry_count`.
- [ ] Keep non-protected public `block_ip` behavior approval-gated.
- [ ] Keep non-block actions unchanged.

Verification:

- [ ] Test protected exact IP in worker path skips safely.
- [ ] Test protected CIDR member in worker path skips safely.
- [ ] Test invalid protected config in worker path skips safely.
- [ ] Test protected skip creates no approval request.
- [ ] Test protected skip does not call executor/adapter.
- [ ] Test protected skip does not increment `retry_count`.
- [ ] Test non-protected public `block_ip` still creates approval.
- [ ] Test non-block action behavior is unchanged.

## Step 3: Integrate Policy Into Dry-Run Firewall Adapter

- [ ] Read `integrations/soar_adapters/linux_firewall.py` and current adapter validation tests.
- [ ] Add protected-target check before command-plan construction.
- [ ] If target is protected, reject with skipped classification.
- [ ] If protected config is invalid, reject with skipped classification.
- [ ] Do not produce a command plan for protected targets.
- [ ] Preserve existing public IP dry-run behavior for non-protected targets.
- [ ] Preserve existing private/loopback/reserved validation behavior.

Verification:

- [ ] Test dry-run adapter rejects protected exact IP.
- [ ] Test dry-run adapter rejects protected CIDR member.
- [ ] Test dry-run adapter rejects invalid protected config safely.
- [ ] Test dry-run adapter allows non-protected public IP.
- [ ] Test dry-run adapter still rejects private/loopback/reserved IPs.

## Step 4: Configuration Documentation

- [ ] Document `SOAR_PROTECTED_IPS` in the appropriate environment/config documentation if such a file exists.
- [ ] Include examples for exact IP and CIDR entries.
- [ ] Document fail-closed invalid config behavior.
- [ ] Do not add secrets or real personal IP addresses to committed examples.

## Step 5: Regression and Safety Audit

- [ ] Run targeted SOAR worker tests.
- [ ] Run targeted adapter tests.
- [ ] Run approval store/routes tests if approval-gate behavior changed.
- [ ] Run full backend test suite.
- [ ] Confirm no frontend files were modified unless explicitly required.
- [ ] Confirm no real firewall execution was added.
- [ ] Confirm no scheduler, daemon, cron, systemd unit, or background thread was added.
- [ ] Confirm ingest, detection, and correlation files were not modified.
- [ ] Confirm approval decision logic was not modified.
- [ ] Confirm protected `block_ip` skips do not create approval requests.
- [ ] Confirm protected `block_ip` skips do not execute adapters.
- [ ] Confirm protected `block_ip` skips do not increment `retry_count`.

## Suggested Verification Commands

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py
python3 -m pytest tests/test_response_action_queue.py tests/test_soar_adapter_interface.py -x --tb=short -v
python3 -m pytest tests/ -x --tb=short -v
git status --short
```
