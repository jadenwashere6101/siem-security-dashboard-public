# Design: Response Outcome Docs and Rollout

## Boundary

This child change is documentation, runbook, and rollout checkpoint work only. It does not add migrations, change API routes, modify canonical outcome writers, or alter UI components or runtime behavior. All phases (1–11) must be implemented before rollout checkpoints can be fully verified.

## Documentation Artifacts

### SOAR Architecture Documentation

Update or create the SOAR architecture document to include:
- Canonical decision/outcome-event model overview: why two tables, what each records.
- `soar_response_decisions` table purpose, key columns, and constraints.
- `soar_response_outcome_events` table purpose, append-only semantics, and key constraints.
- `soar_correlation_id` propagation rules across alerts, queue, playbooks, approvals, notifications, response logs, incidents, and audit log.
- Latest-outcome read model: how it is derived, what SQL/helper is used, what the output shape is.
- Canonical enum values: `execution_mode`, `execution_state`, `decision_source`, `execution_actor`, `reason_code`.
- Boolean compatibility rules: `external_executed`, `tracking_recorded`, `simulated`.

### Dashboard Wording Guide

Document the canonical UI label table for all analysts and frontend developers:

| execution_mode | execution_state | external_executed | tracking_recorded | simulated | Label |
|---|---|---|---|---|---|
| any | observed | false | false | false | Observed only |
| simulation | any | false | false | true | Simulated |
| tracking_only | any | false | true | false | Tracking only |
| real | succeeded | true | false | false | Real executed |
| any | awaiting_approval | false | false | false | Awaiting approval |
| any | blocked | false | false | false | Blocked by approval |
| any | skipped | false | false | false | Skipped |
| any | failed | false | false | false | Failed |

Include guidance:
- Do not use standalone `"Executed"`.
- Use composite phrases for in-progress states: `"Running - Simulated"`, `"Running - Real"`.
- The wording guide is authoritative for all frontend label decisions in Phases 7–9.

### Schema Additions and Rollback Behavior

Document for each new table and additive column:
- What was added (table, column, index, constraint).
- Rollback behavior: what happens if new tables/columns are dropped.
- Whether existing behavior changes if rollback occurs.
- Confirm: rollback does not require reconstructing old behavior because existing legacy tables remain authoritative during rollout.

### Backfill Strategy and Legacy Compatibility

Document:
- Dry-run mode: what it produces, how to interpret the output, what to review before enabling write mode.
- Write mode: what rows are created, how idempotency is maintained, how to re-run safely.
- Conservative defaults: how ambiguous legacy rows are mapped (observed/simulation conservatively, not real).
- Compatibility resolvers: how old records answer the primary analyst question without canonical rows.
- Known gaps: what legacy records cannot be fully mapped and why.

### Real Execution Safety Boundaries

Document:
- Firewall adapter remains simulation/dry-run only in the current implementation. No Phase 1–13 work enables real firewall enforcement. Document this boundary explicitly.
- Notification adapters: real execution requires explicit adapter metadata confirming delivery success; fail-closed paths must not set `external_executed = true`.
- Manual actions: tracking-only blocklist recording sets `tracking_recorded = true`, not `external_executed = true`. No local enforcement occurs.
- Future changes to real execution boundaries require a separate approved OpenSpec.

### Analyst Runbooks

Add step-by-step runbooks answering:
1. **"What happened to this alert?"**: navigate to Alert Details → read `ResponseOutcomeSummary` → interpret canonical labels.
2. **"Was anything actually executed?"**: check `external_executed` in `response_outcome`; `true` means real provider/enforcement; `false` with `tracking_recorded = true` means SIEM-only tracking.
3. **"Why was this blocked?"**: check `execution_state = blocked` and `reason_code = approval_denied`; navigate to Approvals Panel for decision details.
4. **"What playbook ran?"**: check `response_outcome.related.playbook_execution_id`; navigate to Playbooks Panel for step-level timeline.
5. **"What does this queue item mean?"**: use SOAR Queue detail panel; read SOAR correlation id and canonical lifecycle summary.

### Interview Notes

Summarize:
- Why canonical outcomes were introduced: to replace ambiguous `executed` semantics that could not distinguish simulated, tracking-only, and real enforcement.
- How they reduce ambiguity: one model, one set of labels, one API shape across all SIEM/SOAR views.
- What was preserved: simulation mode, existing detection semantics, approval workflows, all legacy fields during transition.
- What was not changed: real firewall enforcement policy (still dry-run only), detection and correlation logic, approval policy.

## Rollout Checkpoint Design (Phase 13)

### Checkpoint 1: Schema-only rollback

- Deploy schema (tables + linkage columns) with no behavior change.
- Verify rollback by ignoring additive tables/columns — existing behavior must be unchanged.
- Document: which objects to drop, what queries must still work after drop.

### Checkpoint 2: Backend dual-write disable

- Disable canonical outcome writing without reverting to pre-Phase-4 queue worker behavior.
- Verify: queue worker still processes jobs; approvals still work; playbooks still run; no runtime error occurs when canonical write is skipped.

### Checkpoint 3: API legacy fallback

- Remove `response_outcome` from API responses (revert Phase 6 API additions).
- Verify: frontend can render with only legacy fields; no JavaScript error occurs; no backend error occurs.

### Checkpoint 4: UI inferred legacy outcomes

- Verify Phase 7 components handle null `response_outcome` gracefully (confirmed by Phase 7 null-handling tests).
- Document: no frontend crash when `response_outcome` is absent from any API response.

### Checkpoint 5: Production rollout order

Document the required production rollout sequence:
1. Deploy schema (Phase 1 migration).
2. Deploy backend helpers (Phase 2).
3. Run backfill dry-run; review output (Phase 3).
4. Deploy runtime dual-write (Phases 4–5).
5. Run write-mode backfill after review.
6. Deploy API `response_outcome` fields (Phase 6).
7. Deploy Phase 7 shared UI components.
8. Deploy Phase 8 and 9 screen updates.
9. Verify end-to-end (Phase 11) and retention (Phase 10) documentation.
10. Enable canonical UI for all users.

### Checkpoint 6: Production rollback order

Document the required rollback sequence:
1. Disable UI canonical reads (revert Phases 8–9 to legacy display).
2. Disable API canonical preference (remove `response_outcome` from Phase 6 additions).
3. Disable backend dual-write (revert Phase 4–5 runtime wiring).
4. Leave additive tables/columns in place (or drop in a separately approved rollback migration).

### Known Risks and Mitigations

Document each risk from the parent design section and confirm its mitigation has been implemented:
- Canonical events and legacy snapshots diverge → one outcome writer, consistency tests.
- Backfill misclassification → conservative defaults, dry-run, reason codes, safe summaries.
- Schema migration complexity → additive nullable, phased, rollback ignores new columns.
- UI shows old ambiguous fields during transition → shared outcome component, phased removal.
- Real adapter semantics vary → only mark `external_executed=true` with explicit evidence.
- Tracking-only confused with blocking → labels say `"Tracking only"`, summaries say no enforcement.
- Append-only events grow quickly → indexes, latest-outcome read model, retention policy.
- SOAR correlation ids missing in old records → deterministic legacy ids, compatibility resolvers.
