## Why

The SOAR playbook audit (`audit-soar-playbook-library`) found a mature execution engine with no real playbook content, two independently-triggered automation paths with inconsistent safety guarantees, and a handful of specific correctness gaps. That audit's follow-on roadmap review determined the minimum set of properly scoped child implementation specs needed to address the findings. There is currently no single place tracking that multi-spec effort as it moves from decision to hardening to content to capability work. This parent roadmap is that single coordination point.

## What Changes

- Add a lightweight, non-implementing parent change that lists the nine child specs identified for SOAR playbook modernization, in dependency order, with a checkbox per child spec to track completion.
- Record the deferred items (rollback/compensating actions, generic pluggable action framework, reusable investigation stages, cross-execution incident timeline UI) so they remain visible without being scheduled.
- No design detail, no implementation steps, and no code/schema changes are included here — each checked-off item corresponds to its own separate, focused child OpenSpec change created later.

## Capabilities

### New Capabilities
- `soar-playbook-modernization-roadmap`: tracks the ordered child-spec roadmap for SOAR playbook modernization and the audit-only/no-implementation boundary of this parent change.

### Modified Capabilities
(none — this change does not alter behavior of any existing capability)

## Impact

- **Affected code:** none (coordination artifact only; no files under `engines/`, `core/`, `routes/`, `migrations/`, or `frontend/` are touched).
- **Affected artifacts:** adds `openspec/changes/soar-playbook-modernization-roadmap/` as a new, unimplemented parent change.
- **Downstream effect:** each roadmap checkbox is expected to become its own child OpenSpec change (e.g., `soar-automation-path-consolidation`, `playbook-engine-correctness-hardening`, etc.). None of that child work is authorized or started by this change.
- **Dependencies:** the `audit-soar-playbook-library` change (source of the findings and roadmap ordering this tracks).
