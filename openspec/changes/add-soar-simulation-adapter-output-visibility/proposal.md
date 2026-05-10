# Proposal: SOAR Simulation Adapter Output Visibility

## Problem
Adapter-backed simulated playbook steps now write structured results into `steps_log[*].output.adapter_result`, but the frontend does not yet make that nested output easy to inspect. Operators need to see which simulation adapter handled a step, what action was simulated, whether it succeeded, and what metadata was recorded without mistaking the result for real remediation.

## Goal
Improve `PlaybooksPanel` read-only visibility for adapter-backed simulated playbook steps by rendering `output.adapter_result` clearly in the execution timeline.

## Scope
- Add frontend-only display polish in `PlaybooksPanel` for `steps_log[*].output.adapter_result`.
- Show adapter name, adapter action, simulated and executed flags, success or failure, message, and metadata when present.
- Keep the display read-only and consistent with the existing execution timeline.
- Add focused frontend tests for adapter-backed timeline output.

## Out of scope
- No backend changes.
- No executor changes.
- No schema changes.
- No real integrations.
- No network calls.
- No run, retry, cancel, approve, deny, or resume behavior changes.
- No ingest, detection, or correlation changes.
- No SOAR queue, approval decision, incident, adapter, or firewall behavior changes.

## Success criteria
- Adapter-backed simulated steps are readable in `PlaybooksPanel` without requiring raw JSON inspection.
- The UI clearly labels adapter output as simulated and does not imply real remediation occurred.
- Steps without `adapter_result` continue to render normally.
- Existing read-only and super-admin behavior remains unchanged.
- Focused frontend tests cover adapter result rendering and no mutation-control regressions.
