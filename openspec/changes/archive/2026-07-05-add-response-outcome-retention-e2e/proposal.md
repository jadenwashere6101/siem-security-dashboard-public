# Proposal: Response Outcome Retention and API Integration Tests

## Problem

The parent roadmap `openspec/changes/clarify-soar-response-outcomes` defines canonical SOAR response outcome semantics across the full stack. Phases 1–9 cover schema, backend helpers, backfill, runtime wiring, API contracts, and UI components. Phases 10 and 11 remain: retention/archive/reporting verification and API/read-model integration traceability tests. Without these, the canonical model has no verified data lifecycle policy and no cross-surface regression harness that proves the primary analyst question can be answered from canonical API responses: "What happened, what response was selected, what playbook ran, and was anything actually executed?"

## Goal

Implement Phases 10 and 11 of the parent roadmap:
- Define and verify the retention window and archive criteria for canonical decisions and outcome events.
- Add a reporting query that answers the primary analyst question.
- Verify query performance at representative event volume.
- Verify metrics either include archived summaries or document their live retention window through additive retention metadata.
- Add API/read-model integration tests for every major canonical lifecycle shape: observed-only, simulated queue, manual tracking-only, playbook simulation, approval pending, approval denied/expired, notification simulated, guarded real notification, and real-capable blocked/fail-closed.
- Add regression tests proving simulated actions are never shown as real executed, and tracking-only entries are never shown as firewall enforcement.
- Verify SOC Command Center and Source-IP Context show the same canonical outcome facts.

## Scope

**Included:**
- Define and document default retention window for canonical decisions and outcome events.
- Define and document archive criteria for append-only outcome events (what is preserved, what is summarized/dropped).
- Add a reporting query or helper that answers the primary analyst question from canonical tables.
- Performance verification: confirm latest-outcome queries perform acceptably with representative event volume.
- Verify metrics either include archived summaries or clearly document their live retention window through additive retention metadata.
- API/read-model integration test: observed-only alert lifecycle.
- API/read-model integration test: detection-selected simulated queue action.
- API/read-model integration test: manual tracking-only blocklist action.
- API/read-model integration test: playbook simulation step sequence.
- API/read-model integration test: playbook awaiting approval.
- API/read-model integration test: approval denied/expired blocking execution.
- API/read-model integration test: notification simulated delivery.
- API/read-model integration test: guarded real notification success with seeded real execution evidence.
- API/read-model integration test: real-capable notification blocked/fail-closed path.
- API/read-model integration test: Source-IP Context and SOC Command Center metrics showing same canonical facts.
- Regression test: simulated actions never shown as real executed.
- Regression test: tracking-only blocklist entries never shown as firewall enforcement.

**Excluded:**
- No new canonical tables, migrations, or API routes.
- No changes to existing phase implementations (Phases 1–9), except additive retention metadata on metrics responses to document the live retention boundary.
- No frontend UI changes.
- No runtime behavior changes.
- No real firewall enforcement.
- No commits or pushes.

## Parent Roadmap Reference

This child change implements Phases 10 and 11 from `openspec/changes/clarify-soar-response-outcomes`. The parent remains the master roadmap. This child change is the active implementation spec for retention/archive/reporting verification and API/read-model integration test work only.

## Success Criteria

- Retention window and archive criteria documented and agreed.
- Reporting query returns correct data answering the primary analyst question.
- Latest-outcome query performance acceptable at representative volume.
- Metrics documentation is accurate about live retention window.
- All twelve API/read-model integration and regression tests pass with zero failures.
- Regression tests are deterministic and cannot be made to pass by relabeling simulated work as real or tracking-only as enforcement.
