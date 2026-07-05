# Proposal: Response Outcome Alert and Queue UI

## Problem

The parent roadmap `openspec/changes/clarify-soar-response-outcomes` defines canonical SOAR response outcome semantics across the full stack. Phase 7 shared components exist; backend API `response_outcome` fields are available on alert and SOAR queue endpoints. The Alert Details view, response log UI, manual action feedback, and SOAR Queue UI have not yet been updated to consume these canonical payloads. Analysts still see subsystem-specific status strings or ambiguous `executed` labels without knowing whether a response was simulated, tracking-only, or real.

## Goal

Implement Phase 8 of the parent roadmap: update the Alert Details view, response log display, manual action wording, and SOAR Queue UI to display canonical outcome data using the shared Phase 7 components.

## Scope

**Included:**
- Expanded alert row: show canonical `ResponseOutcomeBadge` for each alert's `response_outcome`.
- Alert side/detail panel: show `ResponseOutcomeSummary` with selected action, decision source, execution actor, mode, state, execution booleans, outcome summary, and related ids.
- Alert response log display: use canonical outcome language to distinguish simulated, tracking-only, and real outcomes.
- Manual action feedback (e.g., block_ip response): describe tracking-only blocklist behavior accurately using canonical labels; remove or update any copy that implies external enforcement.
- SOAR Queue list rows: show `ResponseOutcomeBadge` and canonical outcome summary alongside existing status fields.
- SOAR Queue detail panel: show SOAR correlation id, related approval, response log, playbook execution, and canonical lifecycle using `ResponseOutcomeSummary`.
- SOAR Queue run simulation batch feedback: use canonical simulation language (`Simulated`, not `Executed`).
- Frontend tests for all updated Alert Details and SOAR Queue outcome rendering.

**Excluded:**
- No SOC Command Center, Source-IP Context, Attack Map, Blocklist Manager, Approvals Panel, Playbooks Panel, or SOAR Metrics changes (those are Phase 9; see child change `add-response-outcome-soc-context-ui`).
- No new shared components (those are Phase 7; see child change `add-response-outcome-frontend-components`).
- No backend changes.
- No migrations.
- No new API routes.
- No runtime behavior changes.
- No commits or pushes.

## Parent Roadmap Reference

This child change implements Phase 8 from `openspec/changes/clarify-soar-response-outcomes`. The parent remains the master roadmap. This child change is the active implementation spec for Phase 8 Alert Details and SOAR Queue UI work only.

## Success Criteria

- Alert expanded rows display `ResponseOutcomeBadge` with correct canonical label for every outcome state.
- Alert detail panel shows full `ResponseOutcomeSummary` with related ids.
- Response log entries no longer use ambiguous standalone `executed`; they use canonical simulation/tracking-only/real labels.
- Manual action feedback for `block_ip` explicitly says tracking-only/SIEM-only, not external enforcement.
- SOAR Queue list rows show canonical badge alongside existing status.
- SOAR Queue detail panel shows SOAR correlation id and canonical lifecycle.
- SOAR Queue batch simulation feedback uses `Simulated` not `Executed`.
- All Phase 7 shared components used; no inline label logic duplicated.
- `response_outcome: null` rendered gracefully in all views using the no-history state.
- Frontend tests pass with zero failures for all updated surfaces.
