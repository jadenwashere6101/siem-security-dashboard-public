## Context

The UI already receives mode-aware execution data and renders accurate badges, but adjacent Playbooks copy hardcodes “simulation.” Timeline resume copy has the same defect. Genuine read-only enrichment is recorded with simulation/no-execution metadata, and source-controlled worker launch/service templates make safety claims that do not match live precedence. Mac is the only source of truth for durable code, tests, units, and documentation.

## Goals / Non-Goals

**Goals:**

- Establish one normalized mode vocabulary across Playbooks surfaces and backend presentation metadata.
- Correct every audit-identified misleading label, including Teams qualifier copy.
- Make environment loading secret-safe and configuration precedence deterministic and testable.
- Provide deployment artifacts and acceptance checks the VM AI can execute safely.

**Non-Goals:**

- Changing which providers are enabled on production, enabling firewall enforcement, or promoting legacy advisory actions.
- Mutating VM `.env`, queues, dead letters, or approvals.
- Committing, pushing, or deploying without separate authorization.

## Decisions

1. **Normalize mode once.** Introduce/reuse a helper that maps `mode` and `execution_mode` into `real`, `simulation`, `read_only`, or `unknown`. Components consume the normalized value; missing mode never defaults to real.
2. **Describe workflow state separately from mode.** Primary copy says execution/completed/failed/paused/resumed/retry/resume; mode appears as a qualified badge or phrase. This avoids calling genuine orchestration or DB reads simulations.
3. **Represent enrichment as read-only executed work.** Backend metadata must distinguish “no external side effect” from “not executed.” Existing historical records need no rewrite; frontend remains backward-compatible.
4. **Use deterministic environment loading.** Inspect actual wrapper/unit composition and select one precedence contract. Prefer systemd-native `EnvironmentFile` plus explicit overrides and a launcher that does not source `.env`; if shell loading remains necessary, use a parser that treats values as data, never executable shell. Unit descriptions must state actual behavior.
5. **Test contracts, not strings alone.** Add table-driven UI tests for modes and states, backend outcome tests for enrichment, and source-level/temporary-unit tests for precedence and secrets containing shell metacharacters.

## Risks / Trade-offs

- [Older API records lack mode] → render neutral “execution” language and an Unknown badge.
- [Changing enrichment metadata affects metrics] → document the semantic correction and test aggregations that consume `executed` or mode.
- [Launcher changes affect all secrets] → test representative whitespace, quotes, `$`, `#`, and shell metacharacters without real credentials.
- [Unit fix accidentally disables approved providers] → deployment checklist captures sanitized pre/post effective environments and provider readiness.

## Migration Plan

1. Add normalization and regression tests, then update Playbooks/timeline/Teams copy.
2. Correct enrichment metadata and dependent tests/metrics.
3. Reproduce environment precedence locally, update launcher/unit templates and runbooks, and test the kill-switch contract.
4. Hand source diff and deployment checklist to the VM AI; deploy only after commit/push authorization and a clean-VM check.
5. Roll back through the normal Mac commit/deploy path; restore prior build/units and verify effective provider guards.

## Open Questions

- Which exact response payload fields cover all historical execution records?
- Does any metric intentionally count read-only enrichment as simulated work?
- Can the wrapper be removed entirely from both worker units without losing required setup?
