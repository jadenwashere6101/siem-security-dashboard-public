## 12. Phase 12 - Documentation and Interview Notes

> Parent roadmap task reference: tasks 12.1–12.8 in `openspec/changes/clarify-soar-response-outcomes/tasks.md`.
> The parent remains the master roadmap. Mark parent tasks complete after this child is verified.

### Pre-Implementation

- [x] 12.0.1 Confirm Phases 1–11 are implemented and their respective tests pass.
- [x] 12.0.2 Locate existing SOAR architecture documentation location (if any) in the repo.
- [x] 12.0.3 Locate existing wording guides or style documentation (if any) in the repo.

### SOAR Architecture Documentation

- [x] 12.1 Update or create the SOAR architecture document to include the canonical decision/outcome-event model overview: why two tables, what each records, and how they relate.
- [x] 12.2 Document `soar_response_decisions` table purpose, key columns, and constraints.
- [x] 12.3 Document `soar_response_outcome_events` table purpose, append-only semantics, and key constraints.
- [x] 12.4 Document `soar_correlation_id` propagation rules across alerts, queue, playbooks, approvals, notifications, response logs, incidents, and audit log.
- [x] 12.5 Document the latest-outcome read model: how it is derived, what helper is used, and what the output shape is.
- [x] 12.6 Document canonical enum values: all `execution_mode`, `execution_state`, `decision_source`, `execution_actor`, and `reason_code` values.
- [x] 12.7 Document boolean compatibility rules: `external_executed`, `tracking_recorded`, and `simulated`.

### Dashboard Wording Guide

- [x] 12.8 Create a dashboard wording guide documenting the canonical label table for all combinations of `execution_mode`, `execution_state`, `external_executed`, `tracking_recorded`, and `simulated`.
- [x] 12.9 Include guidance that standalone `"Executed"` must not be used in any canonical label.
- [x] 12.10 Include composite label examples for in-progress states.
- [x] 12.11 Mark this guide as authoritative for all frontend label decisions in Phases 7–9.

### Schema Additions and Rollback Behavior

- [x] 12.12 Document each new table and additive column with its rollback behavior (what happens if dropped, whether existing behavior changes).
- [x] 12.13 Confirm and document that rollback does not require reconstructing old behavior because legacy tables remain authoritative during rollout.

### Backfill Strategy and Legacy Compatibility Documentation

- [x] 12.14 Document the dry-run mode output format, how to interpret it, and what must be reviewed before enabling write mode.
- [x] 12.15 Document write-mode idempotency: how to re-run safely, how to confirm no duplicate decisions/events were created.
- [x] 12.16 Document conservative default mappings for ambiguous legacy rows.
- [x] 12.17 Document compatibility resolver behavior for old records without canonical rows.
- [x] 12.18 Document known mapping gaps: which legacy records cannot be fully mapped and why.

### Real Execution Safety Boundaries

- [x] 12.19 Document that the firewall adapter remains simulation/dry-run only in the current implementation; no Phase 1–13 work enables real firewall enforcement.
- [x] 12.20 Document notification adapter real-execution requirements: explicit adapter metadata confirming delivery success; fail-closed paths must not set `external_executed = true`.
- [x] 12.21 Document manual action tracking-only boundary: blocklist recording sets `tracking_recorded = true`, not `external_executed = true`; no local enforcement occurs.
- [x] 12.22 Document that future changes to real execution boundaries require a separate approved OpenSpec.

### Analyst Runbooks

- [x] 12.23 Add runbook: "What happened to this alert?" — step-by-step using Alert Details canonical outcome display.
- [x] 12.24 Add runbook: "Was anything actually executed?" — how to read `external_executed` and canonical labels.
- [x] 12.25 Add runbook: "Why was this blocked?" — how to read `execution_state = blocked`, `reason_code = approval_denied`, and navigate to Approvals Panel.
- [x] 12.26 Add runbook: "What playbook ran?" — how to read `related.playbook_execution_id` and navigate to Playbooks Panel.
- [x] 12.27 Add runbook: "What does this queue item mean?" — how to use SOAR Queue detail panel and SOAR correlation id.

### Interview Notes

- [x] 12.28 Write interview notes summarizing why canonical outcomes were introduced: replace ambiguous `executed` semantics; distinguish simulated, tracking-only, and real enforcement.
- [x] 12.29 Write interview notes summarizing how canonical outcomes reduce ambiguity: one model, one label set, one API shape across all views.
- [x] 12.30 Write interview notes confirming what was preserved: simulation mode, existing detection semantics, approval workflows, all legacy fields during transition.
- [x] 12.31 Write interview notes confirming what was not changed: real firewall enforcement policy (still dry-run only), detection/correlation logic, approval policy.

### OpenSpec Task Status

- [x] 12.32 Update parent roadmap task status (`clarify-soar-response-outcomes/tasks.md`) for all Phase 12 tasks as they are completed.

### Validation

- [x] 12.33 Run `openspec validate add-response-outcome-docs-rollout --strict` and confirm valid.
- [x] 12.34 Run `git diff --check` and confirm no whitespace errors.

---

## 13. Phase 13 - Rollout and Rollback Checkpoints

> Parent roadmap task reference: tasks 13.1–13.7 in `openspec/changes/clarify-soar-response-outcomes/tasks.md`.
> The parent remains the master roadmap. Mark parent tasks complete after this child is verified.

### Pre-Implementation

- [x] 13.0.1 Confirm Phases 1–12 are implemented.
- [x] 13.0.2 Confirm Phase 11 end-to-end and regression tests pass.

### Rollout Checkpoint 1: Schema-only rollback

- [x] 13.1 Verify schema-only deployment can be rolled back by ignoring or dropping additive tables/columns without changing existing behavior.
- [x] 13.2 Document which objects to drop and confirm existing queries still work after drop.

### Rollout Checkpoint 2: Backend dual-write disable

- [x] 13.3 Verify backend dual-write can be disabled without breaking queue worker, approval, playbook, or notification runtime behavior.
- [x] 13.4 Document how to disable dual-write (feature flag, env var, or code revert) and confirm no runtime error occurs.

### Rollout Checkpoint 3: API legacy fallback

- [x] 13.5 Verify API consumers can fall back to legacy fields if `response_outcome` is removed from API responses.
- [x] 13.6 Document which frontend files and API routes to revert to restore legacy-only display.

### Rollout Checkpoint 4: UI inferred legacy outcomes

- [x] 13.7 Verify Phase 7 `ResponseOutcomeSummary` handles null `response_outcome` gracefully (confirmed by Phase 7 null-handling tests).
- [x] 13.8 Document that no frontend crash occurs when `response_outcome` is absent from any API response.

### Rollout Checkpoint 5: Production rollout order

- [x] 13.9 Document the required production rollout sequence (schema → helpers → dry-run → dual-write → backfill → API fields → UI components → screen updates → e2e verification → canonical UI enabled).
- [x] 13.10 Verify the rollout sequence is safe to pause after each step.

### Rollout Checkpoint 6: Production rollback order

- [x] 13.11 Document the required rollback sequence (UI revert → API revert → dual-write disable → additive data preserved).
- [x] 13.12 Confirm rollback does not require deleting canonical tables; they can be left in place and ignored until a separately approved rollback migration.

### Known Risks and Mitigations

- [x] 13.13 Document each risk from the parent design section and confirm its mitigation has been implemented across Phases 1–11.
- [x] 13.14 Document operator-facing mitigations before enabling canonical UI in production: dry-run review, backfill review, dual-write confirmation, e2e test pass, rollout order review.

### OpenSpec Task Status

- [x] 13.15 Update parent roadmap task status (`clarify-soar-response-outcomes/tasks.md`) for all Phase 13 tasks as they are completed.
- [x] 13.16 Mark this child change as complete in the parent roadmap delegation notes after all tasks pass.

### Validation

- [x] 13.17 Run `openspec validate add-response-outcome-docs-rollout --strict` and confirm valid.
- [x] 13.18 Run `git diff --check` and confirm no whitespace errors.
