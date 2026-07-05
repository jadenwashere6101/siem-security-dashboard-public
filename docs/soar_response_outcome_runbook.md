# SOAR Response Outcome Analyst Runbook

Last updated: 2026-07-05

Use this runbook to answer the analyst question:

> What happened, what response was selected, what playbook ran, and was anything actually executed?

The authoritative field is `response_outcome` when present. If it is null, use
legacy fields and compatibility notes from the same screen.

## What Happened to This Alert?

1. Open the alert in Alert Details or expand the alert row.
2. Read the canonical response outcome badge.
3. Read the response outcome summary.
4. Confirm `selected_action` to see what response was selected.
5. Confirm `decision_source` to see whether detection, correlation, playbook,
   manual action, or migration selected it.
6. Use `soar_correlation_id` to compare the same lifecycle across queue,
   playbook, approval, notification, incident, source-IP context, and audit views.
7. If `response_outcome` is null, treat the alert as having no canonical history
   yet and use legacy `response_action`/`response_status` only as transitional
   evidence.

Interpretation:

- `Observed only`: no selected or executed response.
- `Simulated`: no real provider/local enforcement occurred.
- `Tracking only`: SIEM tracking state changed only.
- `Real executed`: guarded real provider delivery or actual local enforcement
  evidence exists.
- `Awaiting approval`, `Blocked by approval`, `Skipped`, and `Failed` are
  lifecycle states; read `reason_code` and summary for the cause.

## Was Anything Actually Executed?

1. Open the record and locate `response_outcome.external_executed`.
2. If `external_executed=true`, confirm the label is `Real executed` and the
   latest event has `execution_mode=real`, `execution_state=succeeded`.
3. If `external_executed=false` and `tracking_recorded=true`, the system recorded
   internal SIEM state only. It did not enforce a firewall/provider action.
4. If `simulated=true` or `execution_mode=simulation`, the result is simulation
   evidence only.
5. For notifications, confirm provider evidence exists in the related
   notification delivery attempt before describing it as real execution.
6. For firewall/blocklist work, do not describe the result as enforcement. Current
   firewall behavior remains dry-run/tracking-only unless a future approved spec
   changes that boundary.

## Why Was This Blocked?

1. Locate the canonical outcome on Alert Details, SOAR Queue, Playbooks, or
   Approvals Panel.
2. Confirm `execution_state=blocked`.
3. Confirm `reason_code=approval_denied` for approval denial or expiration.
4. Open the Approvals Panel and search for the related `approval_request_id`.
5. Read approval events to distinguish denied from expired. Both map to the
   canonical reason code `approval_denied`; the summary should preserve the
   difference.
6. Confirm `external_executed=false`, `tracking_recorded=false`, and
   `simulated=false` for blocked approval outcomes.

## What Playbook Ran?

1. Read `response_outcome.related.playbook_execution_id`.
2. Open the Playbooks Panel.
3. Search or filter to the execution id.
4. Read the execution timeline for step-level state, approval pauses, retries,
   failures, and terminal state.
5. Compare the execution `soar_correlation_id` to the alert or queue row to prove
   it is the same lifecycle.
6. If the id is absent, no playbook execution is linked to this canonical outcome.

## What Does This Queue Item Mean?

1. Open the SOAR Queue detail panel.
2. Read the queue status and canonical response outcome side by side.
3. Use `soar_correlation_id` to trace the item to alert, approval, response log,
   playbook execution, notification delivery, incident, or audit evidence.
4. Read `execution_state`:
   - `queued`: waiting for processing.
   - `awaiting_approval`: paused for approval.
   - `running`: worker has claimed it.
   - `skipped`: no execution was attempted.
   - `blocked`: approval or policy prevented execution.
   - `failed`: failed path or terminal failure.
   - `succeeded`: read mode/booleans before saying what kind of success.
5. Read booleans before saying "executed":
   - `external_executed=true`: real execution evidence.
   - `tracking_recorded=true`: internal SIEM tracking only.
   - `simulated=true`: simulation only.

## Interview Notes

Canonical outcomes were introduced because the old word `executed` was
ambiguous. A simulated queue action, a tracking-only SIEM blocklist insert, and a
real provider delivery are operationally different, but older surfaces could
collapse them into the same phrase.

The canonical model reduces ambiguity by using one model, one label set, and one
API shape across Alert Details, SOAR Queue, Playbooks, Approvals, Notifications,
Incidents, Source-IP Context, metrics, and reporting.

Preserved behavior:

- Simulation mode remains supported and explicit.
- Detection and correlation semantics were not redesigned.
- Approval workflows remain the gate for approval-required work.
- Legacy fields remain available during transition.
- Existing queue, playbook, notification, incident, blocklist, and audit records
  remain readable.

Not changed:

- Real firewall enforcement policy remains dry-run/tracking-only.
- Detection and correlation logic are unchanged.
- Approval policy is unchanged.
- Real notification semantics still require guarded adapter evidence.

How to explain the value:

- `execution_mode` tells what type of response path happened.
- `execution_state` tells where the lifecycle ended or paused.
- `external_executed`, `tracking_recorded`, and `simulated` answer whether
  anything real happened, only SIEM tracking happened, or the outcome was
  simulated.
- `soar_correlation_id` ties the answer together across views.
