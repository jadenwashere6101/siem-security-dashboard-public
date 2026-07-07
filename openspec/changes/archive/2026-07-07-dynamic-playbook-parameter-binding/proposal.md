## Why

The `core-playbook-pack-v1` design audit re-verified that playbook step `params` are read verbatim from stored step JSON at execution time (`engines/playbook_step_executor.py`: `params = step.get("params")`) with no substitution of the triggering alert's fields. `execution["alert_id"]` is available to the executor and used for outcome linkage, but never to populate step parameters. Trigger matching (`engines/playbook_engine.py`) already loads full alert rows for evaluation, yet that context is not carried into action dispatch. Without per-execution parameter binding, containment actions (`block_ip`), alert-specific notifications, and any adapter action requiring runtime alert context cannot function correctly in automatically-triggered playbooks. This is a foundational engine capability that must exist before the first production playbook pack ships.

## What Changes

- Define the engine capability for resolving playbook step parameter values at execution time against the alert (and, where applicable, execution context) that triggered the run.
- Specify parameter syntax, the alert field surface exposed to playbooks, validation rules, security boundaries, missing-field behavior, and the relationship between static and dynamic parameter values.
- Identify which existing actions benefit (`block_ip`, notification actions, future adapter actions) without prescribing playbook content.
- No implementation, no schema changes in this proposal step, and no playbook definitions.

## Capabilities

### New Capabilities
- `dynamic-playbook-parameter-binding`: records the engine requirements for per-execution resolution of playbook step `params` against alert (and execution) context. No existing spec under `openspec/specs/` covers this domain.

### Modified Capabilities
(none)

## Impact

- **Affected code (future implementation phase, not this proposal step):** `engines/playbook_step_executor.py` (primary resolution point), `engines/playbook_registry.py` (definition-time validation of binding syntax), potentially `routes/playbook_routes.py` (authoring validation surfaced to API consumers).
- **Affected artifacts (this step):** adds `openspec/changes/dynamic-playbook-parameter-binding/` as a new, unimplemented child change under the `soar-playbook-modernization-roadmap` parent.
- **Downstream effect:** unblocks `Core Playbook Pack v1` content authorship for containment and alert-specific notification playbooks; provides the parameter-binding foundation that `Conditional Branching Primitive` and `Ad Hoc Trigger & Enrichment Step` can extend without redefining the base mechanism.
- **Dependencies:** `Playbook Engine Correctness Hardening` (hardened executor and canonical action vocabulary); soft dependency on `SOAR Automation Path Consolidation Decision` (confirms playbook engine as authoritative execution path).
