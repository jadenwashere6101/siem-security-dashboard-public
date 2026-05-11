# Tasks: SOAR Playbook Approval Visibility Polish

Implement later as a visibility-only frontend change. Do not implement as part of this
spec-only change.

## Step 1: Reconfirm Current Data Shape

- [ ] Read `frontend/src/components/PlaybooksPanel.js`.
- [ ] Read `frontend/src/components/PlaybooksPanel.test.js`.
- [ ] Inspect sample `steps_log` entries from approval-gated executor tests.
- [ ] Confirm `GET /playbook-executions/<id>` returns `steps_log` without stripping approval
      fields.
- [ ] Confirm whether backend read API changes are unnecessary.

Stop if required approval context is not available from stored execution data and cannot be
added with read-only serializer polish.

## Step 2: Add Timeline Label Helpers

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Add helper to derive approval event label from `event`, `status`, and `action`.
- [ ] Map `approval_requested` to `Approval requested`.
- [ ] Map `approval_approved` to `Approval approved`.
- [ ] Map `approval_resumed` to `Simulation resumed`.
- [ ] Map `approval_denied` to `Approval denied`.
- [ ] Map `approval_expired` to `Approval expired`.
- [ ] Map `skipped_after_approval_gate` to `Skipped after approval gate`.
- [ ] Preserve existing generic labels for non-approval steps.

## Step 3: Add Awaiting Approval Notice

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Detect `detailRecord.status === "awaiting_approval"`.
- [ ] Also detect pending approval gate entries when useful.
- [ ] Render the exact message:

```text
Approval-gated simulation paused; no later steps will run until approval.
```

- [ ] Ensure the notice is read-only.
- [ ] Do not add approval, denial, resume, retry, run, cancel, or execute buttons.

## Step 4: Improve Approval Timeline Rows

File:

```text
frontend/src/components/PlaybooksPanel.js
```

- [ ] Show `approval_request_id` when present.
- [ ] Show `approval_status` when present.
- [ ] Show `risk_level` when present.
- [ ] Show skip reason from `output.skip_reason` for skipped later steps.
- [ ] Clearly show `simulated=true` and `executed=false`.
- [ ] Keep raw JSON secondary/read-only.
- [ ] Preserve existing timeline rendering for non-approval steps.
- [ ] Ensure long messages and IDs wrap safely.

## Step 5: Add Focused Frontend Tests

File:

```text
frontend/src/components/PlaybooksPanel.test.js
```

Add tests for:

- [ ] `awaiting_approval` execution renders the pause notice.
- [ ] `approval_requested` row shows approval request ID, status, and risk.
- [ ] approved/resumed rows render clear labels.
- [ ] denied row renders clear label and skipped later steps.
- [ ] expired row renders clear label and skipped later steps.
- [ ] skipped later steps show they were not executed.
- [ ] no approve/deny/resume/run/retry/cancel controls appear.
- [ ] existing non-approval execution timeline tests still pass.

## Step 6: Backend Read API Polish Only If Needed

Only if `GET /playbook-executions/<id>` omits needed stored fields.

Files:

```text
routes/playbook_routes.py
tests/test_playbook_routes.py
```

- [ ] Preserve all stored `steps_log` approval fields in response.
- [ ] Keep endpoint read-only.
- [ ] Add route test proving approval event fields serialize.
- [ ] Add route test proving read does not mutate execution or approval rows.

Do not add mutation APIs.

## Verification Commands

Frontend focused:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/components/PlaybooksPanel.test.js
```

Frontend full:

```bash
cd frontend
CI=true npm test -- --watchAll=false
npm run build
```

Backend only if read API polish is changed:

```bash
python3 -m py_compile routes/playbook_routes.py
python3 -m pytest tests/test_playbook_routes.py -v
```

Playbook/executor regression:

```bash
python3 -m pytest tests/test_playbook_step_executor.py tests/test_playbook_routes.py -v
```

Final check:

```bash
git status --short
```

## Stop/Rollback Conditions

- [ ] Stop if implementation requires executor behavior changes.
- [ ] Stop if implementation requires approval decision controls in PlaybooksPanel.
- [ ] Stop if implementation requires frontend run/resume/retry/cancel controls.
- [ ] Stop if implementation requires SOAR queue changes.
- [ ] Stop if implementation requires ingest/detection/correlation changes.
- [ ] Stop if implementation requires real adapters or integrations.
- [ ] Stop if implementation requires firewall/blocklist mutation.
- [ ] Stop if backend changes become more than read-only serializer polish.

Rollback plan:

- [ ] Revert only PlaybooksPanel visibility helpers/rendering/tests from this change.
- [ ] Revert backend read serializer tests/code only if added by this change.
- [ ] Preserve executor, approval, SOAR queue, ingest, detection, and correlation behavior.
