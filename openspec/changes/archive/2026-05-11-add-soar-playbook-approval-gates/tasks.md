# Tasks: SOAR Playbook Approval Gates

Implement later in small backend-first steps. Do not implement as part of this spec-only
change.

## Step 1: Reconfirm Current State

- [ ] Read `schema.sql` approval and playbook execution sections.
- [ ] Read `core/approval_store.py`.
- [ ] Read `core/playbook_store.py`.
- [ ] Read `engines/playbook_registry.py`.
- [ ] Read `engines/playbook_step_executor.py`.
- [ ] Read existing approval route/UI tests.
- [ ] Confirm whether `approval_requests` has a direct playbook execution link.

Stop if approval requests cannot safely link to a playbook execution and step index.

## Step 2: Add Minimal Schema Link If Required

File:

```text
schema.sql
```

- [ ] Add nullable `approval_requests.playbook_execution_id` only if no equivalent exists.
- [ ] Add nullable `approval_requests.playbook_step_index` only if no equivalent exists.
- [ ] Add an index on `playbook_execution_id`.
- [ ] Add a uniqueness guard for active approval requests per execution step.
- [ ] Adjust the approval target check so one of incident, queue, or playbook execution is
      required.
- [ ] Preserve existing incident and queue approval behavior.

Stop if this becomes a broad schema rewrite.

## Step 3: Add Registry Validation

Files:

```text
engines/playbook_registry.py
tests/test_playbook_registry.py
```

- [ ] Add `require_approval` as a supported playbook step action.
- [ ] Validate optional `risk_level`.
- [ ] Validate optional bounded `expires_in_minutes`.
- [ ] Validate optional `reason`.
- [ ] Validate `on_denied` and `on_expired` for the initially supported behavior.
- [ ] Confirm existing playbook definitions still validate.

## Step 4: Add Store Helper Tests

Files:

```text
tests/test_approval_store.py
tests/test_playbook_store.py
```

Add tests for:

- [ ] Creating a pending approval linked to `playbook_execution_id` and `playbook_step_index`.
- [ ] Reusing or rejecting duplicate active approval for the same execution step.
- [ ] Listing/getting approval requests includes playbook execution context if API visibility
      requires it.
- [ ] Marking playbook execution `awaiting_approval`.
- [ ] Returning awaiting approval executions for manual resume only.
- [ ] Updating `steps_log` with approval lifecycle entries.
- [ ] Store helpers do not commit internally.
- [ ] Store helpers do not touch `response_actions_queue`.

## Step 5: Add Store Helpers

Files:

```text
core/approval_store.py
core/playbook_store.py
```

- [ ] Add `create_playbook_step_approval_request(...)` or equivalent narrow helper.
- [ ] Add `get_active_playbook_step_approval_request(...)`.
- [ ] Add `list_approval_requests` support for playbook execution filters only if needed.
- [ ] Add `set_playbook_execution_awaiting_approval(...)`.
- [ ] Add `list_awaiting_approval_playbook_executions(...)` only if manual resume needs a
      batch path.
- [ ] Keep existing approval request helpers backward compatible.
- [ ] Do not import queue worker, adapters, ingest, detection, correlation, or frontend code.

## Step 6: Add Executor Approval Tests First

File:

```text
tests/test_playbook_step_executor.py
```

Exact backend test requirements:

- [ ] Pending execution with `require_approval` pauses as `awaiting_approval`.
- [ ] Pending approval prevents all later steps from running.
- [ ] Re-running while approval is pending does not duplicate approval requests or step logs.
- [ ] Approved approval resumes from the step after the gate.
- [ ] Approved resume records approval/resumed entries.
- [ ] Denied approval marks execution failed.
- [ ] Denied approval does not run later steps.
- [ ] Expired approval marks execution failed.
- [ ] Expired approval does not run later steps.
- [ ] Missing linked approval during resume does not continue execution.
- [ ] `block_ip` after approval remains simulated only.
- [ ] No `response_actions_queue` rows are created.
- [ ] No approvals are created for steps that are not `require_approval`.
- [ ] No adapters/firewall/blocklist/network calls occur.
- [ ] Terminal executions are not re-run.

## Step 7: Add Executor Behavior

File:

```text
engines/playbook_step_executor.py
```

- [ ] Detect `require_approval` during simulation.
- [ ] Create or reuse an approval request for the execution step.
- [ ] Append an approval requested entry to `steps_log`.
- [ ] Mark execution `awaiting_approval` and return without later steps.
- [ ] Add manual resume function for `awaiting_approval` executions.
- [ ] Resume only when linked approval is approved.
- [ ] Stop safely when linked approval is denied or expired.
- [ ] Keep all later remediation steps simulated only.
- [ ] Do not enqueue SOAR actions.
- [ ] Do not create queue rows.
- [ ] Do not call adapters.
- [ ] Do not mutate firewall/blocklist.

## Step 8: API/Frontend Test Requirements Only If Needed

Only do this if approval responses need additive playbook context visibility.

- [ ] Add approval route tests proving existing incident/queue approval responses still work.
- [ ] Add approval route tests for playbook execution context fields.
- [ ] Add narrow frontend approval visibility tests only if existing UI displays the new
      context.
- [ ] Do not redesign approval UI.
- [ ] Do not add playbook run/retry/cancel buttons.

## Verification Commands

Focused backend checks:

```bash
python3 -m py_compile core/approval_store.py core/playbook_store.py engines/playbook_registry.py engines/playbook_step_executor.py
python3 -m pytest tests/test_approval_store.py tests/test_playbook_store.py tests/test_playbook_registry.py tests/test_playbook_step_executor.py -v
```

Approval and queue regressions:

```bash
python3 -m pytest tests/test_approval_routes.py tests/test_response_action_queue.py tests/test_soar_queue_visibility_api.py tests/test_soar_worker_admin_run_control.py -v
```

Playbook regressions:

```bash
python3 -m pytest tests/test_playbook_engine.py tests/test_playbook_routes.py tests/test_soar_playbook_orchestrator.py -v
```

Pipeline regressions:

```bash
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
```

Frontend checks only if approval UI/API response display changes:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/components/ApprovalsPanel.test.js
CI=true npm test -- --watchAll=false
npm run build
```

Final check:

```bash
git status --short
```

## Stop/Rollback Conditions

- [ ] Stop if implementation requires real firewall execution.
- [ ] Stop if implementation requires Slack/email/PagerDuty/webhook integration.
- [ ] Stop if implementation requires daemon/systemd/scheduler behavior.
- [ ] Stop if implementation requires ingest/detection/correlation changes.
- [ ] Stop if implementation changes existing SOAR queue behavior.
- [ ] Stop if implementation enqueues `response_actions_queue` rows.
- [ ] Stop if implementation mutates firewall/blocklist.
- [ ] Stop if approval UI needs a broad redesign.
- [ ] Stop if playbook approval linking cannot be done with a narrow additive schema change.

Rollback plan:

- [ ] Revert only the playbook approval-gate helpers, executor changes, tests, and any narrow
      additive schema link from this change.
- [ ] Preserve existing approval, SOAR queue, incident, and playbook simulation behavior.
