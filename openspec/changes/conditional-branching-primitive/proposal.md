## Why

The playbook execution engine (`engines/playbook_step_executor.py`) runs every definition's `steps` list strictly in order — the loop always advances to `index + 1`, with no way for a playbook to choose its next step based on the alert that triggered it or on what already happened during the run. `dynamic-playbook-parameter-binding` gives playbooks per-execution *values* (which IP to block, what message to send) but still no per-execution *decisions*. The roadmap's next content item, `core-playbook-pack-v1`, needs exactly that: contain a `critical`-severity offender differently than a `low`-severity one, skip blocking when reputation signal is weak, or react to an approval denial instead of always hard-failing. This is a foundational engine capability, not playbook content — it must exist before that pack can be authored correctly.

## What Changes

- Define the engine capability for a single new step action, `branch`, that evaluates one structured condition (sourced from the alert-field binding surface `dynamic-playbook-parameter-binding` already validated, the most recently recorded step outcome, or the latest approval decision) and jumps forward to a named `label`, or falls through to the next step.
- Specify the branch step shape, the allowed condition sources/operators (reusing `ALERT_BINDING_FIELDS` and `SEVERITY_RANK` rather than introducing a second field surface), definition-time validation rules, execution-time fail-closed behavior, and how branch decisions and skipped steps are recorded in `steps_log` and outcome events.
- Add one small, strictly opt-in extension to the existing `require_approval` gate (`on_denied`/`on_expired: "branch"`) so a denial/expiry can be observed by a branch step instead of always hard-failing the execution — default behavior for every existing playbook is unchanged.
- No implementation, no schema changes in this proposal step, and no playbook definitions.

## Capabilities

### New Capabilities
- `conditional-branching-primitive`: records the engine requirements for a single, forward-only, label-based conditional branch step. No existing spec under `openspec/specs/` covers this domain.

### Modified Capabilities
(none — this proposal does not change the behavior of any shipped capability; the `on_denied`/`on_expired: "branch"` value is additive and opt-in only)

## Impact

- **Affected code (future implementation phase, not this proposal step):** `engines/playbook_step_executor.py` (executor loop becomes a redirectable cursor; branch evaluation, skip logging), `engines/playbook_registry.py` (definition-time validation of branch shape, labels, forward-only targets, and the `on_denied`/`on_expired` extension), a new small module for condition evaluation (proposed `engines/playbook_branch_conditions.py`).
- **Affected artifacts (this step):** adds `openspec/changes/conditional-branching-primitive/` as a new, unimplemented child change under the `soar-playbook-modernization-roadmap` parent.
- **Downstream effect:** unblocks severity/reputation-aware and approval-aware playbook content in `Core Playbook Pack v1`; provides the decision primitive that `Playbook Chaining & Cross-Path Orchestration Layer` may later build on for cross-path routing.
- **Dependencies:** `Playbook Engine Correctness Hardening` (hardened executor and canonical action vocabulary this spec extends); `Dynamic Playbook Parameter Binding` (this spec reuses its `ALERT_BINDING_FIELDS` allow-list for condition fields rather than redefining one).
