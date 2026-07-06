This is a decision/specification-only child spec. No code, schema, or playbook content is implemented here. Section 1 reflects the analysis performed to reach the decision; Section 2 lists the boundary-enforcement tasks that belong to a later, separately-scoped enforcement child spec — they are listed here for traceability only and remain unchecked until that future spec executes them.

## 1. Decision Analysis (completed as part of this spec)

- [x] 1.1 Re-confirm both paths' current trigger mechanisms, execution models, and safety enforcement directly against the code (`engines/soar_enqueue_orchestrator.py`, `engines/soar_action_worker.py`, `core/response_action_queue_store.py`, `engines/soar_playbook_orchestrator.py`, `engines/playbook_step_executor.py`, `core/soar_protected_targets.py`).
- [x] 1.2 Document the concrete risk of leaving both paths ambiguous.
- [x] 1.3 Evaluate merge / permanently-separate / retire-playbook-engine / retire-queue-path-authoritative-playbook-engine against capability ceiling, safety-maintenance cost, sunk engineering value, and migration risk.
- [x] 1.4 Record one exact decision with rationale.
- [x] 1.5 Define implementation boundaries for the later enforcement spec (in scope vs. out of scope).
- [x] 1.6 Define acceptance criteria for considering the decision fully enforced.
- [x] 1.7 Define a validation plan for confirming enforcement later.

## 2. Deferred Enforcement Tasks (belong to a future, separately-scoped child spec — NOT executed by this spec)

- [ ] 2.1 Add a freeze/deprecation notice (docstring/comment only) to `engines/soar_enqueue_orchestrator.py` and `engines/soar_action_worker.py` referencing this decision.
- [ ] 2.2 Confirm playbook `block_ip` enforces `soar_protected_targets.require_unprotected_target` (tracked in the `Playbook Engine Correctness Hardening` child spec; this task only confirms it before coverage migration proceeds).
- [ ] 2.3 Produce a coverage map of every alert type currently routed to the queue path via `response_action`, and confirm each has or will have an equivalent playbook.
- [ ] 2.4 Remove the queue path's ingest-time trigger call (`enqueue_committed_alerts`) once 2.2 and 2.3 are both satisfied.
- [ ] 2.5 Re-run the validation plan below once 2.1–2.4 are complete.

## Safety Boundaries

- [x] Do not modify any file under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] Do not create any new playbooks, engine features, branching, schedules, or evidence-collection work as part of this spec.
- [x] Do not change `response_actions_queue` or `playbook_definitions` schema.
- [x] Do not commit.
