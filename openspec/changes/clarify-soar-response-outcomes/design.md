## Context

The current SIEM/SOAR records related facts across several independent surfaces:

- Detection creates `alerts` with `response_action` and `response_status`.
- Ingest post-processing creates `response_actions_queue` rows, incidents, and pending `playbook_executions`.
- The legacy queue worker writes terminal rows to `response_actions_log`.
- Playbook workers record step outcomes inside `playbook_executions.steps_log`.
- Approval gates use `approval_requests` and `approval_request_events`.
- Notification adapters write `notification_delivery_attempts`, including mode and provider outcome.
- Manual alert actions can write `response_actions_log` and, for `block_ip`, create a tracking-only `blocked_ips` row.
- Audit rows and dashboard views expose fragments of the same lifecycle without one consistent outcome model.

These records are individually useful, but they do not share canonical semantics. In particular, the word "executed" is overloaded. A simulated queue action can be logged as executed, a tracking-only blocklist insert records internal SIEM state without external enforcement, and real provider delivery is visible only in notification-specific records.

The design must preserve simulation mode, existing detection semantics, approval workflows, playbook behavior, source-IP context contracts, and current records. It should introduce a durable answer to the primary analyst question:

> What happened, what response was selected, what playbook ran, and was anything actually executed?

## Goals / Non-Goals

**Goals:**

- Define canonical outcome language for observed-only, simulated, tracking-only, real-executed, failed, blocked, awaiting-approval, and skipped states.
- Make manual actions, queue actions, playbook steps, approvals, adapter deliveries, source-IP context, SOC Command Center, Alert Details, SOAR Queue, Playbooks Panel, Attack Map popup, and Blocklist Manager use the same vocabulary.
- Add durable decision and append-only outcome-event records that link alert, queue, playbook, approval, adapter delivery, response log, incident, audit log, and UI summaries through a safe `soar_correlation_id`.
- Preserve old records and provide explicit compatibility/backfill semantics.
- Avoid vague UI labels. Any use of "executed" must say whether it was simulated, tracking-only, or real.
- Allow phased implementation across multiple sessions with verifiable checkpoints.

**Non-Goals:**

- Do not remove simulation mode.
- Do not make simulated actions look real.
- Do not treat tracking-only SIEM state as real execution.
- Do not enable new real firewall enforcement.
- Do not redesign detection, correlation, incident creation, SOAR approval policy, or playbook matching.
- Do not delete or rewrite existing historical records.
- Do not store secrets, raw provider payloads, webhooks, tokens, passwords, raw headers, raw responses, or unsafe exception text.
- Do not require autonomous retries, a new scheduler, or queue replay as part of this change.
- Do not commit or push as part of spec creation.

## Decisions

### Decision 1: Use a Canonical Outcome Model

The canonical model uses:

```text
execution_mode: observed | simulation | tracking_only | real
execution_state: observed | selected | queued | awaiting_approval | running | skipped | blocked | succeeded | failed
external_executed: boolean
tracking_recorded: boolean
simulated: boolean
decision_source: detection_default | correlation | playbook | manual | migration
execution_actor: queue_worker | playbook_worker | adapter | approval_service | manual | system
outcome_summary: text
reason_code: approval_required | approval_denied | simulation_mode | tracking_only | adapter_unavailable | provider_error | policy_blocked | duplicate_suppressed | unsupported_action
soar_correlation_id: safe shared string
```

Rationale:

- `execution_mode` answers what class of response path occurred.
- `execution_state` answers where the response is in the lifecycle.
- `external_executed` answers whether a real external provider or actual local enforcement action happened.
- `tracking_recorded` answers whether internal SIEM tracking state was recorded.
- `simulated` answers whether the lifecycle evidence came from simulation.
- `decision_source` explains what selected the response.
- `execution_actor` explains what worker/service/manual path produced an execution event.
- `outcome_summary` gives analyst-readable context.
- `soar_correlation_id` ties distributed records together without reusing delivery/provider correlation identifiers.

Compatibility note:

- Existing APIs may keep legacy `executed` fields while rolling out the canonical model, but new canonical payloads must not use `executed` as the source of truth.

Alternatives considered:

- Keep one `executed` boolean. Rejected because it cannot distinguish real enforcement from tracking-only internal state.
- Only infer from existing table statuses. Rejected because existing statuses are ambiguous and inconsistent.
- Only add UI formatting rules. Rejected because backend APIs would still return ambiguous data and historical compatibility would be fragile.
- Add separate enum sets per subsystem. Rejected because it preserves the current fragmentation.

### Decision 2: Use a Hybrid Decision/Event Data Model

Introduce two additive canonical tables:

1. `soar_response_decisions`: one row per selected response.
2. `soar_response_outcome_events`: append-only lifecycle/event trail for each decision.

Latest outcome is not a separately authored truth field. It is derived by API/read-model query from the most recent relevant outcome event for a decision, alert, incident, source IP, queue row, playbook execution, approval request, notification delivery, or SOAR correlation id.

#### `soar_response_decisions`

Suggested columns:

```text
id SERIAL PRIMARY KEY
soar_correlation_id VARCHAR(128) NOT NULL UNIQUE
parent_soar_correlation_id VARCHAR(128)
alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL
incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL
source_ip INET
selected_action TEXT NOT NULL
decision_source VARCHAR(64) NOT NULL
actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
playbook_id VARCHAR(64) REFERENCES playbook_definitions(id) ON DELETE SET NULL
playbook_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL
playbook_step_index INTEGER
queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE SET NULL
approval_request_id INTEGER REFERENCES approval_requests(id) ON DELETE SET NULL
reason_code VARCHAR(128)
decision_summary TEXT NOT NULL
safe_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
selected_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Constraints:

- `decision_source IN ('detection_default', 'correlation', 'playbook', 'manual', 'migration')`
- `reason_code` is either null or one of the canonical reason codes.
- `soar_correlation_id` must be safe and must not contain secrets or raw user/provider payloads.

#### `soar_response_outcome_events`

Suggested columns:

```text
id SERIAL PRIMARY KEY
decision_id INTEGER NOT NULL REFERENCES soar_response_decisions(id) ON DELETE CASCADE
soar_correlation_id VARCHAR(128) NOT NULL
event_type VARCHAR(64) NOT NULL
alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL
incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL
queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE SET NULL
response_log_id INTEGER REFERENCES response_actions_log(id) ON DELETE SET NULL
playbook_id VARCHAR(64) REFERENCES playbook_definitions(id) ON DELETE SET NULL
playbook_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL
playbook_step_index INTEGER
approval_request_id INTEGER REFERENCES approval_requests(id) ON DELETE SET NULL
approval_request_event_id INTEGER REFERENCES approval_request_events(id) ON DELETE SET NULL
notification_delivery_attempt_id INTEGER REFERENCES notification_delivery_attempts(id) ON DELETE SET NULL
blocked_ip_id INTEGER REFERENCES blocked_ips(id) ON DELETE SET NULL
audit_log_id INTEGER REFERENCES audit_log(id) ON DELETE SET NULL
source_ip INET
execution_mode VARCHAR(32) NOT NULL
execution_state VARCHAR(32) NOT NULL
external_executed BOOLEAN NOT NULL DEFAULT FALSE
tracking_recorded BOOLEAN NOT NULL DEFAULT FALSE
simulated BOOLEAN NOT NULL DEFAULT FALSE
execution_actor VARCHAR(64) NOT NULL
outcome_summary TEXT NOT NULL
reason_code VARCHAR(128)
provider VARCHAR(64)
adapter_name VARCHAR(64)
external_reference TEXT
idempotency_key VARCHAR(160)
safe_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
occurred_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Constraints:

- `execution_mode IN ('observed', 'simulation', 'tracking_only', 'real')`
- `execution_state IN ('observed', 'selected', 'queued', 'awaiting_approval', 'running', 'skipped', 'blocked', 'succeeded', 'failed')`
- `execution_actor IN ('queue_worker', 'playbook_worker', 'adapter', 'approval_service', 'manual', 'system')`
- `reason_code` is either null or one of the canonical reason codes.
- `external_executed = TRUE` only when `execution_mode = 'real'` and `execution_state = 'succeeded'`.
- `tracking_recorded = TRUE` only when `execution_mode = 'tracking_only'` and `execution_state = 'succeeded'`.
- `simulated = TRUE` only when `execution_mode = 'simulation'`.
- `execution_mode = 'observed'` requires all three booleans to be false.
- `execution_mode = 'real'` requires `simulated = FALSE` and `tracking_recorded = FALSE`.
- `execution_mode = 'tracking_only'` requires `simulated = FALSE` and `external_executed = FALSE`.

Indexes:

- `soar_response_decisions(alert_id)`
- `soar_response_decisions(incident_id)`
- `soar_response_decisions(source_ip)`
- `soar_response_decisions(soar_correlation_id)`
- `soar_response_decisions(created_at)`
- `soar_response_outcome_events(decision_id)`
- `soar_response_outcome_events(alert_id)`
- `soar_response_outcome_events(incident_id)`
- `soar_response_outcome_events(source_ip)`
- `soar_response_outcome_events(soar_correlation_id)`
- `soar_response_outcome_events(created_at)`
- Additional useful indexes may cover queue, playbook execution/step, approval request, notification delivery, mode/state/time, and unique `idempotency_key` where present.

Rationale:

- A decision table separates "what response was selected and why" from "what happened later."
- Append-only events provide an audit-friendly trail without mutating historical outcome facts.
- A latest-outcome read model keeps dashboard queries simple without copying every field into every legacy table.
- Additive schema minimizes rollback risk.

Alternatives considered:

- A single `soar_response_outcomes` table. Rejected because it can become ambiguous about whether a row is a decision, event, or current snapshot.
- Only extend each existing table. Rejected because every UI would still have to merge subsystem-specific semantics.
- Replace `response_actions_log`. Rejected because existing audit behavior and historical rows must remain readable.
- Store outcomes only in JSON. Rejected because queryability, metrics, and migration verification need indexed fields.

### Decision 3: Extend Existing Tables Only for Linkage

Use additive nullable linkage columns where they improve traceability:

- `alerts`: `soar_correlation_id`, `decision_id`, `latest_outcome_event_id` if useful for list rendering.
- `response_actions_queue`: `soar_correlation_id`, `decision_id`, `latest_outcome_event_id`.
- `response_actions_log`: `soar_correlation_id`, `decision_id`, `latest_outcome_event_id`.
- `playbook_executions`: `soar_correlation_id`, `decision_id`, `latest_outcome_event_id` where an execution maps to one primary response.
- `approval_requests`: `soar_correlation_id`, `decision_id`, `latest_outcome_event_id`.
- `approval_request_events`: `soar_correlation_id`, `decision_id`, `latest_outcome_event_id` if event linkage is useful.
- `notification_delivery_attempts`: add `soar_correlation_id`, `decision_id`, `latest_outcome_event_id` rather than overloading any provider/delivery correlation field.
- `incidents`: `latest_outcome_event_id` only if it materially improves list performance.
- `blocked_ips`: `soar_correlation_id`, `decision_id`, `latest_outcome_event_id` for tracking-only provenance.
- `audit_log`: `soar_correlation_id`, `decision_id`, `latest_outcome_event_id` when audit rows represent SOAR lifecycle changes.

Do not duplicate every canonical outcome field into every old table. If any legacy table needs copied mode/state booleans for a short-term performance reason, those fields must be explicitly documented as snapshot-only, and read paths must prefer canonical decisions/events where available.

Rationale:

- The canonical model remains authoritative.
- Legacy tables keep their current operational roles.
- Rollback can ignore additive linkage without reconstructing legacy behavior.

### Decision 4: Centralize Outcome Writing and Reading

Add backend helpers in a future implementation, such as `core/soar_response_outcome_store.py` and `core/soar_response_outcome_model.py`.

Responsibilities:

- Validate enums and boolean compatibility.
- Generate or propagate `soar_correlation_id`.
- Create one decision row for each selected response.
- Append lifecycle outcome events.
- Enforce idempotency keys for re-runnable backfill and retry-safe writers.
- Sanitize metadata.
- Produce latest-outcome read models and API serialization.
- Provide compatibility wrappers for older rows.

Rationale:

- Manual action, queue worker, playbook worker, approval routes, notification delivery, blocklist manager, audit log, and source-IP context must not each invent outcome language.

### Decision 5: SOAR Correlation ID Strategy

Use a safe string generated at first response selection, then propagate:

```text
soar-{alert_id or none}-{short_uuid}
```

Rules:

- Detection-created alert with selected default response starts a `soar_correlation_id`.
- Queue rows inherit the alert decision's `soar_correlation_id`.
- Playbook executions inherit the alert decision's `soar_correlation_id` when they represent the same response decision, or create child decisions for distinct selected step actions.
- Approval requests inherit the related decision's `soar_correlation_id`.
- Notification delivery attempts store `soar_correlation_id` separately from any provider or delivery-specific correlation identifier.
- Manual alert actions create a new `soar_correlation_id` if no response decision exists, or a child decision if a prior lifecycle already exists.
- Backfilled legacy records use deterministic `legacy-{table}-{id}` SOAR correlation ids and `decision_source='migration'`.

Rationale:

- One lifecycle id makes cross-view explanation possible without embedding secrets or provider ids.
- The `soar_` prefix avoids confusing SOAR lifecycle correlation with adapter/provider delivery correlation.

### Decision 6: Latest-Outcome API / Read Model

Every API that shows SOAR status should expose either:

- `response_outcome`: latest canonical outcome for a single record/context.
- `response_outcomes`: ordered canonical event timeline or recent list.

Latest outcome is derived from `soar_response_outcome_events` by the relevant decision/context and `occurred_at, id` ordering. APIs may use a SQL view, helper query, or materialized/cache table if performance requires it, but any cache must be treated as derived data.

Example latest outcome shape:

```json
{
  "soar_correlation_id": "soar-123-...",
  "decision_id": 77,
  "latest_outcome_event_id": 202,
  "selected_action": "block_ip",
  "decision_source": "manual",
  "execution_actor": "manual",
  "execution_mode": "tracking_only",
  "execution_state": "succeeded",
  "external_executed": false,
  "tracking_recorded": true,
  "simulated": false,
  "outcome_summary": "Recorded IP in SIEM blocklist only; no firewall enforcement occurred.",
  "reason_code": "tracking_only",
  "related": {
    "alert_id": 123,
    "queue_id": null,
    "playbook_id": null,
    "playbook_execution_id": null,
    "playbook_step_index": null,
    "approval_request_id": null,
    "notification_delivery_attempt_id": null,
    "incident_id": 44
  },
  "timestamps": {
    "selected_at": "...",
    "occurred_at": "..."
  }
}
```

Existing fields should remain during migration.

### Decision 7: UI Language

Use these labels:

- `Observed only`: detection exists; no response selected or executed.
- `Simulated`: response ran in simulation; no real provider/local enforcement action occurred.
- `Tracking only`: internal SIEM state changed, such as blocklist tracking; no firewall/provider/local enforcement occurred.
- `Real executed`: external provider or actual local enforcement action occurred.
- `Awaiting approval`: selected action is paused for human approval.
- `Blocked by approval`: approval denied or expired prevented the action.
- `Skipped`: no action was attempted due to validation, duplicate prevention, unsupported action, protected target, or operator-abandoned flow.
- `Failed`: action was attempted or prepared but failed according to the canonical state.

Avoid standalone `executed` in UI copy. Use phrases like `Simulated succeeded`, `Tracking-only recorded`, or `Real executed`.

### Decision 8: Backfill, Compatibility, and Idempotency

Backfill is additive and must support dry-run before writes:

- Alerts with no response fields produce `observed/observed` with all three booleans false.
- Alerts with `response_action` but no queue/log produce `simulation/selected` unless evidence proves tracking-only or real.
- Queue rows map current status to canonical state.
- Response log rows with details `Simulated ...` map to `simulation/succeeded`, `simulated=true`.
- Response log rows with details `Recorded in SIEM blocklist (tracking only)` map to `tracking_only/succeeded`, `tracking_recorded=true`.
- Notification deliveries map from `mode`, `status`, and metadata `executed`, but only explicit provider success evidence can set `external_executed=true`.
- Playbook steps map from `steps_log` `mode`, `status`, `simulated`, `executed`, and adapter result.
- Unknown legacy rows map conservatively to `simulation` or `observed` with all execution booleans false unless positive evidence exists.

Idempotency rules:

- Backfill decision rows must use deterministic `soar_correlation_id` and/or source-table idempotency keys.
- Outcome event writers must include an `idempotency_key` for retries, backfill, and worker re-entry where a duplicate event would mislead analysts.
- Re-running dry-run or write backfill must produce stable counts and must not create duplicate decisions/events.

### Decision 9: Retention and Archive Strategy

Canonical decisions and outcome events are audit/reporting data and should not be deleted during normal rollback.

Retention guidance:

- Keep recent canonical outcome events queryable for dashboard and source-IP context use.
- Archive older append-only events only through a separately approved retention policy.
- Archive must preserve decision id, SOAR correlation id, selected action, final/latest outcome, and enough related ids to answer the primary analyst question.
- Metrics should either include archived summaries or clearly document their live retention window.

## Risks / Trade-offs

- [Risk] Canonical events and existing linkage snapshots can diverge. -> Mitigation: one outcome writer, consistency tests, and read paths prefer canonical decision/event data.
- [Risk] Backfill may misclassify ambiguous historical rows. -> Mitigation: conservative defaults, `decision_source='migration'`, reason codes, dry-run counts, and safe summaries that say inferred.
- [Risk] More schema surface increases migration complexity. -> Mitigation: additive nullable columns, phased deployment, and rollback that ignores new columns/tables.
- [Risk] UI may still show old ambiguous fields during transition. -> Mitigation: shared outcome component and phased removal of direct status copy.
- [Risk] Real adapter semantics vary by provider. -> Mitigation: only mark `real/external_executed=true` when adapter returns explicit execution evidence.
- [Risk] Local tracking-only may be confused with blocking. -> Mitigation: labels must say `Tracking only`, summaries must say no enforcement occurred, and `external_executed` must remain false.
- [Risk] Append-only events can grow quickly. -> Mitigation: required indexes, latest-outcome read model, and retention/archive policy.
- [Risk] SOAR correlation ids may be missing in old records. -> Mitigation: deterministic legacy SOAR correlation ids and compatibility resolvers.

## Migration Plan

1. Add schema/tables/linkage columns with no behavior change.
2. Add canonical model, writer helpers, and latest-outcome read helpers.
3. Add compatibility resolver and backfill dry-run before broad UI migration.
4. Backfill old records conservatively after dry-run validation.
5. Dual-write decisions/events from manual, queue, playbook, approval, notification, audit, and tracking-only paths.
6. Extend APIs to include canonical outcome payloads while preserving legacy fields.
7. Update shared frontend components and individual screens.
8. Verify end-to-end traceability and compare legacy vs canonical metrics.
9. After stable use, consider de-emphasizing legacy ambiguous fields in UI.

Rollback:

- Stop writing new decisions/events.
- Revert UI/API consumers to legacy fields.
- Leave additive tables/columns in place or drop them in a separate approved rollback migration if no data retention requirement exists.
- Because existing legacy tables remain authoritative during rollout, rollback does not require reconstructing old behavior.

## Open Questions

- Should the first implementation create a SQL view for latest outcomes, or keep latest-outcome selection entirely in backend helper queries?
- Should source-IP context include all outcomes by default or only recent/high-signal outcomes?
- What production retention window should apply before canonical events are archived?
- Should blocklist manager show tracking-only provenance for all blocklist rows, including manually-created entries not tied to alerts?
