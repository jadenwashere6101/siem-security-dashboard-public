## 1. Overall Goal

Track the ordered child-spec roadmap for modernizing the SOAR playbook subsystem, as identified by the `audit-soar-playbook-library` audit. Each item below becomes its own separate, focused child OpenSpec change when work on it begins — this parent tracks sequencing and completion only, with no implementation detail.

## 2. Child-Spec Roadmap (ordered)

- [ ] 2.1 SOAR Automation Path Consolidation Decision
  - Dependency: none — unblocks everything below.
- [ ] 2.2 Playbook Engine Correctness Hardening
  - Dependency: soft dependency on 2.1 (finalize protected-target guard placement once the path decision is made).
- [ ] 2.3 Playbook Schedules Resolution
  - Dependency: none — independent, can run in parallel with any other item.
- [ ] 2.4 Dynamic Playbook Parameter Binding
  - Dependency: 2.2 (hardened executor and canonical action vocabulary before adding resolution semantics).
- [ ] 2.5 Core Playbook Pack v1
  - Dependency: 2.1 (target the decided execution path), 2.2 (build on hardened primitives), and 2.4 (per-execution parameter binding for containment and alert-specific notifications).
- [ ] 2.6 Conditional Branching Primitive
  - Dependency: 2.2 (hardened base before adding new execution semantics).
- [ ] 2.7 Ad Hoc Trigger & Enrichment Step
  - Dependency: 2.2 (hardened base); soft dependency on 2.5 (a real playbook to invoke/enrich).
- [ ] 2.8 Incident Evidence Collection & Automated Case Enrichment
  - Dependency: soft dependency on 2.7 (reuse enrichment-snapshot shape).
- [ ] 2.9 Playbook Chaining & Cross-Path Orchestration Layer
  - Dependency: 2.1, 2.2, 2.5, 2.6 — sequenced last on purpose.

## 3. Deferred for now

Not scheduled as child specs; revisit only if circumstances change (see rationale in the audit roadmap review).

- Rollback / compensating actions
- Generic pluggable action framework
- Reusable investigation stages
- Cross-execution incident timeline UI

## Safety Boundaries

- [x] This parent change contains no implementation steps or code changes.
- [x] Do not modify any file under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] Do not create child implementation specs as part of this change.
- [x] Do not commit.
