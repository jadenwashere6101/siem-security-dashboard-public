# SOAR Response Outcome Model

Last updated: 2026-07-05

This document is the canonical architecture reference for response outcome
semantics. It defines how the dashboard and API answer:

> What happened, what response was selected, what playbook ran, and was anything actually executed?

## Model Overview

The response outcome model uses two additive canonical tables:

- `soar_response_decisions`: one row for the response that was selected.
- `soar_response_outcome_events`: append-only lifecycle events for that decision.

The split is intentional. A decision explains what the system, playbook, analyst,
or migration selected and why. Outcome events explain what happened after that
selection: queued, awaiting approval, running, skipped, blocked, failed,
simulated success, tracking-only success, or guarded real success.

Legacy SOAR tables remain operationally authoritative during rollout. The
canonical tables add traceability and dashboard language; they do not replace
queue, approval, playbook, notification, incident, blocklist, or audit behavior.

## `soar_response_decisions`

Purpose: record the selected response once per response lifecycle.

Key fields:

| Field | Meaning |
|---|---|
| `id` | Canonical decision id. |
| `soar_correlation_id` | Safe lifecycle id shared across related SOAR rows. Unique and non-empty. |
| `parent_soar_correlation_id` | Optional parent lifecycle for retried or child work. |
| `alert_id`, `incident_id`, `source_ip` | Investigation context. |
| `selected_action` | Response selected, such as monitor, notify, block_ip, or playbook action. |
| `decision_source` | Source that selected the response. |
| `reason_code` | Optional canonical reason for the decision. |
| `outcome_summary` | Analyst-readable decision summary. |
| `playbook_id`, `playbook_execution_id`, `playbook_step_index` | Playbook linkage where relevant. |
| `queue_id`, `approval_request_id` | Queue and approval linkage where relevant. |
| `created_by` | User id for manual decisions when known. |
| `safe_metadata` | Redacted metadata only. No secrets, tokens, URLs, raw headers, raw payloads, or provider responses. |

Constraints:

- `soar_correlation_id` and `selected_action` must be non-empty.
- `decision_source` must be one of the canonical values below.
- `reason_code` must be null or one canonical reason code.
- `playbook_step_index` must be null or non-negative.
- `idx_soar_response_decisions_soar_correlation_id` enforces one decision per
  correlation id.

## `soar_response_outcome_events`

Purpose: append-only evidence of lifecycle transitions for a decision.

Key fields:

| Field | Meaning |
|---|---|
| `id` | Canonical event id. |
| `decision_id` | Required reference to `soar_response_decisions`. |
| `soar_correlation_id` | Same safe lifecycle id as the decision. |
| `event_type` | Transition name, usually matching the canonical state. |
| `execution_mode` | Class of response path. |
| `execution_state` | Lifecycle state. |
| `external_executed` | True only for guarded real success with external/provider or actual local enforcement evidence. |
| `tracking_recorded` | True only when internal SIEM tracking was recorded. |
| `simulated` | True only for simulation evidence. |
| `execution_actor` | Worker/service/adapter/manual actor that produced the event. |
| `reason_code` | Optional canonical reason. |
| `outcome_summary` | Analyst-readable event summary. |
| `queue_id`, `playbook_execution_id`, `approval_request_id`, `notification_delivery_attempt_id`, `response_action_log_id` | Related subsystem rows. |
| `provider`, `adapter_name`, `external_reference` | Safe adapter/provider evidence identifiers. |
| `idempotency_key` | Optional unique key for retry-safe and backfill-safe event writes. |
| `metadata` | Redacted event metadata only. |
| `occurred_at`, `created_at` | Event timing. |

Append-only semantics:

- Existing events are not rewritten to change historical facts.
- New state is represented by appending a later event.
- The latest outcome is derived by ordering events, not by hand-maintaining a
  mutable truth field.
- Events with `idempotency_key` are unique so repeated worker entry or backfill
  runs do not create duplicate evidence.

## SOAR Correlation ID Propagation

`soar_correlation_id` is a safe lifecycle identifier, not a provider delivery id.
It is generated as `soar-{alert_id or none}-{short_uuid}` for new work and as
`legacy-{table}-{id}` for backfilled rows.

Propagation rules:

| Surface | Rule |
|---|---|
| Alerts | Detection-selected or manual response work starts or links to a SOAR correlation id. |
| Queue | `response_actions_queue.decision_id` and `soar_correlation_id` link durable queue work to the selected response. |
| Playbooks | `playbook_executions.decision_id` and `soar_correlation_id` link execution-level decisions and step events. |
| Approvals | `approval_requests.decision_id` and `soar_correlation_id` link approval gates to queue or playbook work. |
| Notifications | `notification_delivery_attempts.decision_id` and `soar_correlation_id` link delivery evidence separately from provider identifiers. |
| Response logs | `response_actions_log.decision_id` and `soar_correlation_id` link terminal legacy log rows where available. |
| Incidents | Incident APIs read related canonical outcomes; incident state is not mutated by outcome events. |
| Audit log | Relevant audit rows can be linked through safe details and an outcome event when they represent SOAR lifecycle changes. |

## Latest-Outcome Read Model

Latest outcome is derived from `soar_response_outcome_events` using
`occurred_at DESC, created_at DESC, id DESC`.

Backend helpers in `core/soar_response_outcomes.py` include:

- `get_latest_outcome_for_decision`
- `get_latest_outcome_for_alert`
- `get_latest_outcome_for_incident`
- `get_latest_outcome_for_source_ip`
- `get_latest_outcome_for_queue`
- `get_latest_outcome_for_playbook_execution`
- `get_latest_outcome_for_approval_request`
- `get_latest_outcome_for_notification_delivery`
- `get_latest_outcome_by_correlation_id`
- `get_latest_outcomes_for_alerts_bulk`
- `get_latest_outcomes_for_queues_bulk`
- `get_latest_outcomes_for_playbook_executions_bulk`
- `get_latest_outcomes_for_approvals_bulk`
- `serialize_latest_outcome`
- `serialize_outcome_timeline`

The serialized `response_outcome` shape includes:

- `soar_correlation_id`
- `decision_id`
- `latest_outcome_event_id`
- `selected_action`
- `decision_source`
- `execution_actor`
- `outcome_label`
- `execution_mode`
- `execution_state`
- `external_executed`
- `tracking_recorded`
- `simulated`
- `outcome_summary`
- `reason_code`
- `decision`
- `latest_outcome`
- `related`
- `timestamps`

If no canonical row exists, APIs should include `response_outcome: null` rather
than omitting the key. Compatibility resolvers in
`core/soar_response_outcomes_legacy.py` infer the same shape for older records
when canonical rows are absent.

## Canonical Values

`execution_mode`:

- `observed`: detection or context exists; no response execution evidence.
- `simulation`: response lifecycle is simulated.
- `tracking_only`: internal SIEM tracking state was recorded only.
- `real`: guarded real provider delivery or actual local enforcement path.

`execution_state`:

- `observed`
- `selected`
- `queued`
- `awaiting_approval`
- `running`
- `skipped`
- `blocked`
- `succeeded`
- `failed`

`decision_source`:

- `detection_default`
- `correlation`
- `playbook`
- `manual`
- `migration`

`execution_actor`:

- `queue_worker`
- `playbook_worker`
- `adapter`
- `approval_service`
- `manual`
- `system`

`reason_code`:

- `approval_required`
- `approval_denied`
- `simulation_mode`
- `tracking_only`
- `adapter_unavailable`
- `provider_error`
- `policy_blocked`
- `duplicate_suppressed`
- `unsupported_action`

## Boolean Compatibility

| Boolean | Canonical rule |
|---|---|
| `external_executed` | May be true only when `execution_mode=real` and `execution_state=succeeded`. |
| `tracking_recorded` | May be true only when `execution_mode=tracking_only` and `execution_state=succeeded`. |
| `simulated` | May be true only when `execution_mode=simulation`. |

Additional rules:

- `execution_mode=observed` requires all three booleans to be false.
- `execution_mode=real` requires `simulated=false` and `tracking_recorded=false`.
- `execution_mode=tracking_only` requires `simulated=false` and `external_executed=false`.
- Simulation outcomes must not set `external_executed` or `tracking_recorded`.

## Dashboard Wording Guide

This guide is authoritative for all frontend label decisions introduced by
Phases 7-9. Standalone `Executed` must not be used in any canonical label.

Canonical labels:

| Condition | Label | Meaning |
|---|---|---|
| `execution_mode=observed`, `execution_state=observed`, all booleans false | Observed only | Detection/context exists; no selected or executed response. |
| `execution_mode=simulation` or `simulated=true` | Simulated | Response evidence is simulation-only. |
| `execution_mode=tracking_only` or `tracking_recorded=true` | Tracking only | SIEM state was recorded; no firewall/provider/local enforcement occurred. |
| `execution_mode=real`, `execution_state=succeeded`, `external_executed=true` | Real executed | Guarded real provider delivery or actual local enforcement occurred. |
| `execution_state=failed` | Failed | Response path failed or terminal failure was recorded. |
| `execution_state=blocked`, usually `reason_code=approval_denied` | Blocked by approval | Approval denial or expiration blocked the response. Use `Blocked` where space is constrained. |
| `execution_state=awaiting_approval`, usually `reason_code=approval_required` | Awaiting approval | Selected response is paused for human approval. |
| `execution_state=skipped` | Skipped | No execution was attempted because policy, duplicate suppression, unsupported action, protected target, validation, or operator flow skipped it. |
| `execution_state=queued` | Queued | Durable work exists and is waiting for processing. |
| `execution_state=running` | Running | Worker or playbook processing is in progress. |
| `execution_state=selected` | Selected | Response was selected but no later lifecycle event is available. |
| `execution_state=succeeded`, none of the three booleans true | Selected | Success evidence is not enough to claim simulation, tracking, or real execution. Prefer the summary for detail. |

Composite in-progress labels should combine state and mode when it reduces
ambiguity:

- `Running - Simulated`
- `Running - Real`
- `Queued - Simulated`
- `Awaiting approval - Real`

Do not collapse these to `Executed`. If a label needs to mention execution, use
the explicit canonical phrase: `Real executed`, `Simulated`, or `Tracking only`.

## Schema Additions and Rollback Behavior

| Object | Added for | Rollback behavior |
|---|---|---|
| `soar_response_decisions` | Canonical selected response records. | Can be ignored or dropped by a separately approved rollback migration. Legacy behavior remains in existing tables. |
| `soar_response_outcome_events` | Append-only lifecycle events. | Can be ignored or dropped by a separately approved rollback migration. Legacy behavior remains in existing tables. |
| `response_actions_queue.decision_id`, `response_actions_queue.soar_correlation_id` | Queue linkage. | Nullable and additive. Existing queue queries can ignore them. |
| `response_actions_log.decision_id`, `response_actions_log.soar_correlation_id` | Terminal log linkage. | Nullable and additive. Existing log queries can ignore them. |
| `playbook_executions.decision_id`, `playbook_executions.soar_correlation_id` | Playbook execution linkage. | Nullable and additive. Existing playbook queries can ignore them. |
| `approval_requests.decision_id`, `approval_requests.soar_correlation_id` | Approval linkage. | Nullable and additive. Existing approval queries can ignore them. |
| `notification_delivery_attempts.decision_id`, `notification_delivery_attempts.soar_correlation_id` | Notification delivery linkage. | Nullable and additive. Existing notification queries can ignore them. |
| Canonical indexes | Query performance and uniqueness. | Dropping indexes affects canonical read performance only. Legacy behavior remains. |

Rollback does not require reconstructing old behavior because legacy tables
remain authoritative during rollout. Prefer leaving additive data in place and
reverting readers/writers first. Drop canonical objects only through a separate
approved rollback migration if retention requirements allow it.

## Backfill Strategy and Legacy Compatibility

Backfill uses `scripts/soar_outcome_backfill.py`.

Dry-run mode:

```bash
python3 scripts/soar_outcome_backfill.py --dry-run --db-url "$DATABASE_URL"
```

Dry-run prints a summary dictionary covering:

- total records scanned
- proposed decisions and events
- decisions/events by source table
- mode/state counts
- reason-code counts
- execution boolean counts
- observed-only count
- ambiguous count and up to 25 ambiguous record examples

Review before write mode:

- Confirm no ambiguous rows would be classified as `real`.
- Confirm notification real successes require `mode=real`, `status=success`,
  `metadata.executed=true`, `metadata.simulated=false`, and provider success
  evidence such as real adapter mode, delivery success, or a 2xx HTTP status.
- Confirm tracking-only blocklist rows say no enforcement occurred.
- Confirm unknown legacy statuses map conservatively to simulation or selected
  states with all execution booleans false.

Write mode:

```bash
python3 scripts/soar_outcome_backfill.py --apply --db-url "$DATABASE_URL"
```

Write mode is idempotent:

- Decisions are reused by deterministic `soar_correlation_id`.
- Events are reused by deterministic `legacy-backfill-{table}-{id}-event-latest`
  idempotency keys.
- Legacy rows are linked with nullable `decision_id` and `soar_correlation_id`
  only where the row still lacks linkage.
- Re-running should show reused decisions/events rather than duplicate rows.

Confirm no duplicates:

- Compare `soar_response_decisions` and `soar_response_outcome_events` counts
  before and after a second write-mode run.
- Check for duplicate `soar_correlation_id` in decisions and duplicate non-null
  `idempotency_key` in events.
- Confirm apply summary reports reused rows on repeat.

Conservative defaults:

- Alert-only records with no response are `observed/observed`.
- Legacy selected responses without execution evidence are `simulation/selected`.
- Queue success maps to simulated success unless real evidence exists elsewhere.
- Response-log `block_ip` rows with a matching SIEM blocklist row map to
  `tracking_only/succeeded`.
- Unknown statuses are marked ambiguous and need review.
- No ambiguous row may infer `external_executed=true`.

Known mapping gaps:

- Legacy text fields can indicate simulation or tracking only, but they cannot
  always prove what provider work happened.
- Some historical rows lack direct alert, incident, or source-IP linkage.
- `blocked_ips` direct decision/correlation columns are not part of the current
  schema; manual tracking-only outcomes link through alert/source IP/response log
  where available.
- Old audit rows may lack enough details to link to a decision.
- Provider-specific delivery evidence may be missing from older notification
  metadata, so those rows remain simulation/failed/ambiguous unless explicit
  success evidence is present.

## Real Execution Safety Boundaries

Firewall:

- The firewall adapter remains simulation/dry-run/tracking-only in the current
  implementation.
- No Phase 1-13 work enables real firewall enforcement.
- Manual `block_ip` records SIEM blocklist tracking only and must set
  `tracking_recorded=true`, `external_executed=false`, and `simulated=false`.
- No local firewall/provider enforcement is implied by a blocklist row.

Notifications:

- Real notification execution requires guarded real-mode adapter evidence.
- `external_executed=true` requires explicit metadata confirming delivery
  success: real mode, successful provider result, `executed=true`,
  `simulated=false`, and provider acceptance evidence.
- Fail-closed, timeout, blocked, unavailable, missing-guard, or ambiguous paths
  must not set `external_executed=true`.

Future boundary changes:

- Any change that enables real firewall enforcement or relaxes guarded real
  notification evidence requires a separate approved OpenSpec.
