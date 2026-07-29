## Why

Analysts can detect and respond to alerts, but the workflow for organizing follow-up investigation state is still fragmented across alert views, incident views, SOAR panels, recon context, and AI summaries. This change defines the final investigation workflow layer so analysts can preserve context, understand attack narratives, and maintain private investigation notes without changing the existing shell, Anakin command architecture, or SOAR engine.

## What Changes

- Add an Investigation Drawer concept for focused alert/incident investigation without losing the current workspace context.
- Add a Threat Story view that turns existing timeline, detection, entity, and response data into a coherent investigation narrative.
- Add an Analyst Workspace concept as a private, analyst-owned notebook for manually pinned objects, notes, hypotheses, tasks, and evidence references.
- Define backend/frontend contracts for workspace persistence, ownership, RBAC, evidence references, investigation state, and future collaboration.
- Reuse `analyst-experience-foundation` primitives and `anakin-analyst-experience` command/context extension points.
- Keep system events, incident queues, playbook state, and analyst workspace state separate.
- Do not implement shell, theme, command palette, Anakin surface, AI provider, detection engine, or SOAR engine redesigns.

## Capabilities

### New Capabilities

- `investigation-workflow`: Investigation drawer, Threat Story, private Analyst Workspace, persistence/ownership contracts, evidence references, and future investigation extension points.

### Modified Capabilities

- None.

## Impact

- Frontend: new investigation drawer/panel, Threat Story presentation, Analyst Workspace UI, services, state adapters, and tests built on existing primitives and command context.
- Backend/API: new persistence contracts for private analyst workspace items, investigation state, notes, hypotheses, tasks, pins, and evidence references.
- Database: new analyst-owned workspace/investigation tables or equivalent normalized persistence with migration and ownership constraints.
- Security/RBAC: workspace data is private by default, scoped to the authenticated analyst, and must preserve existing RBAC, audit, and protected-action boundaries.
- AI/Anakin: optional read-only command integrations may use existing command registry/context providers; no new AI providers or backend AI redesign.
- Deployment: backend/schema work requires Mac validation and a VM handoff only after implementation, commit, push, and explicit deployment approval.
