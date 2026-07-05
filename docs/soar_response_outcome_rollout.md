# SOAR Response Outcome Rollout and Rollback

Last updated: 2026-07-05

This checkpoint guide covers production rollout and rollback for the canonical
SOAR response outcome model. It is documentation only and does not authorize new
runtime behavior.

## Scope Confirmation

The current implementation is additive:

- Legacy tables remain authoritative during rollout.
- Canonical tables and linkage columns are nullable/additive.
- API fields are additive and legacy fields remain present.
- Frontend components are expected to tolerate `response_outcome: null`.
- Firewall enforcement remains dry-run/tracking-only.
- Notifications require guarded real-execution evidence before
  `external_executed=true`.

## Checkpoint 1: Schema-Only Rollback

Verification:

- Additive schema can be ignored without changing existing queue, playbook,
  approval, notification, incident, blocklist, audit, or alert behavior.
- Existing queries that do not select canonical objects continue to work.
- No rollback requires reconstructing old behavior.

Objects to drop only in a separately approved rollback migration:

- `soar_response_outcome_events`
- `soar_response_decisions`
- `response_actions_queue.decision_id`
- `response_actions_queue.soar_correlation_id`
- `response_actions_log.decision_id`
- `response_actions_log.soar_correlation_id`
- `playbook_executions.decision_id`
- `playbook_executions.soar_correlation_id`
- `approval_requests.decision_id`
- `approval_requests.soar_correlation_id`
- `notification_delivery_attempts.decision_id`
- `notification_delivery_attempts.soar_correlation_id`
- Canonical indexes on the above tables

Preferred rollback is to leave objects in place and ignore them.

## Checkpoint 2: Backend Dual-Write Disable

Dual-write means runtime paths continue writing legacy records while also writing
canonical decisions/events.

Disable strategy:

- Prefer a code revert of the Phase 4-5 canonical writer wiring if emergency
  rollback is required.
- There is no documented production feature flag in this repository that
  disables all canonical writes globally.
- Keep legacy queue, approval, playbook, notification, and response-log paths in
  place.
- Do not drop canonical data as part of this operational rollback.

Verification:

- Queue worker still claims and completes jobs.
- Approval requests can still be created, approved, denied, or expired.
- Playbook executions still run through existing worker behavior.
- Notification delivery attempts still record legacy delivery state.
- Runtime paths do not require canonical write success to preserve legacy
  behavior.

## Checkpoint 3: API Legacy Fallback

API rollback means consumers stop relying on `response_outcome` and
`response_outcomes`.

Routes to inspect or revert for legacy-only display:

- `routes/alerts_events_routes.py`
- `routes/alert_mutation_routes.py`
- `routes/playbook_routes.py`
- `routes/approval_routes.py`
- `routes/notification_delivery_routes.py`
- `routes/incident_routes.py`
- `routes/source_ip_context_routes.py`
- `routes/blocklist_routes.py`
- `routes/metrics_routes.py`

Verification:

- Legacy fields such as `response_action`, `response_status`, queue status,
  playbook status, approval status, notification status, and blocklist state
  remain available.
- API payloads should include `response_outcome: null` during normal rollout when
  no canonical record exists.
- If an emergency revert removes `response_outcome`, frontend code must use
  legacy fields and must not crash.

## Checkpoint 4: UI Inferred Legacy Outcomes

Frontend files to inspect or revert for legacy-only display:

- `frontend/src/components/ResponseOutcome.js`
- `frontend/src/components/ResponseOutcomeBadge.js`
- `frontend/src/components/ResponseOutcomeSummary.js`
- `frontend/src/components/AlertExpandedRow.js`
- `frontend/src/components/AlertDetailsPanel.js`
- `frontend/src/components/AlertSidePanel.js`
- `frontend/src/components/AlertResponseLog.js`
- `frontend/src/components/AlertManualActions.js`
- `frontend/src/components/SoarQueuePanel.js`
- `frontend/src/components/SocCommandCenter.js`
- `frontend/src/components/SourceIpContext.js`
- `frontend/src/components/MapView.js`
- `frontend/src/components/BlocklistManagerPanel.js`
- `frontend/src/components/ApprovalsPanel.js`
- `frontend/src/components/PlaybooksPanel.js`
- `frontend/src/components/PlaybookExecutionTimeline.js`
- `frontend/src/components/SoarMetricsDashboard.js`
- `frontend/src/services/alertsService.js`
- `frontend/src/services/soarQueueService.js`
- `frontend/src/services/playbookService.js`
- `frontend/src/services/approvalService.js`
- `frontend/src/services/notificationDeliveryService.js`
- `frontend/src/services/sourceIpContextService.js`
- `frontend/src/services/blocklistService.js`
- `frontend/src/services/metricsService.js`

Verification:

- Phase 7 null-handling tests cover `ResponseOutcomeSummary` behavior when
  `response_outcome` is null or absent.
- No frontend crash should occur when canonical outcome data is unavailable.
- Legacy labels must avoid implying real execution unless real evidence exists.

## Production Rollout Order

1. Deploy schema: canonical tables and nullable linkage columns.
2. Deploy backend helpers: validators, writers, serializers, compatibility
   resolver, and latest-outcome read helpers.
3. Run backfill dry-run and review counts, ambiguous rows, booleans, and real
   notification evidence.
4. Deploy runtime dual-write for queue, manual action, playbook, approval,
   notification, audit, and response-log paths.
5. Run write-mode backfill after dry-run approval.
6. Deploy API `response_outcome` fields while preserving legacy fields.
7. Deploy shared UI components.
8. Deploy screen updates across Alert Details, SOAR Queue, SOC Command Center,
   Source-IP Context, Map, Blocklist Manager, Approvals, Playbooks, and metrics.
9. Verify end-to-end outcome flows and retention/reporting checks.
10. Enable canonical UI as the primary analyst language.

Each step is safe to pause after verification because the next step consumes
additive data from the previous one. Do not proceed from dry-run to write-mode
backfill until ambiguous rows and real-execution counts are reviewed.

## Production Rollback Order

1. Disable or revert UI canonical reads so screens use legacy fields.
2. Disable or revert API canonical preference and remove/ignore
   `response_outcome` fields.
3. Disable runtime canonical dual-write by reverting writer wiring or applying a
   separately approved global disable mechanism if one exists later.
4. Leave additive canonical data in place.
5. Drop canonical tables/columns only through a separately approved rollback
   migration after retention and audit requirements are reviewed.

Rollback does not require deleting canonical tables. They can be left in place
and ignored.

## Parent Risks and Mitigations

| Risk | Mitigation status |
|---|---|
| Canonical events and legacy snapshots diverge. | Implemented through centralized writer helpers, idempotency keys, and tests around writer/read behavior. |
| Backfill misclassifies historical rows. | Implemented through dry-run summaries, conservative defaults, `decision_source=migration`, reason codes, review flags, and real notification evidence gates. |
| Schema migration complexity increases. | Implemented as additive nullable tables/columns and indexes. Rollback can ignore new objects. |
| UI shows old ambiguous fields during transition. | Implemented through shared outcome components and canonical wording; legacy fallback remains transitional. |
| Real adapter semantics vary. | Implemented by requiring explicit guarded adapter metadata before `external_executed=true`. |
| Tracking-only confused with blocking. | Implemented through `Tracking only` labels, `tracking_recorded=true`, and summaries that state no enforcement occurred. |
| Append-only events grow quickly. | Implemented with indexes, latest-outcome read helpers, and retention/archive guidance. |
| SOAR correlation ids missing in old records. | Implemented through deterministic legacy correlation ids and compatibility resolvers. |

## Operator Mitigations Before Enabling Canonical UI

Complete these checks before broad production enablement:

- Dry-run backfill reviewed and approved.
- Ambiguous legacy rows reviewed.
- Write-mode backfill run once and repeat-run idempotency confirmed.
- Dual-write confirmed on queue, manual, playbook, approval, notification, audit,
  and response-log paths.
- Phase 11 end-to-end and regression tests pass.
- Rollout order reviewed with operators.
- Rollback order reviewed with operators.
- Firewall dry-run/tracking-only boundary confirmed.
- Notification real-execution evidence gate confirmed.
