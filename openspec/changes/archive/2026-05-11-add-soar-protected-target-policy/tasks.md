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

- [x] Create `core/soar_protected_targets.py`.
- [x] Add `ProtectedTargetConfigError`.
- [x] Add a skip/error class or reuse an existing skip classification in a way that produces a skipped outcome, not retry/failure.
- [x] Implement `load_protected_targets(env=None)` reading `SOAR_PROTECTED_IPS`.
- [x] Parse comma-separated exact IPs and CIDRs with `ipaddress`.
- [x] Normalize exact IPs to `/32` or `/128` networks.
- [x] Ignore blank entries caused by whitespace or doubled commas.
- [x] Fail closed on invalid entries by raising `ProtectedTargetConfigError`.
- [x] Implement `is_protected_target(ip_address, protected_networks=None)`.
- [x] Implement `require_unprotected_target(ip_address, protected_networks=None)`.

Verification:

- [x] Add tests for exact protected IP matching.
- [x] Add tests for protected CIDR matching.
- [x] Add tests for whitespace and blank-entry normalization.
- [x] Add tests for invalid config handling.
- [x] Add tests for non-protected public IP allowed.
- [x] Run focused helper tests.

## Step 2: Integrate Policy Before `block_ip` Approval Creation

- [x] Locate the worker approval gate for `block_ip` in `engines/soar_action_worker.py`.
- [x] Add protected-target check before creating an approval request.
- [x] If the target is protected, transition the queue row to `skipped`.
- [x] Use a stable skip code/message such as `protected_target`.
- [x] If protected config is invalid, transition the queue row to `skipped`.
- [x] Use a stable skip code/message such as `protected_target_config_invalid`.
- [x] Ensure protected skip does not call the executor.
- [x] Ensure protected skip does not create an approval request.
- [x] Ensure protected skip does not increment `retry_count`.
- [x] Keep non-protected public `block_ip` behavior approval-gated.
- [x] Keep non-block actions unchanged.

Verification:

- [x] Test protected exact IP in worker path skips safely.
- [x] Test protected CIDR member in worker path skips safely.
- [x] Test invalid protected config in worker path skips safely.
- [x] Test protected skip creates no approval request.
- [x] Test protected skip does not call executor/adapter.
- [x] Test protected skip does not increment `retry_count`.
- [x] Test non-protected public `block_ip` still creates approval.
- [x] Test non-block action behavior is unchanged.

## Step 3: Integrate Policy Into Dry-Run Firewall Adapter

- [x] Read `integrations/soar_adapters/linux_firewall.py` and current adapter validation tests.
- [x] Add protected-target check before command-plan construction.
- [x] If target is protected, reject with skipped classification.
- [x] If protected config is invalid, reject with skipped classification.
- [x] Do not produce a command plan for protected targets.
- [x] Preserve existing public IP dry-run behavior for non-protected targets.
- [x] Preserve existing private/loopback/reserved validation behavior.

Verification:

- [x] Test dry-run adapter rejects protected exact IP.
- [x] Test dry-run adapter rejects protected CIDR member.
- [x] Test dry-run adapter rejects invalid protected config safely.
- [x] Test dry-run adapter allows non-protected public IP.
- [x] Test dry-run adapter still rejects private/loopback/reserved IPs.

## Step 4: Configuration Documentation

- [x] Document `SOAR_PROTECTED_IPS` in the appropriate environment/config documentation if such a file exists.
- [x] Include examples for exact IP and CIDR entries.
- [x] Document fail-closed invalid config behavior.
- [x] Do not add secrets or real personal IP addresses to committed examples.

## Step 5: Regression and Safety Audit

- [x] Run targeted SOAR worker tests.
- [x] Run targeted adapter tests.
- [x] Run approval store/routes tests if approval-gate behavior changed.
- [x] Run full backend test suite.
- [x] Confirm no frontend files were modified unless explicitly required.
- [x] Confirm no real firewall execution was added.
- [x] Confirm no scheduler, daemon, cron, systemd unit, or background thread was added.
- [x] Confirm ingest, detection, and correlation files were not modified.
- [x] Confirm approval decision logic was not modified.
- [x] Confirm protected `block_ip` skips do not create approval requests.
- [x] Confirm protected `block_ip` skips do not execute adapters.
- [x] Confirm protected `block_ip` skips do not increment `retry_count`.

## Suggested Verification Commands

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py
python3 -m pytest tests/test_response_action_queue.py tests/test_soar_adapter_interface.py -x --tb=short -v
python3 -m pytest tests/ -x --tb=short -v
git status --short
```
