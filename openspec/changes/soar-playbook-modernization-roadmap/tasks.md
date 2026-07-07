## 1. Overall Goal

Track the ordered child-spec roadmap for modernizing the SOAR playbook subsystem, as identified by the `audit-soar-playbook-library` audit. Each item below becomes its own separate, focused child OpenSpec change when work on it begins — this parent tracks sequencing and completion only, with no implementation detail.

## 2. Child-Spec Roadmap (ordered)

- [x] 2.1 SOAR Automation Path Consolidation Decision
  - Dependency: none — unblocks everything below.
  - Verified 2026-07-06: decision-only spec, fully complete per its own scope; archived.
- [x] 2.2 Playbook Engine Correctness Hardening
  - Dependency: soft dependency on 2.1 (finalize protected-target guard placement once the path decision is made).
  - Verified 2026-07-06: all three fixes (block_ip protected-target check, canonical action vocabulary incl. `notify_teams`, `attempt_count` increment in stale recovery) confirmed present in code and covered by passing tests.
  - Updated 2026-07-07: the child spec's sole remaining task (2.9, landing the fix as three separate revertible commits) was waived as not applicable after merge — the fix already landed as a single commit and commit granularity cannot be rewritten retroactively. Closed by project decision based on delivered, tested capability rather than commit structure; archived.
- [x] 2.3 Playbook Schedules Resolution
  - Dependency: none — independent, can run in parallel with any other item.
  - Verified 2026-07-06: schedule routes, store functions, and frontend tab fully retired in code; `playbook_schedules` table intentionally left as inert legacy schema per the spec's own design; archived.
- [x] 2.4 Dynamic Playbook Parameter Binding
  - Dependency: 2.2 (hardened executor and canonical action vocabulary before adding resolution semantics).
  - Verified 2026-07-06: `engines/playbook_param_binding.py` implemented and wired into registry + executor; tests passing; archived.
- [x] 2.5 Core Playbook Pack v1
  - Dependency: 2.1 (target the decided execution path), 2.2 (build on hardened primitives), and 2.4 (per-execution parameter binding for containment and alert-specific notifications).
  - Verified 2026-07-06: `core/core_playbook_pack_v1.py` defines and validates all five playbooks with a `seed_core_playbook_pack_v1` loader; tests passing. Note: the seed function has no caller in application startup today — seeding a live database is an explicit, separate operational step, not automatic; archived.
- [x] 2.6 Conditional Branching Primitive
  - Dependency: 2.2 (hardened base before adding new execution semantics).
  - Verified 2026-07-06: `engines/playbook_branch_conditions.py` implemented, executor/registry extended, tests passing; archived.
- [ ] 2.7 Ad Hoc Trigger & Enrichment Step
  - Dependency: 2.2 (hardened base); soft dependency on 2.5 (a real playbook to invoke/enrich).
  - Verified 2026-07-06: design-only (11/17 tasks); no manual-execution route or `enrich_context` action exists in code. Not implemented.
- [ ] 2.8 Incident Evidence Collection & Automated Case Enrichment
  - Dependency: soft dependency on 2.7 (reuse enrichment-snapshot shape).
  - Verified 2026-07-06: design-only (14/21 tasks); no `evidence_snapshot` column or `incident_store` changes exist in code. Not implemented.
- [x] 2.9 Playbook Chaining & Cross-Path Orchestration Layer
  - Dependency: 2.1, 2.2, 2.5, 2.6 — sequenced last on purpose.
  - Verified 2026-07-06: `trigger_playbook` action, parent/child linkage columns, depth-cap/cycle guards, and the ingest-time precedence guard (`exclude_alert_ids`/`playbook_precedence`) all confirmed present in code; freeze notices present in both queue modules; full relevant test suite passing; archived.

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
