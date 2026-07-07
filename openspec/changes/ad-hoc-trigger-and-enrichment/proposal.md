## Why

Analysts can view playbooks and existing executions, but they cannot start an enabled playbook on demand from an alert, incident, threat-hunt pivot, or SOC operational view. The engine also has alert, reputation, MITRE, correlation, and source-IP context available elsewhere, but no reusable read-only playbook step that snapshots that context for downstream steps.

## What Changes

- Define the smallest analyst-initiated execution model: create a normal pending `playbook_executions` row for a selected existing playbook and target alert or incident, then let the existing worker and step executor process it.
- Define a reusable read-only enrichment step that gathers only existing local context: alert fields, stored external reputation snapshots, internal behavioral reputation, MITRE mapping, safe correlation metadata, related alerts/incidents/playbook executions, and source-IP context already queryable by the application.
- Require manual executions to be distinguishable from automatic executions through canonical outcome metadata and audit logging, without creating a duplicate engine or queue.
- Keep approval behavior inside playbook steps: manual launch itself does not require approval, but any `require_approval` step still gates later actions.
- No implementation, source changes, schema migrations, commits, pushes, new dependencies, scheduler work, branching, chaining, workflow builder, or new playbooks are included in this design-only spec.

## Capabilities

### New Capabilities
- `ad-hoc-trigger-and-enrichment`: covers analyst-initiated playbook execution and a reusable read-only enrichment playbook step.

### Modified Capabilities
(none)

## Impact

- **Affected code in a future implementation phase:** `routes/playbook_routes.py`, `core/playbook_store.py`, `engines/soar_playbook_orchestrator.py`, `engines/playbook_registry.py`, `engines/playbook_step_executor.py`, `helpers/enrichment_helpers.py`, `routes/source_ip_context_routes.py` or an extracted helper, `frontend/src/services/playbookService.js`, `frontend/src/components/PlaybooksPanel.js`, `ThreatHuntPanel`, `SocCommandCenter`, and alert/incident action surfaces.
- **Affected APIs in a future implementation phase:** one narrow manual execution endpoint is expected; no scheduler or alternate worker API is expected.
- **Schema impact:** no schema change is expected unless implementation proves existing canonical outcome metadata and audit details are insufficient.
- **Dependencies:** builds on the existing playbook execution pipeline, canonical response outcome linkage, RBAC decorators, audit helper, source-IP context contract, MITRE enrichment helper, and reputation helpers.
