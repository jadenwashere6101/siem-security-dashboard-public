# Tasks: SOAR Playbook Step Executor Simulation

Implement later in small backend-only steps. Do not implement as part of this spec-only
change.

## Step 1: Reconfirm Current State

- [ ] Read `core/playbook_store.py`.
- [ ] Read `engines/playbook_registry.py`.
- [ ] Read `engines/soar_playbook_orchestrator.py`.
- [ ] Read `tests/test_playbook_store.py`.
- [ ] Read `tests/test_soar_playbook_orchestrator.py`.
- [ ] Confirm `playbook_executions` are currently created as inert `pending` records.

Stop if pending executions are not available to consume.

## Step 2: Add Store Helper Tests

File:

```text
tests/test_playbook_store.py
```

Add tests for future helpers:

- [ ] Claim next pending execution returns the oldest or deterministic pending row.
- [ ] Claim helper does not return `running`, `success`, `failed`, or `abandoned` rows.
- [ ] Mark running sets `started_at` and status `running`.
- [ ] Mark success sets `completed_at` and status `success`.
- [ ] Mark failed sets `completed_at` and status `failed`.
- [ ] Write `steps_log` stores a JSON array.
- [ ] Update `last_completed_step` stores the expected integer.
- [ ] Helpers do not commit internally.
- [ ] Helpers do not touch SOAR queue rows.
- [ ] Helpers do not touch approval rows.

## Step 3: Add Store Helpers

File:

```text
core/playbook_store.py
```

Add narrow helpers such as:

- [ ] `claim_next_pending_playbook_execution(conn, now=None)`.
- [ ] `set_playbook_execution_running(conn, execution_id, now=None)`.
- [ ] `set_playbook_execution_success(conn, execution_id, steps_log, last_completed_step, now=None)`.
- [ ] `set_playbook_execution_failed(conn, execution_id, steps_log, last_completed_step=None, now=None)`.
- [ ] Optional `update_playbook_execution_step_log(conn, execution_id, steps_log, last_completed_step=None)`.

Rules:

- [ ] Use parameterized SQL.
- [ ] Do not commit internally.
- [ ] Do not touch `response_actions_queue`.
- [ ] Do not touch approvals.
- [ ] Do not touch alerts.
- [ ] Keep existing helper behavior unchanged.

Verification:

```bash
python3 -m py_compile core/playbook_store.py
python3 -m pytest tests/test_playbook_store.py
```

## Step 4: Add Executor Tests First

New file:

```text
tests/test_soar_playbook_step_executor.py
```

Cover:

- [ ] No pending execution returns empty/none result.
- [ ] Pending execution with one `monitor` step becomes `success`.
- [ ] Pending execution with `monitor`, `flag_high_priority`, and `block_ip` steps becomes
      `success`.
- [ ] `steps_log` contains one entry per step.
- [ ] Each step entry includes `simulated=true` and `executed=false`.
- [ ] `last_completed_step` is updated after successful steps.
- [ ] Missing playbook definition marks execution `failed`.
- [ ] Invalid `steps` root marks execution `failed`.
- [ ] Unsupported action marks execution `failed`.
- [ ] Terminal successful execution is skipped and not modified.
- [ ] Batch processing respects limit.
- [ ] No SOAR queue rows are created.
- [ ] No approval rows are created.
- [ ] No response action logs are created unless explicitly documented as simulation audit
      output.
- [ ] No adapters/firewall/blocklist/network calls occur.

## Step 5: Add Simulation Executor Module

New file:

```text
engines/soar_playbook_step_executor.py
```

Implement:

- [ ] `process_next_pending_playbook_execution(conn, now=None)`.
- [ ] `process_playbook_execution(conn, execution_id, now=None)`.
- [ ] `process_playbook_execution_batch(conn, limit=10, now=None)`.
- [ ] Private `_simulate_step(step, context, now)` or equivalent.

Rules:

- [ ] Simulation-only.
- [ ] Load linked definition through `core.playbook_store`.
- [ ] Process only pending executions in batch path.
- [ ] Skip terminal executions.
- [ ] Mark execution `running` before simulating steps.
- [ ] Mark execution `success` after all steps succeed.
- [ ] Mark execution `failed` on validation or simulation failure.
- [ ] Record stable `steps_log` entries.
- [ ] Do not import adapter modules.
- [ ] Do not import or call SOAR queue enqueue helpers.
- [ ] Do not create approvals.
- [ ] Do not mutate alerts.
- [ ] Do not commit internally unless the final design explicitly chooses executor-owned
      transaction boundaries; prefer caller-owned commits for consistency.

Verification:

```bash
python3 -m py_compile engines/soar_playbook_step_executor.py
python3 -m pytest tests/test_soar_playbook_step_executor.py
```

## Step 6: Add Optional Manual Runner

Only add this if implementation remains small and useful.

New file:

```text
scripts/soar_playbook_simulation_run.py
```

Requirements:

- [ ] Run one bounded batch and exit.
- [ ] Default batch size is small, e.g. 10.
- [ ] Hard cap batch size, e.g. 50.
- [ ] Simulation-only wording in output.
- [ ] Requires `DATABASE_URL`.
- [ ] No daemon loop.
- [ ] No systemd/scheduler instructions.
- [ ] No real mode flag.

Add tests only if runner is added:

- [ ] Missing `DATABASE_URL` exits non-zero.
- [ ] Batch size is capped.
- [ ] Runner calls simulation executor batch function.
- [ ] Runner output does not imply real execution.

## Step 7: Add No-Real-Execution Safeguard Tests

File:

```text
tests/test_soar_playbook_step_executor.py
```

Add explicit assertions/mocks:

- [ ] Adapter registry is not called.
- [ ] Linux firewall adapter is not imported/called.
- [ ] `enqueue_response_action` is not called.
- [ ] `enqueue_committed_alerts` is not called.
- [ ] Approval creation helpers are not called.
- [ ] No `response_actions_queue` rows are created.
- [ ] No network libraries are used by the executor module.

## Verification Commands

Focused checks:

```bash
python3 -m py_compile core/playbook_store.py engines/soar_playbook_step_executor.py
python3 -m pytest tests/test_playbook_store.py
python3 -m pytest tests/test_soar_playbook_step_executor.py
```

Existing playbook checks:

```bash
python3 -m pytest tests/test_playbook_engine.py
python3 -m pytest tests/test_playbook_registry.py
python3 -m pytest tests/test_playbook_routes.py
python3 -m pytest tests/test_soar_playbook_orchestrator.py
```

SOAR safety checks:

```bash
python3 -m pytest tests/test_soar_queue_visibility_api.py
python3 -m pytest tests/test_soar_worker_admin_run_control.py
python3 -m pytest tests/test_response_action_queue.py
python3 -m pytest tests/test_approval_store.py
python3 -m pytest tests/test_approval_routes.py
python3 -m pytest tests/test_incident_store.py
python3 -m pytest tests/test_incident_routes.py
python3 -m pytest tests/test_soar_protected_targets.py
python3 -m pytest tests/test_soar_adapter_interface.py
```

Pipeline regression checks:

```bash
python3 -m pytest tests/test_failed_login_detection.py
python3 -m pytest tests/test_password_spraying_detection.py
python3 -m pytest tests/test_correlated_activity.py
python3 -m pytest tests/test_targeted_correlation.py
python3 -m pytest tests/test_ingest_api_contracts.py
python3 -m pytest tests/test_alert_mutation_api_contracts.py
```

If a runner is added:

```bash
python3 -m py_compile scripts/soar_playbook_simulation_run.py
python3 -m pytest tests/test_soar_playbook_simulation_runner.py
```

## Stop/Rollback Conditions

- [ ] Stop if implementation requires real firewall execution.
- [ ] Stop if implementation requires Slack/email/PagerDuty/webhook integration.
- [ ] Stop if implementation requires a daemon/systemd/scheduler.
- [ ] Stop if implementation requires approval gates.
- [ ] Stop if implementation enqueues `response_actions_queue` rows.
- [ ] Stop if implementation changes SOAR queue worker behavior.
- [ ] Stop if implementation changes ingest, detection, or correlation.
- [ ] Stop if implementation requires frontend changes.
- [ ] Stop if implementation requires non-additive schema changes.
- [ ] Roll back the current implementation step if focused executor tests fail.
- [ ] Roll back the current implementation step if SOAR queue, approval, incident,
      protected-target, adapter, or pipeline tests regress.
