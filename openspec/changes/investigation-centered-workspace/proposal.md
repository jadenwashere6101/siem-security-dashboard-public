## Why

Analyst Workspace currently stores useful objects, but it does not make an investigation feel like the central analyst activity. This change evolves the workspace so it demonstrates analyst reasoning and supports a realistic SOC loop from alert triage through evidence, hypotheses, tasks, and conclusion.

## What Changes

- Make investigations the primary workspace object, with an active investigation driving the page instead of appearing as one equal card among many.
- Add active investigation selection and a focused investigation detail experience that preserves the existing private-workspace ownership model.
- Introduce an investigation summary/story surface that explains what happened, why it matters, what is known, what is uncertain, and what remains open.
- Add investigation lifecycle fields and presentation for status, disposition, confidence, key entities, linked objects, and progress.
- Make evidence more meaningful by adding analyst rationale, source context, navigation back to original objects, and support/refute/neutral relationships to hypotheses.
- Connect hypotheses to evidence so the workspace shows analyst reasoning rather than isolated notes.
- Connect tasks to investigations and optionally to hypotheses or evidence so next steps are tied to unresolved questions.
- Add investigation conclusions/dispositions without changing alert lifecycle, incident state, detection output, or SOAR execution state.
- Add missing private-workspace cleanup actions such as deleting saved investigations and evidence references when supported by the final design.
- Preserve responsive, accessible, dark-theme SOC UI patterns and existing navigation/history behavior.
- Keep the scope realistic for a junior Detection Engineer portfolio: show a coherent investigation workflow, not an enterprise case-management platform.

## Capabilities

### New Capabilities

- `investigation-centered-workspace`: Active-investigation workspace, investigation story, evidence rationale, hypothesis-evidence reasoning, investigation-scoped tasks, conclusions, linked-object navigation, lifecycle/progress, and scoped persistence/API contracts.

### Modified Capabilities

- None.

## Impact

- Frontend: Analyst Workspace route will become investigation-centered; Investigation Drawer save/open flows will need to land analysts in the active investigation experience; navigation back to alerts, source IPs, incidents, and evidence sources must remain clear.
- Backend/API: existing investigation, note, hypothesis, task, evidence, and workspace APIs may need additional fields/endpoints for active investigation state, rationale, relationships, conclusions, and private deletion flows.
- Database: likely requires a small normalized schema evolution for evidence rationale and relationship records; migration scope must remain minimal and validated before implementation.
- Security/RBAC: private workspace ownership, existing referenced-object RBAC, audit logging, and no-system-mutation boundaries must be preserved.
- Deployment: any schema/API implementation later requires Mac validation and VM handoff only after an approved commit/push/deploy path.
