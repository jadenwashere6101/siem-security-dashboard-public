This spec's authoring step (creating proposal.md/design.md/tasks.md/specs/) makes no code changes. Section 1 reflects the verification work completed to write this spec. Section 2 lists this same spec's own future implementation work — owned here, not deferred to another child spec — to be executed only in a separate, later, explicitly-requested implementation pass.

## 1. Verification (completed as part of writing this spec)

- [x] 1.1 Confirm `engines/playbook_step_executor.py` reads `params` verbatim from stored step JSON with no alert-field substitution.
- [x] 1.2 Confirm `execution["alert_id"]` is available to the executor but is not used to populate step `params` (only for outcome linkage via `_resolve_playbook_alert_source_ip`).
- [x] 1.3 Confirm `engines/playbook_engine.py` loads full alert rows for trigger matching, establishing the field surface available for binding.
- [x] 1.4 Confirm `engines/playbook_registry.py` does not validate `params` at definition save time today.
- [x] 1.5 Confirm no templating or binding helper exists anywhere in playbook modules.
- [x] 1.6 Document parameter syntax, alert field surface, validation rules, security boundaries, missing-field behavior, static vs dynamic semantics, and future extensibility in `design.md`.

## 2. Implementation (this spec's own future work — not started, not deferred to another spec)

- [x] 2.1 Implement a parameter-binding resolver that recognizes `{{alert.<field>}}` (and optionally `{{execution.<field>}}`) expressions and resolves them against the execution's alert row.
- [x] 2.2 Integrate resolution into `engines/playbook_step_executor.py` immediately before action validation and adapter dispatch.
- [x] 2.3 Add definition-time validation in `engines/playbook_registry.py` for binding syntax and allowed field names.
- [x] 2.4 Ensure `require_unprotected_target` and all adapter dispatches receive resolved (concrete) values only.
- [x] 2.5 Add tests: static params unchanged; dynamic `block_ip` targets triggering alert IP; protected IP rejected post-resolution; unknown field rejected at save time; missing nullable field fails at execution time.
- [x] 2.6 Run the full existing playbook test suite and confirm no regressions for static-only definitions.

## Safety Boundaries (for this authoring step)

- [x] Creating this spec's proposal/design/tasks/spec files makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] No playbook content, new actions, branching, chaining, or enrichment work is introduced by this spec.
- [x] Do not commit.
