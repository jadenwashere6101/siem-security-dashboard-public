# Proposal: Response Outcome SOC Context UI

## Problem

The parent roadmap `openspec/changes/clarify-soar-response-outcomes` defines canonical SOAR response outcome semantics across the full stack. Phase 7 shared components exist; Phase 8 Alert Details and SOAR Queue UI are updated. The remaining analyst-facing surfaces — SOC Command Center, Source-IP Context, Attack Map integration, Blocklist Manager, Approvals Panel, Playbooks Panel, and SOAR Metrics dashboard — still display subsystem-specific status strings or ambiguous fields. Analysts cannot consistently answer the primary outcome question ("What happened, was anything executed?") from these views.

## Goal

Implement Phase 9 of the parent roadmap: update the SOC Command Center, Source-IP Context, Attack Map popup context, Blocklist Manager, Approvals Panel, Playbooks Panel, and SOAR Metrics dashboard to display canonical outcome data using the shared Phase 7 components and Phase 6 backend API payloads.

## Scope

**Included:**
- SOC Command Center operational cards: count canonical outcome modes/states and execution booleans using metrics endpoint data already updated in Phase 6.
- SOC Command Center incident workspace: show related canonical outcomes for the selected incident.
- Source-IP Context component: display recent canonical outcomes for the selected IP using the Source-IP Context API `response_outcome` fields.
- Attack Map popup: if the existing Attack Map popup already shows response status, update it to use canonical outcome labels and `ResponseOutcomeBadge`.
- Blocklist Manager: mark tracking-only entries clearly; remove or update any wording that implies firewall enforcement.
- Approvals Panel: show canonical `awaiting_approval`, `blocked_by_approval`, and `real-executed-after-approval` language using outcome data from the approval API.
- Playbooks Panel: update execution timeline to use canonical step outcome labels from the playbook execution API `response_outcome`.
- SOAR Metrics dashboard: distinguish observed, simulated, tracking-only, real, blocked, skipped, failed, awaiting approval, succeeded, `external_executed`, `tracking_recorded`, and `simulated` counts.
- Frontend tests for all updated surfaces.

**Excluded:**
- No Alert Details or SOAR Queue UI changes (those are Phase 8; see child change `add-response-outcome-alert-queue-ui`).
- No new shared components (those are Phase 7; see child change `add-response-outcome-frontend-components`).
- No backend changes.
- No migrations.
- No new API routes.
- No runtime behavior changes.
- No commits or pushes.

## Parent Roadmap Reference

This child change implements Phase 9 from `openspec/changes/clarify-soar-response-outcomes`. The parent remains the master roadmap. This child change is the active implementation spec for Phase 9 SOC context and remaining panel UI work only.

## Success Criteria

- SOC Command Center operational cards use canonical outcome mode/state counts from metrics endpoints.
- SOC Command Center incident workspace shows canonical outcomes for selected incident.
- Source-IP Context shows recent canonical outcomes using `ResponseOutcomeBadge` and `ResponseOutcomeSummary`.
- Attack Map popup uses canonical outcome labels where response status is displayed (or confirms no response status display exists).
- Blocklist Manager tracking-only entries are clearly marked; no enforcement implication.
- Approvals Panel uses canonical awaiting/blocked/real-executed language.
- Playbooks Panel execution timeline uses canonical step outcome labels.
- SOAR Metrics dashboard counts are grouped by canonical outcome fields.
- All Phase 7 shared components used; no inline label logic duplicated.
- Frontend tests pass with zero failures for all updated surfaces.
