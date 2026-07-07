This spec's authoring step (creating proposal.md/design.md/tasks.md/specs/) makes no code changes. Section 1 reflects the verification work completed to write this spec. Section 2 lists this same spec's own future implementation work — owned here, not deferred to another child spec — to be executed only in a separate, later, explicitly-requested implementation pass.

## 1. Verification (completed as part of writing this spec)

- [x] 1.1 Confirm the exact ingest-time call order of `enqueue_committed_alerts` vs. `_create_playbook_executions_for_alerts` across all five `routes/ingest_routes.py` call sites, and confirm the queue path currently decides before playbook matching runs.
- [x] 1.2 Confirm `core.playbook_store.create_pending_playbook_execution_once`'s existing `(playbook_id, alert_id)` dedup index and its already-present `decision_id`/`soar_correlation_id` parameters, suitable for reuse in chaining.
- [x] 1.3 Confirm `soar_response_decisions.parent_soar_correlation_id` already exists and is already populated (for a different parent/child relationship) by `engines/soar_playbook_orchestrator.py`.
- [x] 1.4 Confirm `playbook_executions.incident_id` is realistically always `NULL` in the current flow, and confirm `routes/incident_routes.build_readonly_incident_timeline` already compensates via an alert-id-based fallback — meaning chained executions need no new timeline logic as long as they share their parent's `alert_id`.
- [x] 1.5 Confirm dead-letter capture (`core/dead_letter_store.py`) and the canonical outcome ledger already unify both the queue and playbook paths, so no auditing unification work is needed by this spec.
- [x] 1.6 Confirm approval gates (`approval_requests`) are already scoped per-`playbook_execution_id`, already tolerating multiple independent executions per alert today.
- [x] 1.7 Confirm no chaining action exists today in `engines/playbook_registry.py`'s action vocabulary.
- [x] 1.8 Confirm `core.ip_helpers.determine_response_action`'s exact three-band reputation-score logic and its call sites in `engines/detection_engine.py`/`engines/correlation_engine.py`.
- [x] 1.9 Confirm `soar-automation-path-consolidation-decision`'s Acceptance Criterion 1 (`block_ip` protected-target parity) is already satisfied by `playbook-engine-correctness-hardening`, by re-checking `engines/playbook_step_executor.py` directly.
- [x] 1.10 Confirm no freeze/deprecation notice exists yet in `engines/soar_enqueue_orchestrator.py` or `engines/soar_action_worker.py`.
- [x] 1.11 Build the coverage map: cross-reference the queue's three reputation bands against `core-playbook-pack-v1`'s five designed playbooks' trigger configs, and identify the one severity-floor gap on the `block_ip` band.
- [x] 1.12 Document the chaining model, loop-prevention design, cross-path precedence guard, staged retirement sequence, and non-goals in `design.md`.

## 2. Implementation (this spec's own future work — not started, not part of this authoring step)

- [ ] 2.1 Add a migration extending `playbook_executions` with `parent_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL` and `chain_depth INTEGER NOT NULL DEFAULT 0`, plus an index on `parent_execution_id`; update `schema.sql`.
- [ ] 2.2 Add `trigger_playbook` to `engines/playbook_registry.py`'s `CORE_ACTIONS`, and add the definition-time self-reference rejection rule to `validate_playbook_steps`.
- [ ] 2.3 Implement `trigger_playbook` dispatch in `engines/playbook_step_executor.py`: special-case it in the step loop, reuse `create_pending_playbook_execution_once` for the child insert, set `parent_execution_id`/`chain_depth`, and link the child's canonical decision via `parent_soar_correlation_id` using the existing `create_and_link_playbook_execution_decision` entry point.
- [ ] 2.4 Implement the depth cap (`MAX_CHAIN_DEPTH`) and bounded ancestor-cycle walk, both fail-closed with defined error codes.
- [ ] 2.5 Add the `exclude_alert_ids` parameter to `engines/soar_enqueue_orchestrator.enqueue_committed_alerts` and the `"playbook_precedence"` skip path.
- [ ] 2.6 Reorder the five `routes/ingest_routes.py` call sites so playbook orchestration runs before queue enqueue, and thread the matched-alert-id set between them.
- [ ] 2.7 Add the freeze/deprecation notice (referencing the consolidation decision) to `engines/soar_enqueue_orchestrator.py` and `engines/soar_action_worker.py`.
- [ ] 2.8 Resolve or explicitly accept-and-record the coverage map's severity-floor gap on the `block_ip` band (a `core-playbook-pack-v1` content decision, tracked here as a dependency, not resolved by this spec's engine work).
- [ ] 2.9 Add tests: registry self-reference rejection, executor dispatch/linkage/depth-cap/ancestor-cycle cases, parent-success-independent-of-child-outcome, orchestrator precedence-guard cases (skip when matched, unchanged when not matched).
- [ ] 2.10 Run the full existing playbook, queue, and ingest test suites and confirm zero regressions for every alert and playbook that predates this capability.

## Safety Boundaries (for this authoring step)

- [x] Creating this spec's proposal/design/tasks/spec files makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] No new playbook content, scheduler work, UI redesign, workflow builder, new dependency, or destructive queue removal is introduced by this spec.
- [x] Do not commit.
- [x] Do not push.
