# Proposal: SOAR Playbook Engine Foundation

## Why

The SOAR queue, worker, executor, approval system, incident layer, and protected-target policy
are all built and tested. Detection alerts are enqueued post-commit and routed through a safe
simulation path. But the system has no concept of a playbook.

There is no way to declare "when a `password_spraying` alert fires with severity HIGH and a
reputation score above 80, trigger this named sequence of steps." Every response in the
current system is a single flat action decided at detection time by `determine_response_action()`.
There is no trigger matching, no multi-step definition, and no execution state record beyond
the queue row itself.

A playbook foundation is the necessary precondition before any step execution can be built:
- Without a `playbook_definitions` table there is no persistent, operator-configurable source
  of truth for playbook trigger conditions and step lists.
- Without a `playbook_executions` table there is no per-run record to checkpoint, audit, or
  resume on crash.
- Without a trigger matching engine there is no mechanism for deciding which, if any, playbooks
  apply to a newly committed alert.

Phase 2D (step executor) depends on all three. This change builds the foundation and deliberately
stops before wiring step execution.

---

## What Changes

- Schema addition: `playbook_definitions` table — trigger config and step list per playbook.
- Schema addition: `playbook_executions` table — one row per triggered run with status,
  alert link, incident link, and step checkpoint columns.
- New `core/playbook_store.py` — DB-backed CRUD helpers for definitions and executions.
- New `engines/playbook_engine.py` — trigger matching only. Given a committed alert_id,
  returns the list of enabled definitions whose trigger_config matches. No step execution.
- New `engines/playbook_registry.py` — defines the recognized set of action names for step
  validation. Provides no handlers — step wiring is Phase 2D.
- New `tests/test_playbook_store.py` — store helper and schema constraint tests.
- New `tests/test_playbook_engine.py` — trigger matching unit tests. All DB-independent via
  direct calls to the pure `_evaluate_trigger` function.

No step execution. No ingest, detection, or correlation modifications. No changes to existing
tables, routes, or frontend. No daemon, scheduler, or adapter calls. No playbook runs execute
any action. No call site wires the engine into ingest routes — that is a separate change.

---

## Capabilities

### New Capabilities

- `soar-playbook-definitions`: Stores named, operator-configurable playbook definitions in a
  DB table. Each definition carries a trigger_config (alert_type, min_severity, source,
  correlation_flag, reputation_score_min) and a steps array. Definitions can be
  enabled/disabled without a deploy.

- `soar-playbook-executions`: Records one execution row per triggered playbook run. Tracks
  status (`pending`, `running`, `success`, `failed`, `abandoned`), alert_id, incident_id,
  `last_completed_step` checkpoint, and a `steps_log` JSONB array. These columns are
  scaffolded now so Phase 2D can write to them without a schema migration.

- `soar-trigger-matching`: Given a committed alert (by alert_id), evaluates all enabled
  playbook definitions and returns those whose trigger_config matches. Trigger fields use
  AND logic: all specified fields must match. Unspecified fields match any alert. Matching
  is implemented as a pure function (`_evaluate_trigger`) with no side effects.

### Modified Capabilities

None. The existing SOAR queue, worker, approval system, incident layer, and adapter behavior
are unchanged. No existing test file is modified.

---

## Impact

- Schema: two new tables, one index per table. No existing tables or columns touched.
- Store: one new module (`core/playbook_store.py`). No existing stores modified.
- Engine: one new module (`engines/playbook_engine.py`). Imports from the store and from
  `engines/soar_errors.py` only. Does not import from any detection, correlation, or ingest
  module.
- Registry: one new module (`engines/playbook_registry.py`). Standalone, no imports from
  existing engine modules.
- Tests: two new test files. All existing tests pass unchanged.
