## Executive Summary

Today the SOAR playbook executor (`engines/playbook_step_executor.py`) runs a definition's `steps` list strictly in order: index 0, then 1, then 2, and so on, with no way for a playbook to make a runtime decision. The only existing control-flow primitives are `on_failure: "abort" | "continue"` (per-step, decided before execution) and the `require_approval` gate (pauses the whole execution, then either resumes linearly or hard-fails on denial/expiry). Neither lets a playbook choose *which* step runs next based on the triggering alert's fields, a prior step's outcome, or an approval decision.

This spec defines the smallest possible addition that closes that gap: a single new step action, `branch`, that evaluates one structured condition against an already-established data surface (the alert-field binding surface from `dynamic-playbook-parameter-binding`, the current step's recorded outcome, or the most recent approval decision) and jumps forward to a named label, or falls through to the next step. No loops, no recursion, no expression language, no new adapters, no schema changes. It is designed to slot into the existing linear executor with one bounded, well-audited control-flow addition, not a rewrite.

## Current Executor Audit

Re-verified directly against the current code (including the in-progress, uncommitted `dynamic-playbook-parameter-binding` implementation already present in the working tree, which this spec builds on):

1. **`engines/playbook_engine.py`** (`match_playbooks` / `_fetch_alert` / `_evaluate_trigger`) — read-only trigger matching. Loads a fixed set of alert columns (`id`, `alert_type`, `severity`, `source_ip`, `source`, `source_type`, `message`, `status`, `country`, `city`, `latitude`, `longitude`, `reputation_score`, `reputation_label`, `reputation_source`, `reputation_summary`, `response_action`, `response_status`, `created_at`) and AND-evaluates a flat `trigger_config` dict against them. Defines `SEVERITY_RANK` (`low`=1 … `critical`=4) for ordinal severity comparison. This module has no concept of step order — it decides *whether* a playbook runs, never *which step* runs.

2. **`engines/playbook_param_binding.py`** (new, uncommitted) — resolves `{{alert.<field>}}` / `{{execution.<field>}}` whole-value expressions in step `params` at execution time, against `ALERT_BINDING_FIELDS`/`EXECUTION_BINDING_FIELDS` allow-lists, via `resolve_step_params`. Fails closed (`PlaybookParamBindingError`) on unknown fields, missing alert context, or null field values. This is the first place the engine already does structured, validated, allow-listed field lookups against the alert — this spec reuses that surface rather than inventing a second one.

3. **`engines/playbook_registry.py`** (`validate_playbook_steps`) — the only definition-time gate. Validates `action` is known, `require_approval` shape (`risk_level`, `expires_in_minutes`, `on_denied`/`on_expired` restricted to `APPROVAL_TERMINAL_BEHAVIORS = {"fail"}`), `on_failure` in `{"abort", "continue"}`, and (via the new `validate_step_param_bindings`) param binding syntax. It does not know about step order, labels, or jumps — `steps` is validated as an unordered list of independently-valid dicts.

4. **`engines/playbook_step_executor.py`** (`_process_steps`) — the actual execution loop:
   ```python
   for index, step in enumerate(steps[start_index:], start=start_index):
       ...
       entry = _simulate_step(conn, step, index, timestamp, execution)
       steps_log.append(entry)
       if entry["status"] == "success":
           last_completed_step = index
           ...
           continue
       failed = True
       ...
       on_failure = step.get("on_failure", "abort") if isinstance(step, dict) else "abort"
       if on_failure != "continue":
           break
   ```
   This is a Python `for … enumerate(...)` loop with no branch target — the next iteration is *always* `index + 1`. `_resume_progress` (crash/resume) and `_step_already_succeeded_in_log` (dedup) both assume steps execute in strict ascending index order with no gaps except ones the loop itself decides to `break` out of. `require_approval` steps pause the whole execution (`awaiting_approval`) and, on resume, restart the same `for` loop at `gate_index + 1` — again strictly sequential.

5. **`core/playbook_store.py`** — persistence only. `steps_log` is a JSON array keyed by `step_index`; `last_completed_step` is a single integer high-water mark. Nothing in the schema encodes "the next step to run" as anything other than "the next integer."

**Every assumption of strict linearity, confirmed:**
- The executor loop advances by `index + 1` unconditionally; there is no field on a step or on the execution row that can redirect it.
- `last_completed_step` is a monotonically increasing integer high-water mark; resume logic (`_resume_progress`) assumes "resume at `last_completed_step + 1`" is always correct.
- `_step_already_succeeded_in_log` assumes a step index is either "not yet reached," "succeeded," or (implicitly) "about to be reached" — there is no "skipped because a branch jumped over it" state anywhere in the schema or the log-shape helpers.
- Approval denial/expiry (`_process_awaiting_approval_execution`) unconditionally finalizes the execution as `failed` and marks all later steps `skipped` via `_skipped_later_step_entries` — there is no way today for a playbook to *choose* what happens after a denial; it is always a hard stop.
- `validate_playbook_steps` validates each step independently; it has no notion of a step referencing another step by position or name.

## Why Linear Execution Is No Longer Enough

`core-playbook-pack-v1` needs playbooks that behave differently depending on the alert that triggered them and on what already happened during the run — the audit's own examples make this concrete:

- A brute-force playbook should contain a `high`/`critical` severity alert differently than a `low`/`medium` one (e.g., skip straight to `block_ip` for `severity >= high`, but only `monitor` + notify below that).
- A reputation-aware containment playbook should skip blocking entirely when `reputation_score` is below a threshold, to avoid blocking on weak signal.
- A playbook with a `require_approval` gate currently has exactly one option on denial: fail the whole execution. Real analyst workflows want "if denied, notify and stop *this* remediation path, but still log/flag" — today that requires either two separate playbooks or accepting the current single hard-stop behavior.
- A playbook that tries an action with `on_failure: "continue"` today has no way to *act* on that failure — it just moves to the next static step regardless of whether the prior step failed or succeeded.

None of these require loops, variables, or a scripting layer — they require exactly one thing the executor cannot do today: choose the next step index based on data available at execution time. That is the entire scope of this spec.

## Proposed Branching Model

**A new step action, `branch`**, usable anywhere a normal step is today:

```json
{
  "label": "check_severity",
  "action": "branch",
  "condition": {
    "source": "alert",
    "field": "severity",
    "op": ">=",
    "value": "high"
  },
  "goto_true": "contain_offender",
  "goto_false": "log_and_monitor"
}
```

- **`label`** (optional, on *any* step, not just `branch` steps): a unique, playbook-scoped string identifier (`^[a-z][a-z0-9_]*$`, same character class as binding field names) marking that step as a valid jump target.
- **`condition`** (required on `branch` steps only): a single structured object, not a string expression — `{"source": ..., "field": ..., "op": ..., "value": ...}`. This deliberately mirrors the `{{<namespace>.<field>}}` shape `dynamic-playbook-parameter-binding` already established, extended with one more namespace:
  - `source: "alert"` — `field` must be one of the existing `ALERT_BINDING_FIELDS` (no new alert data is exposed beyond what binding and trigger-matching already read).
  - `source: "previous_step"` — `field` must be the literal `"status"`; evaluates against the most recently recorded step outcome in `steps_log` at the time the branch step runs (not simply "index − 1," so it stays correct even after an earlier branch skipped steps).
  - `source: "approval"` — `field` must be the literal `"status"`; evaluates against the most recent `require_approval` gate's recorded decision in `steps_log` (`approved` / `denied` / `expired`).
- **`goto_true`** (required): the `label` of the step to jump to when `condition` evaluates true.
- **`goto_false`** (optional): the `label` to jump to when `condition` evaluates false. If omitted, false means "fall through to the very next step" — identical to today's default linear behavior, so a playbook author who only cares about one branch never has to think about the false side.

**Jump direction: forward-only, to labels, never backward.** Two deliberate constraints, both load-bearing:
- **Labels, not step-count offsets or raw indices.** A label survives a playbook author inserting or reordering steps; a numeric offset silently breaks. Definition-time validation resolves every `goto_true`/`goto_false` to a concrete step index once, at save time, so execution-time jumping is just an index lookup — no re-parsing.
- **Forward-only** (`target_index > branch_step_index`, strictly). This is the mechanism that keeps this a *primitive* rather than a general control-flow feature: with no backward jump possible, there is no way to construct a loop, so the executor never needs an iteration cap, a recursion guard, or new abandonment logic — the playbook is still guaranteed to reach a terminal step (or explicit failure) in at most `len(steps)` step evaluations, exactly the bound that exists today.

**Execution semantics:** when the executor reaches a `branch` step, it evaluates `condition`, appends one `steps_log` entry recording the evaluation (see Auditability), then appends explicit `"skipped"` entries (reusing the existing shape from `_skipped_later_step_entries`, which today only fires on approval denial) for every step strictly between the branch step and the chosen target label, and resumes the loop at the target index. Choosing "fall through" (false with no `goto_false`) skips nothing — it behaves exactly as if the `branch` step were any other successful step.

**Approval-aware branching, without redesigning the approval gate:** `require_approval`'s `on_denied`/`on_expired` today only accept `"fail"` (hard stop). This spec adds exactly one new, opt-in value: `"branch"`. When set, a denial/expiry no longer finalizes the execution as `failed` — it records the decision (as it already does today) and lets the loop continue to the next step, where a `branch` step with `condition.source == "approval"` can react to it. Every playbook that does not set `on_denied`/`on_expired: "branch"` keeps today's exact behavior; this is additive, not a change to any existing playbook's semantics.

## Validation Rules

All enforced at definition-save time, in `validate_playbook_steps` (extended, not replaced):

1. A step with `action: "branch"` must have `condition` (an object) and `goto_true` (a non-empty string). `goto_false`, if present, must also be a non-empty string.
2. `condition.source` must be one of `"alert"`, `"previous_step"`, `"approval"`. Any other value is rejected.
3. If `source == "alert"`: `condition.field` is required and must be a member of `ALERT_BINDING_FIELDS` (the same allow-list `dynamic-playbook-parameter-binding` already defines and validates against — no new field surface is introduced). `condition.op` must be valid for that field's type:
   - Numeric fields (`reputation_score`, `latitude`, `longitude`, `id`): `==`, `!=`, `>=`, `>`, `<=`, `<`.
   - `severity`: the same ordinal operator set, evaluated via the existing `playbook_engine.SEVERITY_RANK` table (reused, not duplicated) — so `severity >= "high"` behaves identically to how `min_severity` already behaves in trigger matching.
   - All other string/enum fields (`alert_type`, `source`, `source_type`, `message`, `status`, `country`, `city`, `reputation_label`, `reputation_source`, `reputation_summary`, `response_action`, `response_status`, `created_at`): equality-only, `==` / `!=` (no lexicographic ordering — it would be meaningless for these fields).
4. If `source == "previous_step"`: `condition.field` must be exactly `"status"`; `condition.op` must be `==`/`!=`; `condition.value` must be one of `"success"`, `"failed"`, `"skipped"`.
5. If `source == "approval"`: `condition.field` must be exactly `"status"`; `condition.op` must be `==`/`!=`; `condition.value` must be one of `"approved"`, `"denied"`, `"expired"`.
6. `condition.value`'s JSON type must match the field's declared type (e.g., a number for `reputation_score`, a string for `severity`/`status`) — a type mismatch is a save-time error, not a runtime surprise.
7. Every `label` used anywhere in the playbook (on any step, not just `branch` steps) must be unique within that playbook. Duplicate labels are rejected.
8. Every `goto_true`/`goto_false` must resolve to a `label` that exists exactly once among this playbook's steps.
9. The resolved target step's index must be strictly greater than the `branch` step's own index. Any label resolving to the branch step itself or to an earlier step is rejected as a backward jump.
10. `require_approval` steps may now set `on_denied`/`on_expired` to `"branch"` in addition to the existing `"fail"` (i.e., `APPROVAL_TERMINAL_BEHAVIORS` grows from `{"fail"}` to `{"fail", "branch"}`); any other value remains rejected exactly as today.

## Failure Behavior

Definition-time validation (above) is expected to catch essentially all malformed branches before they can be saved — this section covers what happens if a `branch` step nonetheless fails at execution time (legacy data saved before this validation existed, a direct DB edit, or a bug):

| Situation | Behavior |
|---|---|
| `condition.source == "alert"` and the resolved alert field is `null` | Step fails closed with code `binding_field_missing` — identical semantics and code to `dynamic-playbook-parameter-binding`'s missing-field behavior, for consistency across both binding surfaces. No silent "treat null as false." |
| Execution has no `alert_id`, or the alert row no longer exists, and `condition.source == "alert"` | Step fails closed with code `binding_alert_context_missing` / `binding_alert_not_found` (reusing the existing `PlaybookParamBindingError` codes). |
| `condition.source == "previous_step"` but the branch step is first in the list (no prior recorded outcome) | Step fails closed with code `branch_context_missing`. |
| `condition.source == "approval"` but no `require_approval` step has run yet | Step fails closed with code `branch_context_missing`. |
| `goto_true`/`goto_false` label cannot be resolved to a step index at execution time (should be impossible after save-time validation, but checked defensively) | Step fails closed with code `branch_target_not_found`. |

In every case, "fails closed" means: the `branch` step gets a `"failed"` `steps_log` entry (same shape `_failure_entry` already produces for every other step type), `failed = True` is set exactly as any other step failure would, and the existing `on_failure` handling (`"abort"` by default) decides whether the whole execution is finalized failed or continues — no new failure-propagation mechanism is introduced. A `branch` step's own `on_failure` still defaults to `"abort"`, same as every other action.

## Auditability

- **The branch step's own decision is logged, not just its target.** The `steps_log` entry for a `branch` step (on successful evaluation) records: `step_index`, `action: "branch"`, `label` (if set), `status: "success"`, `event: "branch_evaluated"`, the full `condition` object, the resolved boolean `result`, and `goto_label`/`goto_step_index` for the path actually taken. An analyst reviewing execution history sees exactly what was checked, what it resolved to, and where execution went — not just "step 4 succeeded."
- **Skipped steps are explicit, not silent.** Every step between the branch step and its jump target gets its own `steps_log` entry with `status: "skipped"`, `event: "skipped_by_branch"`, and `skip_reason: "branch_not_taken"`, reusing the exact entry shape `_skipped_later_step_entries` already produces for approval-denial skips today. No step index is ever simply absent from `steps_log`.
- **Outcome events are unchanged and automatically apply.** `branch` is a non-adapter, non-`require_approval` action, so it flows through the existing `_append_non_adapter_playbook_step_outcome_event` path with no new code: a `step_succeeded`/`step_failed` canonical outcome event is emitted per branch evaluation, with `metadata.action == "branch"` and the condition/result attached, exactly like every other non-adapter step today. Skipped steps do not emit a separate outcome event, matching today's approval-denial-skip behavior (which also only logs to `steps_log`, not to outcome events, for the steps it skips).
- **Approval-branch interaction is fully traceable.** When `on_denied`/`on_expired: "branch"` is used, the existing `_append_playbook_approval_decision_outcome_event` (denied/expired) still fires exactly as today — this spec adds no new event type there, it only changes whether the execution is finalized failed afterward or allowed to continue to the next step.

## Alternatives Considered

- **A general expression language (arbitrary boolean/arithmetic expressions, e.g. `severity == "high" and reputation_score > 50`).** Rejected: parsing and safely sandboxing an expression grammar is exactly the "custom language" complexity this spec is designed to avoid, for a v1 whose only proven need (per the audit) is single-field, single-operator checks. Compound conditions are achievable today by chaining two `branch` steps (the second only reached if the first's condition was true) — a real but acceptable v1 limitation, not a blocker.
- **Embedded scripting (Python snippets, JSONLogic, Jinja-style templates in conditions).** Rejected outright per the roadmap's explicit non-goals — code execution inside a playbook definition is a security boundary this project has deliberately avoided everywhere else (adapters, param binding), and a branch condition is not a good enough reason to open it.
- **Numeric step-offset jumps (`goto_true: 3`) instead of named labels.** Rejected: offsets silently break the moment a playbook author inserts or reorders a step, with no validation-time signal. Labels are validated (existence, uniqueness, forward-only) at save time and are stable under editing.
- **Backward jumps / bounded loops (e.g., "retry the previous step up to 3 times").** Rejected per the roadmap's explicit non-goals for this spec; also the single mechanism (forward-only) that guarantees this feature cannot introduce infinite or even bounded-but-complex loops. Retry semantics belong to a future, separately-scoped spec if ever pursued.
- **Redesigning `require_approval` so denial never hard-fails.** Rejected: that would silently change behavior for every existing playbook using `require_approval` today. The opt-in `on_denied/on_expired: "branch"` value achieves the same expressiveness with zero behavior change for anything not explicitly opted in.
- **A separate "conditions" section decoupled from steps (e.g., a top-level `rules` list evaluated before execution starts).** Rejected: trigger-time evaluation (`_evaluate_trigger`) already fills that role for "should this playbook run at all." A mid-execution decision needs to see step outcomes and approval decisions that don't exist until execution is already underway, so it must be a step, not a pre-execution rule.

## Implementation Scope

(For a later, separately-scoped and explicitly-requested implementation pass — not part of this spec-authoring step.)

- `engines/playbook_registry.py`: extend `validate_playbook_steps` with the ten validation rules above; extend `APPROVAL_TERMINAL_BEHAVIORS` to `{"fail", "branch"}`; add a label/target-resolution pass (build the label→index map once per definition, verify uniqueness and forward-only jump targets).
- New module, e.g. `engines/playbook_branch_conditions.py`: condition evaluation (`alert`/`previous_step`/`approval` sources), reusing `ALERT_BINDING_FIELDS` from `engines/playbook_param_binding.py` and `SEVERITY_RANK` from `engines/playbook_engine.py` rather than redefining either.
- `engines/playbook_step_executor.py`: convert `_process_steps`'s `for index, step in enumerate(...)` loop to an explicit cursor that can be redirected by a branch decision; add `branch` handling (evaluate → log → compute next index → emit skipped-step entries); add the `on_denied`/`on_expired == "branch"` continuation path in `_process_awaiting_approval_execution`.
- Tests: registry validation (all ten rules, positive and negative cases), executor branch-taken / branch-not-taken / fall-through / skip-logging / outcome-event cases, approval-denied-then-branch cases, and a full existing-suite regression run to confirm zero behavior change for playbooks with no `branch` steps.
- No schema or migration changes: `steps` and `steps_log` are already JSON columns; `branch` is simply a new shape within existing columns.

## Non-goals

- Loops, recursion, or any bounded/unbounded repetition of steps.
- An expression language, embedded scripting, or arithmetic/compound (`and`/`or`) conditions in v1.
- New playbook actions, adapters, or integrations.
- Playbook chaining, reusable subflows, or cross-playbook control flow (tracked separately on the roadmap).
- Variables, computed values, or any state beyond what `steps_log` and the triggering alert already provide.
- Scheduler changes, evidence collection, UI changes, deployment changes, or new dependencies.
- Redesigning `require_approval`'s default behavior (the new `"branch"` value is strictly additive/opt-in).

## Risks

- **[Risk]** Converting the executor's `for … enumerate(...)` loop to an explicit, redirectable cursor touches a hot, heavily-relied-upon path (leasing, heartbeats, crash-resume, dedup-on-replay all depend on today's strict-linear assumption).
  **[Mitigation]** The implementation pass must preserve byte-for-byte behavior for any playbook containing zero `branch` steps (the cursor always equals `index + 1` in that case); the acceptance criteria below require a full existing-suite regression pass before this is considered done.
- **[Risk]** `on_denied`/`on_expired: "branch"` means an approval denial no longer automatically halts an execution for playbooks that opt in, which is a meaningful trust-boundary change for whoever relies on "denial always stops automation."
  **[Mitigation]** Strictly opt-in per step (default remains `"fail"`); documented clearly in `core-playbook-pack-v1` authoring guidance as a deliberate choice, not a default.
- **[Risk]** Authors could build a tangled web of many branch steps that's hard for a reviewer to reason about, even without loops.
  **[Mitigation]** Forward-only jumps keep the step graph a DAG bounded by `len(steps)`; a future spec (out of scope here) could add lint/visualization tooling if this becomes a real problem in practice.
- **[Risk]** Reusing `ALERT_BINDING_FIELDS`/`SEVERITY_RANK` couples this spec's correctness to two other modules' internals.
  **[Mitigation]** This is a deliberate reuse decision (see Alternatives Considered) to avoid a second, drifting field allow-list; any future change to those allow-lists automatically and correctly changes what branch conditions can reference.

## Acceptance Criteria

- A `branch` step with a valid `alert`-sourced condition, `goto_true`, and no `goto_false` correctly jumps to the target label when true and falls through to the next step when false, in both cases producing correct `steps_log` and outcome-event entries.
- A `branch` step whose condition is false and whose `goto_false` is set jumps to that label instead of falling through.
- Every step skipped by a taken branch has an explicit `"skipped"` / `skip_reason: "branch_not_taken"` entry in `steps_log`; no step index is silently missing from the log.
- A playbook definition with a backward-jumping, duplicate-label, unknown-field, wrong-operator, or type-mismatched branch condition is rejected at save time with a clear validation error, and no such definition can be persisted.
- A `branch` step referencing `previous_step.status` correctly reflects the most recently recorded step outcome, including across an intervening earlier branch skip (not simply "index − 1").
- A `branch` step referencing `approval.status` correctly reflects the latest `require_approval` gate's decision, and only reaches this outcome for denial/expiry when that gate's `on_denied`/`on_expired` was explicitly set to `"branch"`.
- A playbook definition containing no `branch` steps executes with output identical to today's engine (no observable behavior change) — verified by the full existing playbook test suite passing unmodified.
- A `branch` step whose condition cannot be resolved at execution time (missing alert context, null field, missing prior-step/approval context) fails closed with the documented error code and does not proceed past that step under any implicit default.

## Validation Plan

- `openspec validate conditional-branching-primitive --strict` must pass as part of this spec-authoring step (no code involved).
- For the later implementation pass: unit tests in `tests/test_playbook_registry.py` for every validation rule (positive and negative); unit tests in `tests/test_playbook_step_executor.py` for branch-taken, branch-not-taken/fall-through, goto_false, skip-logging, outcome-event shape, all five failure-closed cases, and the approval-branch interaction; a full run of the existing playbook-related test suite (`test_playbook_engine.py`, `test_playbook_registry.py`, `test_playbook_step_executor.py`, `test_playbook_store.py`, `test_playbook_param_binding.py`) to confirm zero regressions for non-branching playbooks.

## Overall Assessment

The current executor is linear by construction at every layer (trigger matching, definition validation, step execution, and persistence), and every one of those layers' assumptions has been re-verified directly against the code in this pass. The proposed `branch` step is the smallest change that removes exactly the one constraint blocking the roadmap's next items (`core-playbook-pack-v1` containment/severity logic, and any future approval-aware remediation): the executor cannot currently choose its next step. Reusing the alert-field allow-list and severity ranking already established by `dynamic-playbook-parameter-binding` and `playbook_engine.py`, forward-only label jumps, and a single-condition (no boolean composition) model keep this an additive primitive rather than a redesign — the one genuinely invasive change (the executor's loop becoming a redirectable cursor) is called out explicitly as the main implementation risk, with "zero behavior change for non-branching playbooks" set as a hard acceptance bar. This spec is ready for implementation once explicitly requested as a separate pass.
