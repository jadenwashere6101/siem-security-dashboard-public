## 1. Baseline and Safety Preflight

- [x] 1.1 Reconfirm live VM queue counts by status and action before implementation.
- [x] 1.2 Reconfirm oldest/newest pending queue timestamps and sample pending rows.
- [x] 1.3 Reconfirm running worker services and prove `soar-playbook-worker.service` does not drain `response_actions_queue`.
- [x] 1.4 Reconfirm no existing response-action worker service, timer, or cron entry is active.
- [x] 1.5 Reconfirm `block_ip` approval-gate behavior in `engines/soar_action_worker.py`.
- [x] 1.6 Reconfirm default response-action runner mode is simulation-safe and real firewall enforcement is out of scope.

## 2. Runner Configuration and Preflight Status

- [x] 2.1 Fix or document the deployed VM environment path required for `scripts/soar_worker_run.py --dry-run-info --json` to read queue counts without mutation.
- [x] 2.2 Add a safe helper script or documented command that constructs `DATABASE_URL` from VM `.env` without printing secrets.
- [x] 2.3 Verify dry-run status output reports pending, running, awaiting approval, failed, skipped, and success counts.
- [x] 2.4 Add or update tests if runner configuration behavior changes.

## 3. Deployment Artifacts

- [x] 3.1 Add a one-shot systemd service definition for the response-action queue runner.
- [x] 3.2 Add a systemd timer definition for bounded recurring response-action batches.
- [x] 3.3 Configure service defaults for `SOAR_EXECUTION_MODE=simulation` and bounded `SOAR_RUNNER_BATCH_SIZE`.
- [x] 3.4 Ensure service logs are visible through `journalctl` and do not print database credentials or secrets.
- [x] 3.5 Ensure service/timer names clearly distinguish response-action queue processing from playbook worker processing.
- [x] 3.6 Add install/enable/disable commands or an installation helper for the service/timer.

## 4. Operator Runbook

- [x] 4.1 Add runbook documentation for response-action queue status inspection.
- [x] 4.2 Add runbook documentation for one-time bounded simulation backlog drain.
- [x] 4.3 Add runbook documentation for enabling the recurring timer after sample-batch verification.
- [x] 4.4 Add runbook documentation for expected transitions: monitor/flag actions to success, block_ip to awaiting approval or safe skipped state.
- [x] 4.5 Add runbook documentation for rollback: stop/disable timer and service, preserve data.
- [x] 4.6 Add stop conditions: unexpected real mode, real firewall evidence, unbounded failures, database connection errors, or queue transitions outside expected states.

## 5. One-Time Backlog Drain Verification

- [x] 5.1 Capture before counts from the VM and save them in the implementation notes or runbook.
- [x] 5.2 Run one bounded response-action worker batch in simulation mode only after operator approval.
- [x] 5.3 Capture after counts and compare status transitions.
- [x] 5.4 Verify no real firewall enforcement occurred.
- [x] 5.5 Verify block_ip rows moved to awaiting approval or safe skipped state, not success-real execution.
- [x] 5.6 Continue bounded batches only if the first batch matches expected behavior and the operator approves continuing.

## 6. Timer Rollout Verification

- [x] 6.1 Install the response-action worker service/timer on the VM.
- [x] 6.2 Start or enable the timer only after one-time drain behavior is verified.
- [x] 6.3 Verify the timer invokes bounded batches and exits cleanly.
- [x] 6.4 Verify queue depth decreases or moves into expected approval/terminal states over timer runs.
- [x] 6.5 Verify `soar-playbook-worker.service` remains healthy and unchanged.
- [x] 6.6 Verify disabling the timer stops new scheduled response-action batches.

## 7. Tests and Validation

- [x] 7.1 Run focused response-action worker tests.
- [x] 7.2 Run focused runner configuration/deployment tests if deployment scripts are changed.
- [x] 7.3 Run `openspec validate add-response-action-queue-worker-rollout --strict`.
- [x] 7.4 Run `git diff --check`.
- [x] 7.5 Confirm no migrations were created.
- [x] 7.6 Confirm no frontend components were modified.

## 8. Completion Notes

- [x] 8.1 Document final VM queue counts by status and action.
- [x] 8.2 Document whether remaining items require analyst approval rather than worker action.
- [x] 8.3 Document installed service/timer names and current enabled/disabled state.
- [x] 8.4 Document rollback command summary.
- [x] 8.5 Confirm this change is safe to commit after validation.
