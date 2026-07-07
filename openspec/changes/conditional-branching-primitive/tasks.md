This spec's authoring step (creating proposal.md/design.md/tasks.md/specs/) makes no code changes. Section 1 reflects the verification work completed to write this spec. Section 2 lists this same spec's own future implementation work — owned here, not deferred to another child spec — to be executed only in a separate, later, explicitly-requested implementation pass.

## 1. Verification (completed as part of writing this spec)

- [x] 1.1 Confirm `engines/playbook_step_executor.py`'s `_process_steps` loop (`for index, step in enumerate(steps[start_index:], start=start_index)`) always advances by exactly one index, with no field or mechanism to redirect it.
- [x] 1.2 Confirm `_resume_progress` and `_step_already_succeeded_in_log` assume strict ascending index order with no "skipped by branch" state in the schema.
- [x] 1.3 Confirm `engines/playbook_registry.py`'s `validate_playbook_steps` validates each step independently, with no concept of step order, labels, or cross-step references.
- [x] 1.4 Confirm `require_approval` denial/expiry (`_process_awaiting_approval_execution`) unconditionally finalizes the execution as failed today, with `APPROVAL_TERMINAL_BEHAVIORS` limited to `{"fail"}`.
- [x] 1.5 Confirm `engines/playbook_param_binding.py`'s `ALERT_BINDING_FIELDS` allow-list and `engines/playbook_engine.py`'s `SEVERITY_RANK` table are suitable to reuse as the condition field surface, avoiding a second field allow-list.
- [x] 1.6 Confirm no existing labeling, jump, or branch concept exists anywhere in playbook modules.
- [x] 1.7 Document the branch step shape, condition sources/operators, validation rules, fail-closed execution behavior, auditability, and the opt-in approval-branch extension in `design.md`.

## 2. Implementation (this spec's own future work — not started, not part of this authoring step)

- [ ] 2.1 Add a new module (e.g. `engines/playbook_branch_conditions.py`) that evaluates `alert`/`previous_step`/`approval`-sourced conditions, reusing `ALERT_BINDING_FIELDS` and `SEVERITY_RANK` rather than redefining either.
- [ ] 2.2 Extend `engines/playbook_registry.py`'s `validate_playbook_steps` with all branch validation rules: shape, condition source/field/op/value typing, label uniqueness, forward-only target resolution; extend `APPROVAL_TERMINAL_BEHAVIORS` to `{"fail", "branch"}`.
- [ ] 2.3 Convert `engines/playbook_step_executor.py`'s `_process_steps` loop from a fixed `enumerate` iterator to an explicit, redirectable index cursor, preserving byte-for-byte behavior when no `branch` steps are present.
- [ ] 2.4 Implement `branch` step evaluation: append the evaluation entry, append `"skipped"` entries for every step jumped over, and redirect the cursor to the resolved target index.
- [ ] 2.5 Implement the `on_denied`/`on_expired: "branch"` continuation path in `_process_awaiting_approval_execution`, leaving the default (`"fail"`) path unchanged.
- [ ] 2.6 Add tests: registry validation (all rules, positive and negative), executor branch-taken/fall-through/goto_false/skip-logging/outcome-event cases, all fail-closed cases, and the approval-branch interaction.
- [ ] 2.7 Run the full existing playbook-related test suite and confirm zero regressions for playbook definitions containing no `branch` steps.

## Safety Boundaries (for this authoring step)

- [x] Creating this spec's proposal/design/tasks/spec files makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] No playbook content, new adapters, loops, scripting, or chaining is introduced by this spec.
- [x] Do not commit.
