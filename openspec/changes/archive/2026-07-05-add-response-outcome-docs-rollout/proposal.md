# Proposal: Response Outcome Docs and Rollout

## Problem

The parent roadmap `openspec/changes/clarify-soar-response-outcomes` defines canonical SOAR response outcome semantics across the full stack. Phases 1–11 cover schema, backend, API contracts, UI, retention, and end-to-end tests. Phases 12 and 13 remain: architecture documentation, wording guides, runbooks, interview notes, and production rollout/rollback checkpoints. Without these, the canonical model has no operator documentation, no verified rollout sequence, and no documented rollback order for production incidents.

## Goal

Implement Phases 12 and 13 of the parent roadmap:
- Update SOAR architecture documentation with canonical decision/outcome-event model definitions.
- Add a dashboard wording guide for all canonical outcome labels.
- Document schema additions and rollback behavior.
- Document backfill dry-run/write-mode strategy and compatibility behavior for legacy records.
- Document real execution safety boundaries.
- Add analyst runbooks explaining how to answer the primary outcome question.
- Add interview notes summarizing why canonical outcomes were introduced.
- Update OpenSpec task status after each completed implementation slice.
- Verify schema-only deployment can be rolled back.
- Verify backend dual-write can be disabled without changing legacy behavior.
- Verify API consumers can fall back to legacy fields while canonical fields are unavailable.
- Verify UI can render inferred legacy outcomes.
- Verify production rollout order and rollback order.
- Document known risks and operator-facing mitigations before enabling canonical UI in production.

## Scope

**Included:**
- SOAR architecture documentation update.
- Dashboard wording guide for canonical outcome labels (all modes, states, booleans, reason codes).
- Schema additions and rollback behavior documentation.
- Backfill dry-run/write-mode strategy and legacy compatibility documentation.
- Real execution safety boundaries documentation (firewall dry-run limitation, guarded notification adapters).
- Analyst runbooks: how to answer the primary outcome question from the UI and API.
- Interview notes: why canonical outcomes were introduced, how they reduce ambiguity.
- OpenSpec task status updates in the parent roadmap after each completed phase.
- Rollout checkpoint verification: schema-only rollback, dual-write disable, API legacy fallback, UI inferred legacy outcomes.
- Production rollout order and rollback order documentation.
- Known risks and operator-facing mitigations documentation.

**Excluded:**
- No code changes (no migrations, no API route changes, no UI changes, no new tests).
- No changes to existing phase implementations (Phases 1–11).
- No new canonical tables or routes.
- No runtime behavior changes.
- No real firewall enforcement.
- No commits or pushes.

## Parent Roadmap Reference

This child change implements Phases 12 and 13 from `openspec/changes/clarify-soar-response-outcomes`. The parent remains the master roadmap. This child change is the active implementation spec for documentation and rollout checkpoint work only.

## Success Criteria

- SOAR architecture documentation is updated and accurate.
- Dashboard wording guide covers all canonical outcome modes, states, booleans, and reason codes.
- Schema rollback behavior is documented and confirmed safe.
- Backfill dry-run/write-mode strategy is documented with compatibility notes.
- Analyst runbook answers the primary outcome question step-by-step.
- Interview notes are complete.
- All six rollout checkpoints are verified and documented.
- Production rollout and rollback orders are documented.
- Known risks and mitigations are documented.
- OpenSpec task status in the parent roadmap is current.
