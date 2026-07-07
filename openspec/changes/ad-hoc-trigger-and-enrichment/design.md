## Executive Summary

This design adds two small capabilities to the existing playbook system: an analyst can manually create a pending execution for an enabled playbook against an existing alert or incident, and playbooks can include one read-only enrichment step that snapshots already-known context into the execution log for later steps. The design deliberately reuses `playbook_executions`, `create_and_link_playbook_execution_decision`, the worker/lease executor, approval steps, RBAC decorators, audit logging, MITRE enrichment helpers, reputation helpers, and source-IP context data. It does not add a second engine, scheduler, workflow builder, or new data source.

## Current Manual Execution Audit

- `engines/playbook_engine.py` matches enabled definitions to committed alerts only. It is read-only and does not create executions.
- `engines/soar_playbook_orchestrator.py` creates pending executions after alert commit by calling `create_pending_playbook_execution_once`, then links a canonical response decision with `decision_source="playbook"` and an initial lifecycle outcome event.
- `core/playbook_store.py` already has `create_playbook_execution(conn, playbook_id, alert_id, incident_id)` for generic pending rows and `create_pending_playbook_execution_once` for deduped alert-triggered rows. Existing uniqueness is scoped to active `(playbook_id, alert_id)` rows.
- `engines/playbook_step_executor.py` claims pending rows and processes the same execution object regardless of origin. It already supports `pending`, `running`, `awaiting_approval`, terminal states, leases, delivery tracking, approval gates, and lifecycle outcome events.
- `routes/playbook_routes.py` supports definition list/get/create/update/enable, execution list/get, retry, abandon, permanently fail, and resume. It does not expose a first-run manual execution endpoint.
- `PlaybooksPanel` exposes definitions and executions plus retry/abandon/resume controls. It does not provide "run this playbook now."
- Threat Hunt can search raw events and pivot to related alerts by source IP, but cannot launch playbooks.
- SOC Command Center aggregates incidents, executions, approvals, queue, notifications, dead letters, source-IP context, and metrics. It has operational visibility but no manual launch action.
- Incident routes expose detail/timeline/status. Incident timeline already includes playbook execution and audit context, but there is no incident-scoped launch endpoint.

## Current Enrichment Audit

- `helpers/enrichment_helpers.py` maps selected alert types to MITRE ATT&CK fields and safely extracts correlation metadata from `alerts.context`.
- `routes/alerts_events_routes.py` returns alert payloads enriched with MITRE fields, safe correlation context, stored external reputation fields, and current behavioral reputation from `get_ip_reputation`.
- `core/ip_helpers.py` contains AbuseIPDB lookup used at ingest/backfill time (`lookup_ip_reputation`) and internal behavioral scoring (`get_ip_reputation`). Playbook execution should not call AbuseIPDB directly; it should use stored alert snapshots plus internal scoring.
- `routes/source_ip_context_routes.py` already aggregates alerts, incidents, queue rows, blocklist entries, behavioral reputation, external reputation snapshots, linked playbook executions, and response outcomes for a validated source IP.
- Existing alert context includes `source`, `source_type`, geolocation (`country`, `city`, `latitude`, `longitude`), response action/status, reputation snapshot fields, and JSON `context` for correlation metadata.
- No reusable playbook enrichment action exists in `KNOWN_PLAYBOOK_ACTIONS`; current actions are `monitor`, `flag_high_priority`, `require_approval`, notifications, and `block_ip`.

## Proposed Manual Trigger Model

Manual launch should be a normal execution creation path, not a separate orchestration path. Add a future endpoint shaped like `POST /playbooks/<playbook_id>/executions` with body containing exactly one target: `alert_id` or `incident_id`. It validates that the playbook exists and is enabled, the target exists, and the user is authenticated with analyst or super-admin access.

Launch locations should be limited to places with an explicit selected target:
- Alert detail/action surface: primary v1 location for `alert_id`.
- Incident detail or incident timeline: primary v1 location for `incident_id`.
- Threat Hunt expanded event: only as a pivot to related alerts or a manual launch dialog that requires selecting a concrete alert; raw events alone are not valid targets.
- SOC Command Center: only from an existing incident/execution/source-IP context row that resolves to a concrete alert or incident.
- PlaybooksPanel: optional management-surface launch form for super-admin/analyst users who provide an existing alert or incident ID.

Manual launch itself should not require approval. Approval remains a playbook step concern: if the selected playbook contains `require_approval`, the existing approval flow pauses later steps. Manual executions should create ordinary `playbook_executions` rows with `status="pending"` and be processed by the same worker. They should be distinguishable through canonical outcome metadata such as `trigger_type="manual"`, `manual_actor_username`, `manual_actor_role`, `target_type`, and `target_id`; audit logs should record the same actor and target details. If existing metadata is enough, no schema change is needed.

## Proposed Enrichment Step

Add a new read-only action, for example `enrich_context`, to the playbook action registry. It performs local reads only and writes its result into that step's `steps_log` output for downstream step binding once binding supports enrichment/prior-step fields.

The enrichment output should include only existing information:
- `target`: `alert_id`, `incident_id`, `source_ip`, `target_type`.
- `alert`: core alert fields when an alert is available: type, severity, status, message, source/source_type, geolocation, response action/status, created time.
- `mitre`: values from `enrich_alert_with_mitre`.
- `correlation`: values from `enrich_alert_with_correlation_context` / safe correlation context.
- `reputation`: stored external snapshot fields from alerts, latest external snapshot from source-IP context when available, and current internal behavioral reputation from `get_ip_reputation`.
- `related_alerts`: bounded recent alerts for the same source IP.
- `historical_detections`: counts or bounded recent alert-type history from existing alerts, not a new detector.
- `previous_incidents`: bounded incidents directly tied to the source IP or linked alerts.
- `source_ip_context`: a compact subset of the existing source-IP context sections, not a second divergent aggregator.
- `playbook_executions`: bounded recent linked executions.
- `usernames`: only if already present in existing event/alert context fields; do not infer or invent identity enrichment.

Do not introduce new network calls, new AbuseIPDB lookups, new geolocation lookups, new telemetry sources, evidence persistence, or long-lived enrichment tables. Downstream steps should see a deterministic JSON object in the execution step output; if parameter binding later exposes prior-step output, it can reference this object without redefining enrichment.

## Execution Flow

1. Analyst selects an enabled playbook and an existing alert or incident from an authorized UI surface.
2. API validates RBAC, playbook enabled state, target existence, and exactly-one-target input.
3. API creates a pending `playbook_executions` row through existing store primitives. For alert targets, implementation may use active-execution dedupe; for incident-only targets, dedupe should be explicit and conservative.
4. API calls `create_and_link_playbook_execution_decision` with initial event type `manual_triggered`, `execution_actor="manual"` or metadata indicating manual actor, and safe metadata identifying trigger type and user.
5. API writes an audit event such as `PLAYBOOK_EXECUTION_MANUAL_TRIGGER`.
6. Existing worker claims the pending row and processes steps normally.
7. If the playbook includes `enrich_context`, the step reads existing local context and appends sanitized enrichment output to `steps_log`.
8. Later steps and approvals continue through current executor behavior.

## Validation Rules

- Request body must be JSON.
- `playbook_id` must resolve to an enabled definition; disabled playbooks cannot be manually launched by analysts.
- Exactly one of `alert_id` or `incident_id` is required.
- Alert targets must exist. Incident targets must exist.
- Raw threat-hunt events are not valid execution targets unless resolved to an existing alert or incident first.
- Manual launch must reject or no-op on duplicate active execution for the same playbook and target according to the existing active-execution semantics; do not create unbounded duplicates.
- `enrich_context` accepts only optional bounded flags/limits; limits are capped and must not trigger external calls.
- Enrichment output must be JSON-serializable, bounded, and sanitized like existing API payloads.

## Security / RBAC

Manual launch should require authenticated analyst or super-admin access because it can start notification, approval, and simulated containment workflows. Definition authoring remains super-admin only. Approval decisions remain super-admin only through the existing approval system. The enrichment step performs local reads already available to analyst/super-admin views and must not expose fields beyond those users can already access through existing alert, incident, playbook, and source-IP context APIs.

## Audit Logging

Every successful manual launch must write an audit event with actor username, actor role, HTTP method/path, source IP, playbook ID, execution ID, target type, alert ID or incident ID, and trigger type `manual`. Rejections for permission failures use existing auth behavior. Canonical response outcome metadata should also mark the execution as manual so execution timelines can distinguish it from automatic post-commit alert matches.

## Alternatives Considered

- Duplicate manual execution engine: rejected because the worker already processes pending execution rows.
- Scheduler-style ad hoc job queue: rejected because this is immediate analyst action, not scheduled automation.
- Manual approval before any playbook starts: rejected because existing `require_approval` steps already model risky actions; adding launch approval would double-gate benign investigation playbooks.
- Direct AbuseIPDB lookup in enrichment: rejected because AbuseIPDB already feeds stored alert reputation and backfill; playbook enrichment must be read-only and deterministic.
- New enrichment persistence table: rejected for this child spec; `steps_log` is enough for downstream step context and visibility.

## Implementation Scope

Future implementation scope is intentionally small:
- Add one manual execution API endpoint and tests.
- Reuse `playbook_executions`, canonical outcome linkage, audit logging, and existing worker processing.
- Add one registry action for read-only enrichment and executor handling for that action.
- Extract or reuse source-IP context query helpers to avoid duplicating aggregation logic.
- Add minimal UI actions/dialogs on selected alert and incident surfaces, with Threat Hunt and SOC Command Center using only concrete alert/incident targets.
- Add frontend service wrapper and focused component tests.

## Non-goals

- Playbook chaining.
- Evidence persistence.
- Scheduler.
- UI redesign.
- New playbooks.
- Branching redesign.
- Schema redesign unless implementation proves metadata cannot safely distinguish manual executions.
- Deployment.
- New dependencies.
- New external enrichment sources.
- New AbuseIPDB/geolocation calls from playbook execution.

## Risks

- Enrichment output can grow large. Mitigation: use bounded recent collections and compact summaries.
- Manual launch can create noise. Mitigation: require concrete target, enabled playbook, RBAC, audit, and active-execution dedupe.
- Incident-only execution may lack alert fields. Mitigation: enrichment should return target-aware nulls and related linked alerts rather than failing unless a playbook requires alert-only fields.
- Duplicating source-IP context logic could drift. Mitigation: extract reusable helpers or call shared helper functions rather than reimplementing route-private SQL in the executor.

## Acceptance Criteria

- Analysts and super-admins can manually create a pending execution for an enabled playbook against an existing alert or incident.
- Manual executions appear through the existing execution list/detail APIs and are processed by the existing worker.
- Manual executions are distinguishable from automatic executions in canonical outcome metadata and audit logs.
- Manual launch does not bypass existing `require_approval` gates.
- Unauthorized users cannot launch playbooks.
- `enrich_context` is accepted by definition validation and produces bounded, read-only enrichment output from existing local sources.
- Enrichment includes no new external calls and no new sources.
- No duplicate engine, scheduler, branching, chaining, workflow builder, or new dependency is introduced.

## Validation Plan

- API tests for manual launch success, disabled playbook rejection, missing/invalid target rejection, exactly-one-target validation, duplicate active execution behavior, and RBAC.
- Store/orchestrator tests proving the created execution is a normal pending row with canonical linkage and manual metadata.
- Executor tests proving `enrich_context` emits bounded output, handles alert and incident targets, uses existing MITRE/reputation/correlation/source-IP context sources, and performs no external calls.
- Audit tests proving successful manual launch records actor and target details.
- Frontend tests for launch affordances only on authorized, concrete alert/incident targets.
- Regression tests for existing automatic trigger matching and existing retry/abandon/resume behavior.

## Overall Assessment

This is a natural extension of the current architecture. Manual launch should be a thin authenticated creation path into the existing execution pipeline, and enrichment should be one read-only step that reuses context the product already calculates. The design is small enough to deliver without schema redesign, scheduler work, or orchestration changes, while unblocking analyst-initiated playbook use and giving future playbooks reusable context.
