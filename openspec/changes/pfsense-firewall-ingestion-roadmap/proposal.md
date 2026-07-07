## Why

pfSense firewall log ingestion will touch source code, deployment, cloud exposure, VM runtime configuration, and an external operator handoff. Prior sync issues between the Mac source-of-truth repo and the Azure VM make this integration risky unless the work is coordinated from a single parent roadmap before any implementation starts.

This parent roadmap tracks the full pfSense integration from read-only audit through production readiness. It exists to keep code tasks, deployment tasks, security review, Azure/VM operations, and uncle/pfSense handoff sequencing visible in one place.

## What Changes

- Add a coordination-only parent roadmap for `pfsense-firewall-ingestion-roadmap`.
- Track audit, architecture, security, child-spec creation, milestone implementation, deployment, runtime validation, and production handoff phases.
- Include non-code/operator tasks such as Azure NSG review, VM firewall checks, deployment verification, service validation, and pfSense configuration handoff.
- Record hard guardrails before implementation begins:
  - Mac repo is source of truth.
  - Azure VM is deployment/runtime only.
  - No source code edits on the VM unless explicitly labeled VM emergency hotfix.
  - Every runtime-affecting feature must have a deployment plan before implementation.
  - No port opening until security review is complete.
  - No uncle/pfSense configuration request until our side is fully deployed and tested.
  - No implementation until Phase 0 and Phase 1 audits are complete.
  - No production/live log collection until runtime validation passes.

## Capabilities

### New Capabilities

- `pfsense-firewall-ingestion-roadmap`: tracks the parent coordination plan, phase checklist, operational guardrails, and child-spec sequencing for pfSense firewall log ingestion.

### Modified Capabilities

(none - this change is coordination only and does not alter application behavior)

## Impact

- **Affected code:** none. This change must not touch source files under `core/`, `engines/`, `routes/`, `helpers/`, `scripts/`, `migrations/`, `frontend/`, or tests.
- **Affected artifacts:** adds `openspec/changes/pfsense-firewall-ingestion-roadmap/`.
- **Operational scope tracked:** Azure NSG planning, VM firewall/listener checks, systemd/runtime deployment planning, service health checks, fake log validation, and eventual pfSense operator handoff.
- **Implementation status:** no listener, parser, adapter, detection rule, route, service unit, migration, deployment script, or runtime configuration is implemented by this parent roadmap.
- **Downstream work:** child implementation specs will be created later after Phase 0 and Phase 1 audits are complete.

