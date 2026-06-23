## 0. Phase 0 - Audit Confirmation

- [ ] 0.1 Re-read `schema.sql` and migrations for `alerts`, `response_actions_queue`, `response_actions_log`, `playbook_definitions`, `playbook_executions`, `approval_requests`, `approval_request_events`, `notification_delivery_attempts`, `incidents`, `incident_alerts`, `blocked_ips`, and `audit_log`.
- [ ] 0.2 Re-read ingest routes to confirm all post-commit paths that create queue actions, incidents, and playbook executions.
- [ ] 0.3 Re-read manual alert action route and confirm current tracking-only blocklist behavior.
- [ ] 0.4 Re-read `engines/soar_action_worker.py` and `engines/soar_executor.py` to confirm queue action states and simulation behavior.
- [ ] 0.5 Re-read `engines/playbook_step_executor.py` to confirm playbook step mode, approval gate, and notification delivery behavior.
- [ ] 0.6 Re-read integration adapters to confirm which adapters are real-capable and which remain simulation/dry-run only.
- [ ] 0.7 Re-read source-IP context, SOC Command Center, SOAR Queue, Approval Requests, Playbooks Panel, Alert Details, Attack Map, and Blocklist Manager UI data dependencies.
- [ ] 0.8 Document any divergence between the current audit and this spec before implementing schema.
- [ ] 0.9 Confirm no implementation phase will delete simulation mode or relabel simulated work as real.

## 1. Phase 1 - Data Model and Schema Migration

- [ ] 1.1 Draft migration for new canonical `soar_response_outcomes` table with correlation id, related ids, selected action, decision source, execution mode/state, executed boolean, summary, reason code, provider/adapter fields, safe metadata, and timestamps.
- [ ] 1.2 Add database constraints for allowed `execution_mode` values: `observed`, `simulation`, `tracking_only`, `real`.
- [ ] 1.3 Add database constraints for allowed `execution_state` values: `observed`, `selected`, `queued`, `awaiting_approval`, `running`, `skipped`, `blocked`, `succeeded`, `failed`.
- [ ] 1.4 Add database constraints for allowed `decision_source` values: `detection_default`, `correlation`, `playbook`, `queue_worker`, `manual`, `approval`, `adapter`, `migration`.
- [ ] 1.5 Add executed boolean compatibility constraints so observed and simulation outcomes cannot set `executed=true`.
- [ ] 1.6 Add indexes for `correlation_id`, `alert_id`, `incident_id`, `source_ip`, `queue_id`, `playbook_execution_id`, `approval_request_id`, `notification_delivery_attempt_id`, and mode/state/time queries.
- [ ] 1.7 Decide and implement nullable `correlation_id`/`outcome_id` linkage columns on existing tables where needed.
- [ ] 1.8 Add optional `tracking_only` or equivalent provenance linkage for `blocked_ips` if blocklist rows need explicit tracking-only display.
- [ ] 1.9 Update schema snapshot after migration.
- [ ] 1.10 Run schema validation script and record validation output.
- [ ] 1.11 Add migration tests for constraints, indexes, and additive compatibility.

## 2. Phase 2 - Backend Outcome Writer and Helpers

- [ ] 2.1 Create canonical enum/constants module for execution modes, execution states, decision sources, and UI labels.
- [ ] 2.2 Create outcome model validation helper for enum compatibility and executed boolean rules.
- [ ] 2.3 Create safe metadata sanitizer that rejects or redacts secrets, URLs, tokens, raw payloads, raw provider responses, raw headers, and unsafe exception strings.
- [ ] 2.4 Create correlation id generator for new response lifecycles.
- [ ] 2.5 Create deterministic legacy correlation id helper for migration/backfill.
- [ ] 2.6 Create outcome writer helper that inserts canonical outcome rows and returns serialized rows.
- [ ] 2.7 Create outcome lookup helpers by alert id, source IP, incident id, queue id, playbook execution id, approval request id, notification delivery id, and correlation id.
- [ ] 2.8 Create compatibility resolver that infers canonical outcome payloads when no ledger row exists.
- [ ] 2.9 Add unit tests for valid and invalid canonical outcome writes.
- [ ] 2.10 Add unit tests for metadata redaction and correlation id safety.
- [ ] 2.11 Add unit tests for conservative compatibility inference from legacy records.

## 3. Phase 3 - Queue and Response Log Normalization

- [ ] 3.1 Update alert ingest post-commit enqueue path to assign or propagate a SOAR correlation id for selected detection/correlation responses.
- [ ] 3.2 Dual-write canonical `selected` or `queued` outcomes when `response_actions_queue` rows are created.
- [ ] 3.3 Update queue worker claim path to write or update canonical `running` outcome evidence without changing existing queue state transitions.
- [ ] 3.4 Update queue approval-required path to write canonical `awaiting_approval` outcomes linked to queue and approval request.
- [ ] 3.5 Update queue approval-denied/expired path to write canonical `blocked` outcomes with `executed=false`.
- [ ] 3.6 Update queue simulation success path to write canonical `simulation/succeeded/executed=false` outcomes.
- [ ] 3.7 Update queue skipped path to write canonical `skipped/executed=false` outcomes with reason code.
- [ ] 3.8 Update queue failed path to write canonical `failed` outcomes with sanitized error summary.
- [ ] 3.9 Update `response_actions_log` writes to include correlation id and canonical mode/state/executed fields where schema allows.
- [ ] 3.10 Update manual `/alerts/<id>/execute` path to write canonical outcomes for manual monitor, escalation, simulation, and tracking-only blocklist recording.
- [ ] 3.11 Ensure manual tracking-only blocklist action says no firewall enforcement occurred.
- [ ] 3.12 Add route and worker tests for all queue/manual canonical outcome cases.

## 4. Phase 4 - Playbook, Approval, and Notification Outcome Integration

- [ ] 4.1 Propagate alert correlation id into newly-created `playbook_executions`.
- [ ] 4.2 Write canonical outcome rows when a playbook execution is created, claimed, completed, failed, abandoned, resumed, retried, or permanently failed.
- [ ] 4.3 Write canonical step outcomes for non-adapter playbook steps using step index and selected action.
- [ ] 4.4 Write canonical `awaiting_approval` outcomes when a playbook `require_approval` step pauses execution.
- [ ] 4.5 Write canonical `blocked` outcomes when playbook approvals are denied or expired.
- [ ] 4.6 Write canonical approval decision outcomes for `approval_requests` and `approval_request_events`.
- [ ] 4.7 Link approval outcomes to queue rows or playbook execution/step rows as applicable.
- [ ] 4.8 Map `notification_delivery_attempts.mode`, `status`, and metadata into canonical outcomes.
- [ ] 4.9 Ensure real notification delivery only uses `execution_mode=real` and `executed=true` when adapter result explicitly confirms execution.
- [ ] 4.10 Ensure failed-closed real-capable adapter results do not set `executed=true`.
- [ ] 4.11 Ensure firewall playbook adapter outcomes remain simulation/dry-run unless a future approved OpenSpec changes that.
- [ ] 4.12 Add tests covering playbook success, failure, approval pending, approval denied, approval expired, notification simulation, notification real success, notification blocked, and notification timeout.

## 5. Phase 5 - Backend API Contract Updates

- [ ] 5.1 Add canonical outcome serializer shape with `correlation_id`, `selected_action`, `decision_source`, `execution_mode`, `execution_state`, `executed`, `outcome_summary`, `related`, and `timestamps`.
- [ ] 5.2 Update alert list/detail APIs to include `response_outcome` and preserve legacy `response_action`/`response_status`.
- [ ] 5.3 Update response log API to include canonical outcome fields for each log row.
- [ ] 5.4 Update SOAR Queue status/list/detail APIs to include canonical outcomes and latest related approval/playbook/log ids.
- [ ] 5.5 Update Playbooks APIs to include execution-level and step-level canonical outcome payloads.
- [ ] 5.6 Update Approval APIs to include canonical outcomes for approval requests and decisions.
- [ ] 5.7 Update Notification Delivery APIs to include canonical mode/state/executed fields and related outcome ids.
- [ ] 5.8 Update Incident APIs and incident timeline to include canonical outcome events without mutating incident state.
- [ ] 5.9 Update Source-IP Context API to include recent canonical outcomes grouped by mode/state.
- [ ] 5.10 Update SOC Command Center data aggregation to prefer canonical outcomes where available.
- [ ] 5.11 Update Attack Map source-IP popup payloads if they display response status.
- [ ] 5.12 Update Blocklist Manager APIs to include tracking-only provenance and related outcome ids.
- [ ] 5.13 Update metrics APIs to count observed-only, simulation, tracking-only, real, awaiting approval, blocked, skipped, failed, and succeeded outcomes.
- [ ] 5.14 Add API contract tests for each updated endpoint and compatibility fallback for older records.

## 6. Phase 6 - Frontend Shared Outcome Components

- [ ] 6.1 Create shared outcome display utility for canonical labels and color/tone mapping.
- [ ] 6.2 Create shared `ResponseOutcomeBadge` component for execution mode/state.
- [ ] 6.3 Create shared `ResponseOutcomeSummary` component that shows selected action, decision source, executed truth, summary, and related ids.
- [ ] 6.4 Create shared formatter that avoids vague standalone `executed` copy.
- [ ] 6.5 Add UI handling for inferred legacy outcomes.
- [ ] 6.6 Add tests for all canonical modes and states.
- [ ] 6.7 Add accessibility assertions for badge text and summary text.

## 7. Phase 7 - Alert Details and SOAR Queue UI

- [ ] 7.1 Update expanded alert row to display canonical response outcome summary.
- [ ] 7.2 Update alert side/detail panel to display selected action, decision source, mode, state, executed truth, summary, and related ids.
- [ ] 7.3 Update alert response log display to distinguish simulated, tracking-only, and real outcomes.
- [ ] 7.4 Update manual action feedback to describe tracking-only blocklist behavior accurately.
- [ ] 7.5 Update SOAR Queue list rows to show canonical outcome badge and summary.
- [ ] 7.6 Update SOAR Queue detail panel to show correlation id, related approval, response log, playbook execution, and canonical lifecycle.
- [ ] 7.7 Update SOAR Queue run simulation batch feedback to use canonical simulation language.
- [ ] 7.8 Add frontend tests for Alert Details and SOAR Queue outcome rendering.

## 8. Phase 8 - SOC Command Center, Source-IP Context, Map, and Blocklist UI

- [ ] 8.1 Update SOC Command Center operational cards to count canonical outcome modes/states.
- [ ] 8.2 Update SOC Command Center incident workspace to show related canonical outcomes.
- [ ] 8.3 Update Source-IP Context component to display recent canonical outcomes for the selected IP.
- [ ] 8.4 Update Attack Map popup source-IP context integration to show canonical outcome labels if response status is displayed.
- [ ] 8.5 Update Blocklist Manager to mark tracking-only entries and avoid implying firewall enforcement.
- [ ] 8.6 Update Approvals Panel to show canonical awaiting/blocked/executed-after-approval language.
- [ ] 8.7 Update Playbooks Panel execution timeline to use canonical step outcome labels.
- [ ] 8.8 Update SOAR Metrics dashboard to distinguish observed, simulated, tracking-only, real, blocked, skipped, failed, awaiting approval, and succeeded counts.
- [ ] 8.9 Add frontend tests for SOC Command Center, Source-IP Context, Map context, Blocklist Manager, Approvals Panel, Playbooks Panel, and metrics.

## 9. Phase 9 - Migration and Backfill Verification

- [ ] 9.1 Implement backfill script or migration helper for observed-only alert outcomes.
- [ ] 9.2 Implement backfill for existing queue rows by status.
- [ ] 9.3 Implement backfill for existing response action log rows, including simulation and tracking-only inference.
- [ ] 9.4 Implement backfill for existing playbook executions and `steps_log` entries.
- [ ] 9.5 Implement backfill for existing approval requests and approval request events.
- [ ] 9.6 Implement backfill for existing notification delivery attempts.
- [ ] 9.7 Implement backfill for existing blocklist rows where source alert linkage exists.
- [ ] 9.8 Add dry-run mode that reports counts by source table and canonical mode/state without writing.
- [ ] 9.9 Add idempotency checks so repeated backfill runs do not create duplicate outcomes.
- [ ] 9.10 Add verification query/report for "What happened, what response was selected, what playbook ran, and was anything actually executed?"
- [ ] 9.11 Run backfill validation against representative local data and record results.

## 10. Phase 10 - End-to-End Tests

- [ ] 10.1 Add end-to-end test for alert observed-only lifecycle.
- [ ] 10.2 Add end-to-end test for detection-selected simulated queue action.
- [ ] 10.3 Add end-to-end test for manual tracking-only blocklist action.
- [ ] 10.4 Add end-to-end test for playbook simulation step sequence.
- [ ] 10.5 Add end-to-end test for playbook awaiting approval.
- [ ] 10.6 Add end-to-end test for approval denied/expired blocking execution.
- [ ] 10.7 Add end-to-end test for notification simulated delivery.
- [ ] 10.8 Add end-to-end test for guarded real notification success using mocked provider calls.
- [ ] 10.9 Add end-to-end test for real-capable notification blocked/fail-closed path.
- [ ] 10.10 Add end-to-end test for source-IP context and SOC Command Center showing the same canonical outcome facts.
- [ ] 10.11 Add regression test proving simulated actions are never shown as real executed.
- [ ] 10.12 Add regression test proving tracking-only blocklist entries are never shown as firewall enforcement.

## 11. Phase 11 - Documentation and Interview Notes

- [ ] 11.1 Update SOAR architecture documentation with canonical outcome model definitions.
- [ ] 11.2 Add dashboard wording guide for observed-only, simulated, tracking-only, real-executed, failed, blocked, awaiting approval, and skipped.
- [ ] 11.3 Document schema additions and rollback behavior.
- [ ] 11.4 Document backfill strategy and compatibility behavior for legacy records.
- [ ] 11.5 Document real execution safety boundaries, including firewall dry-run limitation and guarded notification adapters.
- [ ] 11.6 Update runbooks for analysts explaining how to answer the primary outcome question.
- [ ] 11.7 Add interview notes summarizing why canonical outcomes were introduced and how they reduce ambiguity.
- [ ] 11.8 Update OpenSpec task status after each completed implementation slice.

## 12. Rollout and Rollback Checkpoints

- [ ] 12.1 Verify schema-only deployment can be rolled back by ignoring additive objects.
- [ ] 12.2 Verify backend dual-write can be disabled without changing legacy behavior.
- [ ] 12.3 Verify API consumers can fall back to legacy fields while canonical fields are unavailable.
- [ ] 12.4 Verify UI can render inferred legacy outcomes.
- [ ] 12.5 Verify production rollout order: schema, helpers, dual-write, backfill dry-run, API fields, UI components, screen migrations, metrics.
- [ ] 12.6 Verify rollback order: disable UI canonical reads, disable API canonical preference, disable dual-write, leave additive data in place.
- [ ] 12.7 Document known risks and operator-facing mitigations before enabling canonical UI in production.
