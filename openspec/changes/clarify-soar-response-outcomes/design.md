## Context

The current SIEM/SOAR records related facts across several independent surfaces:

- Detection creates `alerts` with `response_action` and `response_status`.
- Ingest post-processing creates `response_actions_queue` rows, incidents, and pending `playbook_executions`.
- The legacy queue worker writes terminal rows to `response_actions_log`.
- Playbook workers record step outcomes inside `playbook_executions.steps_log`.
- Approval gates use `approval_requests` and `approval_request_events`.
- Notification adapters write `notification_delivery_attempts`, including mode and provider outcome.
- Manual alert actions can write `response_actions_log` and, for `block_ip`, create a tracking-only `blocked_ips` row.

These records are individually useful, but they do not share a canonical outcome model. In particular, `executed` is overloaded: a simulated queue action can be logged as `executed`, a tracking-only blocklist insert is not external enforcement, and real notification delivery is only visible in notification-specific records.

The design must preserve simulation mode, existing detection semantics, approval workflows, playbook behavior, source-IP context contracts, and current records. It should introduce a durable answer to the primary analyst question:

> What happened, what response was selected, what playbook ran, and was anything actually executed?

## Goals / Non-Goals

**Goals:**

- Define canonical outcome language for observed-only, simulated, tracking-only, real-executed, failed, blocked, awaiting-approval, and skipped states.
- Make manual actions, queue actions, playbook steps, approvals, adapter deliveries, source-IP context, SOC Command Center, Alert Details, SOAR Queue, Playbooks Panel, Attack Map popup, and Blocklist Manager use the same vocabulary.
- Add a durable decision/outcome model that links alert, queue, playbook, approval, adapter delivery, response log, incident, and UI summaries through a safe `correlation_id`.
- Preserve old records and provide explicit compatibility/backfill semantics.
- Avoid vague UI labels. Any use of "executed" must say whether it was simulated, tracking-only, or real.
- Allow phased implementation across multiple sessions with verifiable checkpoints.

**Non-Goals:**

- Do not remove simulation mode.
- Do not make simulated actions look real.
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
executed: boolean
decision_source: detection_default | correlation | playbook | queue_worker | manual | approval | adapter | migration
outcome_summary: text
correlation_id: safe shared string
```

Rationale:

- `execution_mode` answers what class of action occurred.
- `execution_state` answers where it is in the lifecycle.
- `executed` answers whether anything actually happened beyond observation.
- `decision_source` explains why or who selected the response.
- `outcome_summary` gives analyst-readable context.
- `correlation_id` ties distributed records together.

Alternatives considered:

- Only infer from existing table statuses. Rejected because existing statuses are ambiguous and inconsistent.
- Only add UI formatting rules. Rejected because backend APIs would still return ambiguous data and historical compatibility would be fragile.
- Add separate enum sets per subsystem. Rejected because it preserves the current fragmentation.

### Decision 2: Add a Durable Outcome Ledger

Introduce a new additive table, proposed as `soar_response_outcomes`, as the clean source of truth for normalized response lifecycle facts.

Suggested columns:

```text
id SERIAL PRIMARY KEY
correlation_id VARCHAR(128) NOT NULL
parent_correlation_id VARCHAR(128)
alert_id INTEGER REFERENCES alerts(id) ON DELETE SET NULL
incident_id INTEGER REFERENCES incidents(id) ON DELETE SET NULL
queue_id INTEGER REFERENCES response_actions_queue(id) ON DELETE SET NULL
response_log_id INTEGER REFERENCES response_actions_log(id) ON DELETE SET NULL
playbook_id VARCHAR(64) REFERENCES playbook_definitions(id) ON DELETE SET NULL
playbook_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL
playbook_step_index INTEGER
approval_request_id INTEGER REFERENCES approval_requests(id) ON DELETE SET NULL
notification_delivery_attempt_id INTEGER REFERENCES notification_delivery_attempts(id) ON DELETE SET NULL
blocked_ip_id INTEGER REFERENCES blocked_ips(id) ON DELETE SET NULL
source_ip INET
selected_action TEXT
decision_source VARCHAR(64) NOT NULL
execution_mode VARCHAR(32) NOT NULL
execution_state VARCHAR(32) NOT NULL
executed BOOLEAN NOT NULL DEFAULT FALSE
outcome_summary TEXT NOT NULL
reason_code VARCHAR(128)
actor_user_id INTEGER REFERENCES users(id) ON DELETE SET NULL
provider VARCHAR(64)
adapter_name VARCHAR(64)
external_reference TEXT
safe_metadata JSONB NOT NULL DEFAULT '{}'::jsonb
observed_at TIMESTAMPTZ
selected_at TIMESTAMPTZ
queued_at TIMESTAMPTZ
started_at TIMESTAMPTZ
completed_at TIMESTAMPTZ
created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
```

Constraints:

- `execution_mode IN ('observed', 'simulation', 'tracking_only', 'real')`
- `execution_state IN ('observed', 'selected', 'queued', 'awaiting_approval', 'running', 'skipped', 'blocked', 'succeeded', 'failed')`
- `decision_source IN ('detection_default', 'correlation', 'playbook', 'queue_worker', 'manual', 'approval', 'adapter', 'migration')`
- `executed = TRUE` only when `execution_mode IN ('tracking_only', 'real')` and `execution_state = 'succeeded'`
- `execution_mode = 'observed'` requires `executed = FALSE`
- `execution_mode = 'simulation'` requires `executed = FALSE`

Indexes:

- `correlation_id`
- `alert_id, created_at DESC`
- `incident_id, created_at DESC`
- `source_ip, created_at DESC`
- `queue_id`
- `playbook_execution_id, playbook_step_index`
- `approval_request_id`
- `notification_delivery_attempt_id`
- `execution_mode, execution_state, created_at DESC`

Rationale:

- A ledger avoids overloading existing tables and keeps future UI/API contracts simple.
- Additive schema minimizes rollback risk.
- Existing tables can be extended with nullable `correlation_id` fields for direct linkage without making the ledger impossible to roll back.

Alternatives considered:

- Only extend each existing table. Rejected because every UI would still have to merge subsystem-specific semantics.
- Replace `response_actions_log`. Rejected because existing audit behavior and historical rows must remain readable.
- Store outcomes only in JSON. Rejected because queryability, metrics, and migration verification need indexed fields.

### Decision 3: Extend Existing Tables Safely

Use additive nullable columns where they reduce ambiguity or improve joins:

- `alerts`: `correlation_id`, `response_outcome_id`, optional normalized snapshot fields for fast list rendering.
- `response_actions_queue`: `correlation_id`, `execution_mode`, `decision_source`.
- `response_actions_log`: `correlation_id`, `execution_mode`, `execution_state`, `executed`, `outcome_id`.
- `playbook_executions`: `correlation_id`.
- `approval_requests`: `correlation_id`.
- `notification_delivery_attempts`: already has `correlation_id`; add `outcome_id` only if useful.
- `blocked_ips`: `correlation_id`, `outcome_id`, `tracking_only BOOLEAN DEFAULT TRUE` if blocklist tracking needs explicit display.

Rationale:

- The ledger remains canonical, but direct columns support simple reads, backfill verification, and safer incremental UI migration.

Tradeoff:

- Some denormalization is introduced. Mitigation: outcome writer helpers own writes and tests verify consistency.

### Decision 4: Centralize Outcome Writing

Add backend helpers in a future implementation, such as `core/soar_response_outcome_store.py` and `core/soar_response_outcome_model.py`.

Responsibilities:

- Validate enums.
- Generate or propagate `correlation_id`.
- Sanitize metadata.
- Write/append outcome rows.
- Produce API serialization shape.
- Provide compatibility wrappers for older rows.

Rationale:

- Manual action, queue worker, playbook worker, approval routes, notification delivery, blocklist manager, and source-IP context must not each invent outcome language.

### Decision 5: Correlation ID Strategy

Use a safe string generated at first response selection, then propagate:

```text
soar-{alert_id or none}-{short_uuid}
```

Rules:

- Detection-created alert with selected default response starts a correlation id.
- Queue rows inherit alert correlation id.
- Playbook executions inherit alert correlation id, but step-level outcomes may use child ids with `parent_correlation_id`.
- Approval requests inherit the playbook/queue correlation id.
- Notification delivery attempts include their delivery-specific id but link to the parent SOAR correlation id in metadata or `parent_correlation_id`.
- Manual alert actions create a new correlation id if none exists, or a child id if a prior outcome exists.
- Backfilled legacy records use deterministic `legacy-{table}-{id}` correlation ids and `decision_source='migration'`.

Rationale:

- One shared id makes cross-view explanation possible without embedding secrets or provider ids.

### Decision 6: API Contract Shape

Every response outcome returned to the UI should include:

```json
{
  "correlation_id": "soar-123-...",
  "selected_action": "block_ip",
  "decision_source": "manual",
  "execution_mode": "tracking_only",
  "execution_state": "succeeded",
  "executed": true,
  "outcome_summary": "Recorded IP in SIEM blocklist only; no firewall enforcement occurred.",
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
    "observed_at": "...",
    "selected_at": "...",
    "queued_at": null,
    "started_at": "...",
    "completed_at": "..."
  }
}
```

Affected APIs should expose either `response_outcome` for one canonical latest row or `response_outcomes` for timelines/lists. Existing fields should remain during migration.

### Decision 7: UI Language

Use these labels:

- `Observed only`: detection exists; no response selected or executed.
- `Simulated`: response ran in simulation; no real provider/local enforcement action occurred.
- `Tracking only`: internal SIEM state changed, such as blocklist tracking; no firewall/provider enforcement occurred.
- `Real executed`: external provider/local enforcement action actually occurred.
- `Awaiting approval`: selected action is paused for human approval.
- `Blocked by approval`: approval denied or expired prevented the action.
- `Skipped`: no action was attempted due to validation, duplicate prevention, unsupported action, protected target, or operator-abandoned flow.
- `Failed`: action was attempted or prepared but failed according to the canonical state.

Avoid standalone `executed` in UI copy. Use phrases like `Simulated succeeded`, `Tracking-only recorded`, or `Real executed`.

### Decision 8: Backfill and Compatibility

Backfill is additive:

- Alerts with no response fields produce `observed/observed/executed=false`.
- Alerts with `response_action` but no queue/log produce `simulation/selected/executed=false` unless evidence proves tracking-only or real.
- Queue rows map current status to canonical state.
- Response log rows with details `Simulated ...` map to `simulation/succeeded/executed=false`.
- Response log rows with details `Recorded in SIEM blocklist (tracking only)` map to `tracking_only/succeeded/executed=true`.
- Notification deliveries map from `mode`, `status`, and metadata `executed`.
- Playbook steps map from `steps_log` `mode`, `status`, `simulated`, `executed`, and adapter result.
- Unknown legacy rows map conservatively to `simulation` or `observed` with `executed=false` unless positive evidence exists.

Compatibility APIs must continue returning current fields until the UI fully consumes canonical outcomes.

## Risks / Trade-offs

- [Risk] Ledger and existing table snapshots can diverge. -> Mitigation: one outcome writer, consistency tests, and read paths prefer ledger.
- [Risk] Backfill may misclassify ambiguous historical rows. -> Mitigation: conservative defaults, `decision_source='migration'`, `reason_code`, and safe summaries that say inferred.
- [Risk] More schema surface increases migration complexity. -> Mitigation: additive nullable columns, phased deployment, and rollback that ignores new columns/table.
- [Risk] UI may still show old ambiguous fields during transition. -> Mitigation: shared outcome component and phased removal of direct status copy.
- [Risk] Real adapter semantics vary by provider. -> Mitigation: only mark `real/executed=true` when adapter returns explicit executed evidence.
- [Risk] Local tracking-only may be confused with blocking. -> Mitigation: labels must say `Tracking only` and summaries must say no firewall enforcement occurred.
- [Risk] Correlation IDs may be missing in old records. -> Mitigation: deterministic legacy correlation ids and compatibility resolvers.

## Migration Plan

1. Add schema/table/columns with no behavior change.
2. Add canonical model and writer helpers.
3. Backfill old records conservatively.
4. Dual-write outcomes from manual, queue, playbook, approval, notification, and tracking-only paths.
5. Extend APIs to include canonical outcome payloads while preserving legacy fields.
6. Update shared frontend components and individual screens.
7. Verify end-to-end traceability and compare legacy vs canonical metrics.
8. After stable use, consider de-emphasizing legacy ambiguous fields in UI.

Rollback:

- Stop writing new outcome rows.
- Revert UI/API consumers to legacy fields.
- Leave additive table/columns in place or drop them in a separate approved rollback migration if no data retention requirement exists.
- Because existing legacy tables remain authoritative during rollout, rollback does not require reconstructing old behavior.

## Open Questions

- Should `tracking_only` count as `executed=true` because internal SIEM state changed, or should a second field such as `external_executed` be added? This design uses `executed=true` for tracking-only successful state and requires UI to say tracking-only.
- Should the first implementation add normalized snapshot fields to `alerts`, or rely entirely on ledger joins?
- Should blocklist manager show tracking-only provenance for all blocklist rows, including manually-created entries not tied to alerts?
- Should source-IP context include all outcomes by default or only recent/high-signal outcomes?
- How long should canonical outcome ledger rows be retained before archive policy is needed?
