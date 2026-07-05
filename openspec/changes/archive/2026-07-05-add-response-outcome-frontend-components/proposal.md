# Proposal: Response Outcome Frontend Components

## Problem

The parent roadmap `openspec/changes/clarify-soar-response-outcomes` defines canonical SOAR response outcome semantics across the full stack. Backend API work is complete through Phase 6. Frontend screens cannot yet render canonical outcomes because no shared components, label utilities, or display helpers exist. Every screen that needs to display outcome data would independently invent its own language, defeating the purpose of a canonical model.

## Goal

Implement Phase 7 of the parent roadmap: create shared frontend utilities and components for canonical outcome display so that subsequent screen-level changes (Phases 8 and 9) have a single source of truth for labels, badges, and formatting.

## Scope

**Included:**
- Shared label and color/tone utility for canonical execution modes, states, and reason codes.
- `ResponseOutcomeBadge` component displaying execution mode/state with correct labels.
- `ResponseOutcomeSummary` component showing selected action, decision source, execution actor, execution booleans, outcome summary, and related ids.
- Shared formatter that avoids vague standalone `executed` copy per parent Decision 7 UI language rules.
- UI handling for inferred/legacy outcomes (when `response_outcome` is null or has no events).
- Tests for all canonical modes, states, booleans, and reason codes.
- Accessibility assertions for badge text and summary text.

**Excluded:**
- No screen-level UI changes (those are Phases 8 and 9; see child changes `add-response-outcome-alert-queue-ui` and `add-response-outcome-soc-context-ui`).
- No backend changes.
- No migrations.
- No new API routes.
- No runtime behavior changes.
- No commits or pushes.

## Parent Roadmap Reference

This child change implements Phase 7 from `openspec/changes/clarify-soar-response-outcomes`. The parent remains the master roadmap. This child change is the active implementation spec for Phase 7 shared frontend component work only.

## Success Criteria

- All canonical label strings match parent Decision 7 UI language exactly.
- `ResponseOutcomeBadge` handles every `execution_mode`/`execution_state` combination without crashing.
- `ResponseOutcomeSummary` renders null outcome gracefully with a clear no-history state.
- No component uses standalone `executed` as copy.
- Tests cover all canonical enum values, all three execution booleans, null outcome, inferred legacy outcome, and accessibility text.
- Components are importable by Phase 8 and Phase 9 screen-level changes without modification.
