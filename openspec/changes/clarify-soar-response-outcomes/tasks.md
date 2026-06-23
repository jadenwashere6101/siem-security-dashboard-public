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
- [ ] 2.10 Create compatibility resolver that infers canonical latest outcome payloads when no decision/event row exists.
- [x] 2.11 Add unit tests for valid and invalid decision writes.
- [x] 2.12 Add unit tests for valid and invalid outcome event writes.
- [x] 2.13 Add unit tests for metadata redaction and SOAR correlation id safety.
- [x] 2.14 Add unit tests for latest-outcome ordering and read-model defaults when no events exist.

## 3. Phase 3 - Backfill Dry-Run and Compatibility Verification

- [ ] 3.1 Implement dry-run scanner for observed-only alert outcomes without writing canonical rows.
- [ ] 3.2 Implement dry-run scanner for existing queue rows by status.
- [ ] 3.3 Implement dry-run scanner for existing response action log rows, including simulation and tracking-only inference.
- [ ] 3.4 Implement dry-run scanner for existing playbook executions and `steps_log` entries.
- [ ] 3.5 Implement dry-run scanner for existing approval requests and approval request events.
- [ ] 3.6 Implement dry-run scanner for existing notification delivery attempts.
- [ ] 3.7 Implement dry-run scanner for existing blocklist rows where source alert linkage exists.
- [ ] 3.8 Report dry-run counts by source table, decision source, execution mode/state, reason code, `external_executed`, `tracking_recorded`, and `simulated`.
- [ ] 3.9 Add compatibility resolver tests proving old records can answer the primary analyst question before broad UI migration.
- [ ] 3.10 Add idempotency checks proving repeated dry-run and later write-mode backfill cannot create duplicate decisions/events.
- [ ] 3.11 Review dry-run output against representative local data and update mapping rules before enabling write-mode backfill.

## 4. Phase 4 - Queue and Response Log Normalization

- [ ] 4.1 Update alert ingest post-commit enqueue path to assign or propagate a SOAR correlation id for selected detection/correlation responses.
- [ ] 4.2 Create canonical decision rows when detection, correlation, or queue creation selects a response action.
- [ ] 4.3 Append `selected` or `queued` outcome events when `response_actions_queue` rows are created.
- [ ] 4.4 Update queue worker claim path to append `running` outcome events without changing existing queue state transitions.
- [ ] 4.5 Update queue approval-required path to append `awaiting_approval` events linked to queue and approval request.
- [ ] 4.6 Update queue approval-denied/expired path to append `blocked` events with `reason_code=approval_denied` and no execution booleans set.
- [ ] 4.7 Update queue simulation success path to append `simulation/succeeded`, `simulated=true`, `external_executed=false`, and `tracking_recorded=false`.
- [ ] 4.8 Update queue skipped path to append `skipped` events with reason code.
- [ ] 4.9 Update queue failed path to append `failed` events with sanitized error summary.
- [ ] 4.10 Update `response_actions_log` writes to include SOAR correlation and decision/outcome-event linkage where schema allows.
- [ ] 4.11 Update manual `/alerts/<id>/execute` path to create decisions/events for manual monitor, escalation, simulation, and tracking-only blocklist recording.
- [ ] 4.12 Ensure manual tracking-only blocklist action sets `tracking_recorded=true`, `external_executed=false`, and says no firewall enforcement occurred.
- [ ] 4.13 Add route and worker tests for all queue/manual canonical outcome cases.

## 5. Phase 5 - Playbook, Approval, Notification, Audit, and Backfill Write Integration

- [ ] 5.1 Propagate alert SOAR correlation id into newly-created `playbook_executions`.
- [ ] 5.2 Create child decisions for playbook steps that select distinct response actions.
- [ ] 5.3 Append outcome events when a playbook execution is created, claimed, completed, failed, abandoned, resumed, retried, or permanently failed.
- [ ] 5.4 Append step outcome events for non-adapter playbook steps using step index and selected action.
- [ ] 5.5 Append `awaiting_approval` events when a playbook `require_approval` step pauses execution.
- [ ] 5.6 Append `blocked` events when playbook approvals are denied or expired.
- [ ] 5.7 Append approval decision events for `approval_requests` and `approval_request_events` using `execution_actor=approval_service`.
- [ ] 5.8 Link approval outcomes to queue rows or playbook execution/step rows as applicable.
- [ ] 5.9 Map `notification_delivery_attempts.mode`, `status`, and metadata into canonical outcome events.
- [ ] 5.10 Ensure real notification delivery only uses `execution_mode=real` and `external_executed=true` when adapter result explicitly confirms real execution.
- [ ] 5.11 Ensure failed-closed real-capable adapter results do not set `external_executed=true`.
- [ ] 5.12 Ensure firewall playbook adapter outcomes remain simulation/dry-run unless a future approved OpenSpec changes that.
- [ ] 5.13 Link relevant `audit_log` rows to SOAR correlation, decision, and latest outcome event where useful.
- [ ] 5.14 Implement write-mode backfill after dry-run verification, using deterministic idempotency keys.
- [ ] 5.15 Add tests covering playbook success, failure, approval pending, approval denied, approval expired, notification simulation, notification real success, notification blocked, notification timeout, audit linkage, and write-mode backfill idempotency.

## 6. Phase 6 - Backend API Contract Updates

- [ ] 6.1 Add canonical latest-outcome serializer shape with `soar_correlation_id`, `decision_id`, `latest_outcome_event_id`, selected action, decision source, execution actor, execution mode/state, `external_executed`, `tracking_recorded`, `simulated`, summary, reason code, related ids, and timestamps.
- [ ] 6.2 Add outcome timeline serializer for ordered decision/outcome-event history.
- [ ] 6.3 Update alert list/detail APIs to include `response_outcome` and preserve legacy `response_action`/`response_status`.
- [ ] 6.4 Update response log API to include canonical outcome links and latest outcome where available.
- [ ] 6.5 Update SOAR Queue status/list/detail APIs to include canonical latest outcomes and related approval/playbook/log ids.
- [ ] 6.6 Update Playbooks APIs to include execution-level and step-level canonical outcome payloads.
- [ ] 6.7 Update Approval APIs to include canonical outcomes for approval requests and decisions.
- [ ] 6.8 Update Notification Delivery APIs to include canonical mode/state and execution booleans derived from delivery status, mode, and adapter result metadata.
- [ ] 6.9 Update Incident APIs and incident timeline to include canonical outcome events without mutating incident state.
- [ ] 6.10 Update Source-IP Context API to include recent canonical outcomes grouped by mode/state and execution booleans.
- [ ] 6.11 Update SOC Command Center data aggregation to prefer canonical outcomes where available.
- [ ] 6.12 Update Attack Map source-IP popup payloads if they display response status.
- [ ] 6.13 Update Blocklist Manager APIs to include tracking-only provenance and related outcome ids.
- [ ] 6.14 Update metrics APIs to count observed-only, simulation, tracking-only, real, awaiting approval, blocked, skipped, failed, succeeded, `external_executed`, `tracking_recorded`, and `simulated` outcomes.
- [ ] 6.15 Add API contract tests for each updated endpoint and compatibility fallback for older records.

## 7. Phase 7 - Frontend Shared Outcome Components

- [ ] 7.1 Create shared outcome display utility for canonical labels and color/tone mapping.
- [ ] 7.2 Create shared `ResponseOutcomeBadge` component for execution mode/state.
- [ ] 7.3 Create shared `ResponseOutcomeSummary` component that shows selected action, decision source, execution actor, execution booleans, summary, and related ids.
- [ ] 7.4 Create shared formatter that avoids vague standalone `executed` copy.
- [ ] 7.5 Add UI handling for inferred legacy outcomes.
- [ ] 7.6 Add tests for all canonical modes, states, booleans, and reason codes.
- [ ] 7.7 Add accessibility assertions for badge text and summary text.

## 8. Phase 8 - Alert Details and SOAR Queue UI

- [ ] 8.1 Update expanded alert row to display canonical response outcome summary.
- [ ] 8.2 Update alert side/detail panel to display selected action, decision source, execution actor, mode, state, execution booleans, summary, and related ids.
- [ ] 8.3 Update alert response log display to distinguish simulated, tracking-only, and real outcomes.
- [ ] 8.4 Update manual action feedback to describe tracking-only blocklist behavior accurately.
- [ ] 8.5 Update SOAR Queue list rows to show canonical outcome badge and summary.
- [ ] 8.6 Update SOAR Queue detail panel to show SOAR correlation id, related approval, response log, playbook execution, and canonical lifecycle.
- [ ] 8.7 Update SOAR Queue run simulation batch feedback to use canonical simulation language.
- [ ] 8.8 Add frontend tests for Alert Details and SOAR Queue outcome rendering.

## 9. Phase 9 - SOC Command Center, Source-IP Context, Map, and Blocklist UI

- [ ] 9.1 Update SOC Command Center operational cards to count canonical outcome modes/states and execution booleans.
- [ ] 9.2 Update SOC Command Center incident workspace to show related canonical outcomes.
- [ ] 9.3 Update Source-IP Context component to display recent canonical outcomes for the selected IP.
- [ ] 9.4 Update Attack Map popup source-IP context integration to show canonical outcome labels if response status is displayed.
- [ ] 9.5 Update Blocklist Manager to mark tracking-only entries and avoid implying firewall enforcement.
- [ ] 9.6 Update Approvals Panel to show canonical awaiting/blocked/real-executed-after-approval language.
- [ ] 9.7 Update Playbooks Panel execution timeline to use canonical step outcome labels.
- [ ] 9.8 Update SOAR Metrics dashboard to distinguish observed, simulated, tracking-only, real, blocked, skipped, failed, awaiting approval, succeeded, `external_executed`, `tracking_recorded`, and `simulated` counts.
- [ ] 9.9 Add frontend tests for SOC Command Center, Source-IP Context, Map context, Blocklist Manager, Approvals Panel, Playbooks Panel, and metrics.

## 10. Phase 10 - Retention, Archive, and Reporting Verification

- [ ] 10.1 Define default retention window for canonical decisions and outcome events.
- [ ] 10.2 Define archive criteria for append-only outcome events.
- [ ] 10.3 Ensure archive preserves decision id, SOAR correlation id, selected action, final/latest outcome, and enough related ids to answer the primary analyst question.
- [ ] 10.4 Add reporting query for "What happened, what response was selected, what playbook ran, and was anything actually executed?"
- [ ] 10.5 Verify latest-outcome queries perform acceptably with representative event volume.
- [ ] 10.6 Verify metrics either include archived summaries or clearly document their live retention window.

## 11. Phase 11 - End-to-End Tests

- [ ] 11.1 Add end-to-end test for alert observed-only lifecycle.
- [ ] 11.2 Add end-to-end test for detection-selected simulated queue action.
- [ ] 11.3 Add end-to-end test for manual tracking-only blocklist action.
- [ ] 11.4 Add end-to-end test for playbook simulation step sequence.
- [ ] 11.5 Add end-to-end test for playbook awaiting approval.
- [ ] 11.6 Add end-to-end test for approval denied/expired blocking execution.
- [ ] 11.7 Add end-to-end test for notification simulated delivery.
- [ ] 11.8 Add end-to-end test for guarded real notification success using mocked provider calls.
- [ ] 11.9 Add end-to-end test for real-capable notification blocked/fail-closed path.
- [ ] 11.10 Add end-to-end test for source-IP context and SOC Command Center showing the same canonical outcome facts.
- [ ] 11.11 Add regression test proving simulated actions are never shown as real executed.
- [ ] 11.12 Add regression test proving tracking-only blocklist entries are never shown as firewall enforcement.

## 12. Phase 12 - Documentation and Interview Notes

- [ ] 12.1 Update SOAR architecture documentation with canonical decision/outcome-event model definitions.
- [ ] 12.2 Add dashboard wording guide for observed-only, simulated, tracking-only, real-executed, failed, blocked, awaiting approval, and skipped.
- [ ] 12.3 Document schema additions and rollback behavior.
- [ ] 12.4 Document backfill dry-run/write-mode strategy and compatibility behavior for legacy records.
- [ ] 12.5 Document real execution safety boundaries, including firewall dry-run limitation and guarded notification adapters.
- [ ] 12.6 Update runbooks for analysts explaining how to answer the primary outcome question.
- [ ] 12.7 Add interview notes summarizing why canonical outcomes were introduced and how they reduce ambiguity.
- [ ] 12.8 Update OpenSpec task status after each completed implementation slice.

## 13. Rollout and Rollback Checkpoints

- [ ] 13.1 Verify schema-only deployment can be rolled back by ignoring additive objects.
- [ ] 13.2 Verify backend dual-write can be disabled without changing legacy behavior.
- [ ] 13.3 Verify API consumers can fall back to legacy fields while canonical fields are unavailable.
- [ ] 13.4 Verify UI can render inferred legacy outcomes.
- [ ] 13.5 Verify production rollout order: schema, helpers, dry-run compatibility, dual-write, write-mode backfill, API fields, UI components, screen migrations, metrics.
- [ ] 13.6 Verify rollback order: disable UI canonical reads, disable API canonical preference, disable dual-write, leave additive data in place.
- [ ] 13.7 Document known risks and operator-facing mitigations before enabling canonical UI in production.
