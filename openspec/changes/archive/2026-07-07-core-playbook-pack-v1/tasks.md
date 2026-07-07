This spec's authoring step (creating proposal.md/design.md/tasks.md/specs/) makes no code changes and creates no playbook definitions. Section 1 reflects the inventory/verification work completed to write this spec. Section 2 lists content-authorship work — BLOCKED until `dynamic-playbook-parameter-binding` is implemented — to be executed only in a separate, later, explicitly-requested implementation pass through the existing `POST /playbooks` API.

## 1. Inventory and Verification (completed as part of writing this spec)

- [x] 1.1 Enumerate every detection-rule alert type and its severity directly from `engines/detection_engine.py`.
- [x] 1.2 Enumerate every correlation alert type and its trigger mechanism directly from `engines/correlation_engine.py`.
- [x] 1.3 Confirm the current, post-hardening playbook action vocabulary (`KNOWN_PLAYBOOK_ACTIONS`) and each action's real vs. simulated behavior in `engines/playbook_step_executor.py`.
- [x] 1.4 Confirm the five recognized trigger keys and their exact matching semantics in `engines/playbook_engine.py`.
- [x] 1.5 Confirm which enrichment fields are available at alert time vs. re-computable during playbook execution.
- [x] 1.6 Confirm `require_approval` mechanics (risk levels, TTL, RBAC) are unchanged and fully functional.
- [x] 1.7 Confirm static-params gap: `params = step.get("params")` with no alert-field binding; `alert_id` available but unused for param population.
- [x] 1.8 Select the five highest-value Version 1 playbooks and design them with dynamic bindings (not static workarounds).
- [x] 1.9 Enumerate deferred playbook ideas blocked on capabilities other than parameter binding.
- [x] 1.10 Record all five playbook designs with dynamic `block_ip` and notification bindings in `design.md`.
- [x] 1.11 Update parent roadmap to insert `dynamic-playbook-parameter-binding` before this spec and set it as a blocking dependency.

## 2. Content Authorship (BLOCKED — requires `dynamic-playbook-parameter-binding`)

**Prerequisite:** `dynamic-playbook-parameter-binding` implementation complete (roadmap item 2.4).

- [x] 2.1 Create the `Brute Force Containment` playbook via `POST /playbooks` with `block_ip` (`source_ip: "{{alert.source_ip}}"`) and dynamic notification params per `design.md`.
- [x] 2.2 Create the `Password Spray Investigation` playbook with dynamic notification params (no `block_ip` — intentional restraint).
- [x] 2.3 Create the `Successful Login After Spray Response` playbook with approval-gated `block_ip` and dual-channel dynamic notifications.
- [x] 2.4 Create the `Malicious IP Containment` playbook with approval-gated `block_ip` and dynamic notifications.
- [x] 2.5 Create the `Reputation-Only Investigation` playbook with dynamic notification params.
- [x] 2.6 Exercise each playbook end-to-end against a synthetic alert matching its trigger; confirm resolved `block_ip` targets the alert's `source_ip` and notifications contain alert-specific values.
- [x] 2.7 Confirm no regression to existing playbook definition/execution tests from adding these five rows.

## Safety Boundaries (for this authoring step)

- [x] Creating/updating this spec's proposal/design/tasks/spec files makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`, and creates no `playbook_definitions` rows.
- [x] No engine changes, schema changes, new actions, or UI changes are introduced by this spec.
- [x] Playbook designs include `block_ip` with dynamic bindings where containment is intended — not excluded due to engine limitation.
- [x] Implementation tasks remain BLOCKED until `dynamic-playbook-parameter-binding` ships.
- [x] Do not commit.
