## 0. Phase 0 - Audit Confirmation

- [ ] 0.1 Re-read `schema.sql` and migrations for `alerts`, `response_actions_queue`, `response_actions_log`, `playbook_definitions`, `playbook_executions`, `approval_requests`, `approval_request_events`, `notification_delivery_attempts`, `incidents`, `incident_alerts`, `blocked_ips`, and `audit_log`.
- [ ] 0.2 Re-read ingest routes to confirm all post-commit paths that create queue actions, incidents, and playbook executions.
- [ ] 0.3 Re-read manual alert action route and confirm current tracking-only blocklist behavior.
- [ ] 0.4 Re-read `engines/soar_action_worker.py` and `engines/soar_executor.py` to confirm queue action states and simulation behavior.
- [ ] 0.5 Re-read `engines/playbook_step_executor.py` to confirm playbook step mode, approval gate, and notification delivery behavior.
- [ ] 0.6 Re-read integration adapters to confirm which adapters are real-capable and which remain simulation/dry-run only.
- [ ] 0.7 Re-read source-IP context, SOC Command Center, SOAR Queue, Approval Requests, Playbooks Panel, Alert Details, Attack Map, and Blocklist Manager UI data dependencies.
- [ ] 0.8 Document any divergence between the current audit and this spec before implementing schema.
- [ ] 0.9 Confirm no implementation phase will delete simulation mode, relabel simulated work as real, or treat tracking-only state as real execution.

## 1. Phase 1 - Data Model and Schema Migration

- [x] 1.1 Draft migration for additive `soar_response_decisions` table with SOAR correlation id, related alert/incident/playbook/queue/approval ids, source IP, selected action, decision source, actor user, reason code, safe metadata, and timestamps.
- [x] 1.2 Draft migration for additive append-only `soar_response_outcome_events` table with decision linkage, SOAR correlation id, related entity ids, execution mode/state, `external_executed`, `tracking_recorded`, `simulated`, execution actor, summary, reason code, provider/adapter fields, idempotency key, safe metadata, and timestamps.
- [x] 1.3 Add database constraints for allowed `execution_mode` values: `observed`, `simulation`, `tracking_only`, `real`.
- [x] 1.4 Add database constraints for allowed `execution_state` values: `observed`, `selected`, `queued`, `awaiting_approval`, `running`, `skipped`, `blocked`, `succeeded`, `failed`.
- [x] 1.5 Add database constraints for allowed `decision_source` values: `detection_default`, `correlation`, `playbook`, `manual`, `migration`.
- [x] 1.6 Add database constraints for allowed `execution_actor` values: `queue_worker`, `playbook_worker`, `adapter`, `approval_service`, `manual`, `system`.
- [x] 1.7 Add database constraints for canonical reason codes: `approval_required`, `approval_denied`, `simulation_mode`, `tracking_only`, `adapter_unavailable`, `provider_error`, `policy_blocked`, `duplicate_suppressed`, `unsupported_action`.
- [x] 1.8 Add boolean compatibility constraints: only `real/succeeded` may set `external_executed=true`; only `tracking_only/succeeded` may set `tracking_recorded=true`; only `simulation` may set `simulated=true`; `observed` must set all three false.
- [x] 1.9 Add required indexes for `alert_id`, `incident_id`, `source_ip`, `soar_correlation_id`, `decision_id`, and `created_at`.
- [x] 1.10 Add secondary indexes for queue id, playbook execution/step, approval request, notification delivery, mode/state/time, and idempotency keys where useful.
- [x] 1.11 Implement nullable `soar_correlation_id` and `decision_id` linkage columns on legacy SOAR tables; defer `latest_outcome_event_id` to a later phase to avoid circular migration dependencies.
- [x] 1.12 Avoid adding duplicated canonical outcome fields to legacy tables unless they are explicitly documented as snapshot-only.
- [x] 1.13 Update schema snapshot after migration.
- [x] 1.14 Run schema validation script and record validation output.
- [x] 1.15 Add migration tests for constraints, indexes, linkage fields, idempotency uniqueness, and additive compatibility.

## 2. Phase 2 - Backend Outcome Writer and Read Model Helpers

- [x] 2.1 Create canonical enum/constants module for execution modes, execution states, decision sources, execution actors, reason codes, and UI labels.
- [x] 2.2 Create decision model validation helper for selected action, decision source, actor user, SOAR correlation id safety, and safe metadata.
- [x] 2.3 Create outcome event validation helper for enum compatibility and `external_executed`/`tracking_recorded`/`simulated` boolean rules.
- [x] 2.4 Create safe metadata sanitizer that rejects or redacts secrets, URLs, tokens, raw payloads, raw provider responses, raw headers, and unsafe exception strings.
- [x] 2.5 Create SOAR correlation id generator for new response lifecycles.
- [x] 2.6 Create deterministic legacy SOAR correlation id helper for migration/backfill.
- [x] 2.7 Create decision writer helper that inserts or finds canonical decision rows.
- [x] 2.8 Create append-only outcome event writer helper with idempotency-key support.
- [x] 2.9 Create latest-outcome read helper by decision id, alert id, source IP, incident id, queue id, playbook execution id, approval request id, notification delivery id, and SOAR correlation id.
- [x] 2.10 Create compatibility resolver that infers canonical latest outcome payloads when no decision/event row exists.
- [x] 2.11 Add unit tests for valid and invalid decision writes.
- [x] 2.12 Add unit tests for valid and invalid outcome event writes.
- [x] 2.13 Add unit tests for metadata redaction and SOAR correlation id safety.
- [x] 2.14 Add unit tests for latest-outcome ordering and read-model defaults when no events exist.

## 3. Phase 3 - Backfill Dry-Run and Compatibility Verification

- [x] 3.1 Implement dry-run scanner for observed-only alert outcomes without writing canonical rows.
- [x] 3.2 Implement dry-run scanner for existing queue rows by status.
- [x] 3.3 Implement dry-run scanner for existing response action log rows, including simulation and tracking-only inference.
- [x] 3.4 Implement dry-run scanner for existing playbook executions and `steps_log` entries.
- [x] 3.5 Implement dry-run scanner for existing approval requests and approval request events.
- [x] 3.6 Implement dry-run scanner for existing notification delivery attempts.
- [x] 3.7 Implement dry-run scanner for existing blocklist rows where source alert linkage exists.
- [x] 3.8 Report dry-run counts by source table, decision source, execution mode/state, reason code, `external_executed`, `tracking_recorded`, and `simulated`.
- [x] 3.9 Add compatibility resolver tests proving old records can answer the primary analyst question before broad UI migration.
- [x] 3.10 Add idempotency checks proving repeated dry-run and later write-mode backfill cannot create duplicate decisions/events.
- [x] 3.11 Review dry-run output against representative local data and update mapping rules before enabling write-mode backfill.
- [ ] 3.12 Verify notification real-execution compatibility remains conservative: `execution_mode=real`, delivery `status=success`, metadata `executed=true`, metadata `simulated=false`, and provider success evidence are all required before inferring `external_executed=true`.

## 4. Phase 4 - Queue and Response Log Normalization

- [x] 4.1 Update `response_actions_log` writer linkage first: accept `decision_id` and `soar_correlation_id`, write them to the legacy log row where schema allows, and return the inserted log id so terminal canonical outcome events can reference `response_action_log_id`.
- [x] 4.2 Update queue row helpers to read and return `decision_id` and `soar_correlation_id` for `get`, list, claim, approval-skip, success, skipped, failed, requeue, and stale-recovery paths without changing existing queue status transitions.
- [x] 4.3 Update alert ingest post-commit enqueue path to assign or propagate a SOAR correlation id for selected detection/correlation responses.
- [x] 4.4 Create canonical decision rows when detection, correlation, or queue creation selects a response action, and link the inserted queue row to `decision_id` and `soar_correlation_id`.
- [x] 4.5 Make queue decision/event creation idempotent around `response_actions_queue` `ON CONFLICT DO NOTHING`: duplicate queue inserts MUST NOT create duplicate canonical decisions/events, and queued/duplicate-suppressed events MUST use deterministic idempotency keys when written.
- [x] 4.6 Append `queued` outcome events when durable `response_actions_queue` rows are created; use `selected` only when a response is selected but no durable queue row exists.
- [x] 4.7 Update queue worker claim path to append `running` outcome events in the same transaction as the `pending` or approved `awaiting_approval` to `running` claim, before preserving the existing early-claim commit behavior.
- [x] 4.8 Make `running` event writes safe across worker restarts by using deterministic idempotency keys tied to queue id, claim attempt/retry context, and state transition so re-entry cannot create misleading duplicate running events.
- [x] 4.9 Update queue approval-required path to append `awaiting_approval` events linked to queue and approval request when an approval request is created or reused.
- [x] 4.10 Update queue approval-denied/expired path to append `blocked` events with `reason_code=approval_denied` and no execution booleans set; the summary MUST distinguish denied from expired even though both map to the canonical approval-denied reason code.
- [x] 4.11 Update queue simulation success path to append `simulation/succeeded`, `simulated=true`, `external_executed=false`, and `tracking_recorded=false`, and link the event to the returned `response_action_log_id`.
- [x] 4.12 Update queue skipped path to append `skipped` events with canonical reason-code mapping and sanitized summaries.
- [x] 4.13 Update retry behavior to append failed-attempt outcome events for retryable failures, append queued/requeued events when work is returned to `pending`, and append terminal failed events when retries are exhausted.
- [x] 4.14 Update queue failed path for non-retryable failures to append `failed` events with sanitized error summaries and linked response log ids where a terminal log row is written.
- [x] 4.15 Define and apply canonical reason-code mapping for existing worker reasons: approval required/pending, approval denied/expired, protected target and validation failures, unsupported action, adapter unavailable/timeout/provider errors, duplicate suppression, simulation mode, and tracking-only outcomes.
- [x] 4.16 Update manual `/alerts/<id>/execute` path to create decisions/events for manual monitor, escalation, simulation, and tracking-only blocklist recording.
- [x] 4.17 Ensure manual tracking-only `block_ip` only records SIEM blocklist tracking after durable blocklist insertion, sets `tracking_recorded=true`, `external_executed=false`, `simulated=false`, and explicitly says no firewall, provider, external, or local enforcement occurred.
- [x] 4.18 Explicitly defer `blocked_ips.decision_id`, `blocked_ips.soar_correlation_id`, and outcome `blocked_ip_id` linkage unless a new additive migration is approved; Phase 4 MAY link tracking-only manual outcomes through `alert_id`, `source_ip`, `decision_id`, `soar_correlation_id`, and `response_action_log_id`.
- [x] 4.19 Add focused tests in implementation order: log writer linkage, queue helper linkage, enqueue decision plus queued event idempotency, worker running event/early-claim safety, worker terminal events/log linkage including retry paths, and manual route tracking-only/simulation events.

## 5. Phase 5 - Playbook, Approval, Notification, Audit, and Backfill Write Integration

### 5A. Phase 5A Schema Migration (approved)

- [x] 5A.1 Add nullable `decision_id INTEGER REFERENCES soar_response_decisions(id) ON DELETE SET NULL` to `playbook_executions`.
- [x] 5A.2 Add nullable `soar_correlation_id VARCHAR(128)` to `playbook_executions`.
- [x] 5A.3 Update schema snapshot after migration.
- [x] 5A.4 Run schema validation and record output.

### 5B. Phase 5 Runtime Integration

- [x] 5.1 Propagate alert SOAR correlation id into newly-created `playbook_executions`; write it to `playbook_executions.soar_correlation_id` once the Phase 5A migration is applied.
- [x] 5.2 Create one execution-level canonical decision per `playbook_execution` with `decision_source=playbook`; write `decision_id` back to `playbook_executions.decision_id`. Do NOT create per-step child decisions in Phase 5. All step outcome events attach to this single execution-level decision. Per-step child decisions are deferred and must not be implemented unless a future OpenSpec explicitly approves them.
- [x] 5.3 Append outcome events when a playbook execution is created, claimed, completed, failed, abandoned, resumed, retried, or permanently failed; link all events to the execution-level decision.
- [x] 5.4 Append step outcome events for playbook steps using step index and selected action; attach all step events to the execution-level decision, not to per-step child decisions.
- [x] 5.5 Resolve `source_ip` for playbook outcome events from the related `alerts` row when `alert_id` exists; set `source_ip=NULL` when no alert is linked; do not derive `source_ip` from playbook wrapper state, `steps_log`, or indirect paths.
- [x] 5.6 Default `execution_mode=simulation` for Phase 5 playbook outcome events unless verified adapter metadata explicitly confirms real execution AND safety guards allow real mode; do not set `execution_mode=real` or `external_executed=true` from playbook wrapper `mode` state alone.
- [x] 5.7 Append `awaiting_approval` events when a playbook `require_approval` step pauses execution.
- [x] 5.8 Append `blocked` events when playbook approvals are denied or expired.
- [x] 5.9 Append approval decision events for `approval_requests` and `approval_request_events` using `execution_actor=approval_service`.
- [x] 5.10 Link approval outcomes to queue rows or playbook execution rows as applicable.
- [x] 5.11 Map `notification_delivery_attempts.mode`, `status`, and metadata into canonical outcome events.
- [x] 5.12 Ensure real notification delivery only uses `execution_mode=real` and `external_executed=true` when adapter result explicitly confirms real execution.
- [x] 5.13 Ensure failed-closed real-capable adapter results do not set `external_executed=true`.
- [x] 5.14 Ensure firewall playbook adapter outcomes remain simulation/dry-run unless a future approved OpenSpec changes that.
- [x] 5.15 Link relevant `audit_log` rows to SOAR correlation, decision, and latest outcome event where useful.
- [x] 5.16 Implement write-mode backfill as an idempotent operator script (not a migration and not an admin endpoint); dry-run output must be reviewed and approved before write mode is invoked; deterministic idempotency keys must prevent duplicate decisions/events on re-run.
- [x] 5.17 Add tests covering playbook execution-level decision creation, step event attachment to execution-level decision, source_ip resolution from alert, execution_mode simulation default, approval pending, approval denied, approval expired, notification simulation, notification real success, notification blocked, notification timeout, audit linkage, and write-mode backfill idempotency.

## 6. Phase 6 - Backend API Contract Updates

Delegation note: Phase 6 backend API contract work was implemented and verified by child change `add-response-outcome-backend-apis`.

- [x] 6.1 Add canonical latest-outcome serializer helpers: (a) `serialize_latest_outcome(conn, ...)` returning the Decision 6 shape — `outcome_summary` must be sourced from the latest outcome event row (`soar_response_outcome_events.outcome_summary`), not from `soar_response_decisions.decision_summary`; fields: `soar_correlation_id`, `decision_id`, `latest_outcome_event_id`, selected action, decision source, execution actor, execution mode/state, `external_executed`, `tracking_recorded`, `simulated`, summary, reason code, related ids, and timestamps; (b) `get_latest_outcomes_for_alerts_bulk(conn, alert_ids)` issuing a single `WHERE alert_id = ANY(%s)` query and returning `dict[int, dict]` — this helper is required before alert list APIs are updated to avoid N+1 queries; (c) outcome timeline serializer is task 6.2. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.2 Add outcome timeline serializer for ordered decision/outcome-event history. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.3 Update alert list/detail APIs to include `response_outcome`; use `get_latest_outcomes_for_alerts_bulk` (from 6.1) for the list path to avoid N+1 queries; preserve legacy `response_action`/`response_status`; always include the `response_outcome` key — return `response_outcome: null` when no canonical outcome exists (never omit the key). Completed before and confirmed by child change `add-response-outcome-backend-apis`.
- [x] 6.4 Update response log API to include canonical outcome links and latest outcome where available. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.5 Update SOAR Queue status/list/detail APIs to include canonical latest outcomes and related approval/playbook/log ids. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.6 Update Playbooks APIs to include execution-level and step-level canonical outcome payloads. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.7 Update Approval APIs to include canonical outcomes for approval requests and decisions. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.8 Update Notification Delivery APIs to include canonical mode/state and execution booleans derived from delivery status, mode, and adapter result metadata. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.9 Update Incident APIs and incident timeline to include canonical outcome events without mutating incident state. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.10 Update Source-IP Context API to include recent canonical outcomes grouped by mode/state and execution booleans. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.11 There is no dedicated SOC Command Center backend route. Add canonical outcome summary fields (counts by execution mode/state and execution booleans) to the existing `metrics_routes.py` endpoints the SOC Command Center frontend aggregates from: `GET /metrics/playbooks`, `GET /metrics/notifications`, `GET /metrics/incidents`, and `GET /metrics/approvals`. Do not create a new route. Existing fields in all four endpoints must remain. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.12 Update Attack Map source-IP popup payloads if they display response status. Child change `add-response-outcome-backend-apis` confirmed no dedicated Attack Map popup backend route exists; item is delegated/completed as skipped/deferred without creating a new endpoint.
- [x] 6.13 Update Blocklist Manager APIs to include tracking-only provenance and related outcome ids. Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.14 Add canonical outcome count fields to the existing `/metrics/playbooks`, `/metrics/notifications`, `/metrics/incidents`, and `/metrics/approvals` endpoints in `metrics_routes.py`. Do not create a new endpoint. New fields are additive — existing fields must be preserved. Counts must be grouped by: `execution_mode` (observed/simulation/tracking_only/real), `execution_state` (observed/selected/queued/awaiting_approval/running/skipped/blocked/succeeded/failed), `external_executed` (true/false), `tracking_recorded` (true/false), and `simulated` (true/false). Completed by child change `add-response-outcome-backend-apis`.
- [x] 6.15 Add API contract tests for each updated endpoint and compatibility fallback for older records. Completed by child change `add-response-outcome-backend-apis`.

## 7. Phase 7 - Frontend Shared Outcome Components

Delegation note: Phase 7 frontend shared outcome component work was implemented
and verified by child change `add-response-outcome-frontend-components`.

- [x] 7.1 Create shared outcome display utility for canonical labels and color/tone mapping. Completed by child change `add-response-outcome-frontend-components`.
- [x] 7.2 Create shared `ResponseOutcomeBadge` component for execution mode/state. Completed by child change `add-response-outcome-frontend-components`.
- [x] 7.3 Create shared `ResponseOutcomeSummary` component that shows selected action, decision source, execution actor, execution booleans, summary, and related ids. Completed by child change `add-response-outcome-frontend-components`.
- [x] 7.4 Create shared formatter that avoids vague standalone `executed` copy. Completed by child change `add-response-outcome-frontend-components`.
- [x] 7.5 Add UI handling for inferred legacy outcomes. Completed by child change `add-response-outcome-frontend-components`.
- [x] 7.6 Add tests for all canonical modes, states, booleans, and reason codes. Completed by child change `add-response-outcome-frontend-components`.
- [x] 7.7 Add accessibility assertions for badge text and summary text. Completed by child change `add-response-outcome-frontend-components`.

## 8. Phase 8 - Alert Details and SOAR Queue UI

Delegation note: Phase 8 Alert Details and SOAR Queue UI work was implemented
and verified by child change `add-response-outcome-alert-queue-ui`.

- [x] 8.1 Update expanded alert row to display canonical response outcome summary. Completed by child change `add-response-outcome-alert-queue-ui`.
- [x] 8.2 Update alert side/detail panel to display selected action, decision source, execution actor, mode, state, execution booleans, summary, and related ids. Completed by child change `add-response-outcome-alert-queue-ui`.
- [x] 8.3 Update alert response log display to distinguish simulated, tracking-only, and real outcomes. Completed by child change `add-response-outcome-alert-queue-ui`.
- [x] 8.4 Update manual action feedback to describe tracking-only blocklist behavior accurately. Completed by child change `add-response-outcome-alert-queue-ui`.
- [x] 8.5 Update SOAR Queue list rows to show canonical outcome badge and summary. Completed by child change `add-response-outcome-alert-queue-ui`.
- [x] 8.6 Update SOAR Queue detail panel to show SOAR correlation id, related approval, response log, playbook execution, and canonical lifecycle. Completed by child change `add-response-outcome-alert-queue-ui`.
- [x] 8.7 Update SOAR Queue run simulation batch feedback to use canonical simulation language. Completed by child change `add-response-outcome-alert-queue-ui`.
- [x] 8.8 Add frontend tests for Alert Details and SOAR Queue outcome rendering. Completed by child change `add-response-outcome-alert-queue-ui`.

## 9. Phase 9 - SOC Command Center, Source-IP Context, Map, and Blocklist UI

Delegation note: Phase 9 SOC context, map, blocklist, approvals, playbook, and
metrics UI work was implemented and verified by child change
`add-response-outcome-soc-context-ui`.

- [x] 9.1 Update SOC Command Center operational cards to count canonical outcome modes/states and execution booleans. Completed by child change `add-response-outcome-soc-context-ui`.
- [x] 9.2 Update SOC Command Center incident workspace to show related canonical outcomes. Completed by child change `add-response-outcome-soc-context-ui`.
- [x] 9.3 Update Source-IP Context component to display recent canonical outcomes for the selected IP. Completed by child change `add-response-outcome-soc-context-ui`.
- [x] 9.4 Update Attack Map popup source-IP context integration to show canonical outcome labels if response status is displayed. Completed by child change `add-response-outcome-soc-context-ui`.
- [x] 9.5 Update Blocklist Manager to mark tracking-only entries and avoid implying firewall enforcement. Completed by child change `add-response-outcome-soc-context-ui`.
- [x] 9.6 Update Approvals Panel to show canonical awaiting/blocked/real-executed-after-approval language. Completed by child change `add-response-outcome-soc-context-ui`.
- [x] 9.7 Update Playbooks Panel execution timeline to use canonical step outcome labels. Completed by child change `add-response-outcome-soc-context-ui`.
- [x] 9.8 Update SOAR Metrics dashboard to distinguish observed, simulated, tracking-only, real, blocked, skipped, failed, awaiting approval, succeeded, `external_executed`, `tracking_recorded`, and `simulated` counts. Completed by child change `add-response-outcome-soc-context-ui`.
- [x] 9.9 Add frontend tests for SOC Command Center, Source-IP Context, Map context, Blocklist Manager, Approvals Panel, Playbooks Panel, and metrics. Completed by child change `add-response-outcome-soc-context-ui`.

## 10. Phase 10 - Retention, Archive, and Reporting Verification

Delegation note: Phase 10 retention, archive, and reporting verification work was
implemented and verified by child change `add-response-outcome-retention-e2e`.

- [x] 10.1 Define default retention window for canonical decisions and outcome events. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 10.2 Define archive criteria for append-only outcome events. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 10.3 Ensure archive preserves decision id, SOAR correlation id, selected action, final/latest outcome, and enough related ids to answer the primary analyst question. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 10.4 Add reporting query for "What happened, what response was selected, what playbook ran, and was anything actually executed?" Completed by child change `add-response-outcome-retention-e2e`.
- [x] 10.5 Verify latest-outcome queries perform acceptably with representative event volume. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 10.6 Verify metrics either include archived summaries or clearly document their live retention window. Completed by child change `add-response-outcome-retention-e2e`.

## 11. Phase 11 - End-to-End Tests

Delegation note: Phase 11 API/read-model integration and regression tests were
implemented and verified by child change `add-response-outcome-retention-e2e`.

- [x] 11.1 Add end-to-end test for alert observed-only lifecycle. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.2 Add end-to-end test for detection-selected simulated queue action. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.3 Add end-to-end test for manual tracking-only blocklist action. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.4 Add end-to-end test for playbook simulation step sequence. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.5 Add end-to-end test for playbook awaiting approval. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.6 Add end-to-end test for approval denied/expired blocking execution. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.7 Add end-to-end test for notification simulated delivery. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.8 Add end-to-end test for guarded real notification success using mocked provider calls. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.9 Add end-to-end test for real-capable notification blocked/fail-closed path. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.10 Add end-to-end test for source-IP context and SOC Command Center showing the same canonical outcome facts. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.11 Add regression test proving simulated actions are never shown as real executed. Completed by child change `add-response-outcome-retention-e2e`.
- [x] 11.12 Add regression test proving tracking-only blocklist entries are never shown as firewall enforcement. Completed by child change `add-response-outcome-retention-e2e`.

## 12. Phase 12 - Documentation and Interview Notes

Delegation note: Phase 12 documentation and interview-note work was implemented
and verified by child change `add-response-outcome-docs-rollout`.

- [x] 12.1 Update SOAR architecture documentation with canonical decision/outcome-event model definitions. Completed by child change `add-response-outcome-docs-rollout` in `docs/soar_response_outcome_model.md` and `docs/soar_architecture_summary.md`.
- [x] 12.2 Add dashboard wording guide for observed-only, simulated, tracking-only, real-executed, failed, blocked, awaiting approval, and skipped. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 12.3 Document schema additions and rollback behavior. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 12.4 Document backfill dry-run/write-mode strategy and compatibility behavior for legacy records. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 12.5 Document real execution safety boundaries, including firewall dry-run limitation and guarded notification adapters. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 12.6 Update runbooks for analysts explaining how to answer the primary outcome question. Completed by child change `add-response-outcome-docs-rollout` in `docs/soar_response_outcome_runbook.md`.
- [x] 12.7 Add interview notes summarizing why canonical outcomes were introduced and how they reduce ambiguity. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 12.8 Update OpenSpec task status after each completed implementation slice. Completed by child change `add-response-outcome-docs-rollout`.

## 13. Rollout and Rollback Checkpoints

Delegation note: Phase 13 rollout and rollback checkpoints were implemented and
verified by child change `add-response-outcome-docs-rollout`.

- [x] 13.1 Verify schema-only deployment can be rolled back by ignoring additive objects. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 13.2 Verify backend dual-write can be disabled without changing legacy behavior. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 13.3 Verify API consumers can fall back to legacy fields while canonical fields are unavailable. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 13.4 Verify UI can render inferred legacy outcomes. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 13.5 Verify production rollout order: schema, helpers, dry-run compatibility, dual-write, write-mode backfill, API fields, UI components, screen migrations, metrics. Completed by child change `add-response-outcome-docs-rollout` in `docs/soar_response_outcome_rollout.md`.
- [x] 13.6 Verify rollback order: disable UI canonical reads, disable API canonical preference, disable dual-write, leave additive data in place. Completed by child change `add-response-outcome-docs-rollout`.
- [x] 13.7 Document known risks and operator-facing mitigations before enabling canonical UI in production. Completed by child change `add-response-outcome-docs-rollout`.
