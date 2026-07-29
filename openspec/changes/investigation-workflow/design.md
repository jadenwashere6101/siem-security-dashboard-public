## Context

`analyst-experience-foundation` established responsive shell behavior, reusable primitives, dark SOC tokens, dashboard hierarchy, sidebar behavior, and grouped operations feed patterns. `anakin-analyst-experience` added a shared command registry, sanitized command context, the primary Anakin surface, read-only command palette, and Threat Brief extension points.

This final phase extends those decisions into investigation management. It should help analysts organize work after detection by adding a focused Investigation Drawer, narrative Threat Story, and private Analyst Workspace. Unlike prior phases, this phase requires persistence and backend/API contracts because notes, hypotheses, tasks, pinned objects, and saved investigation state must survive sessions and belong to a specific analyst.

## Goals / Non-Goals

**Goals:**

- Provide a focused drawer/panel for alert or incident investigation without forcing analysts to leave their current workspace.
- Present investigation evidence as a coherent Threat Story while reusing existing authoritative alert, incident, recon, SOAR, enrichment, and grouped feed data.
- Add a private Analyst Workspace for manual pins, notes, hypotheses, tasks, evidence references, and saved investigation organization.
- Define persistence, ownership, RBAC, audit, and extension contracts for future collaboration.
- Reuse existing foundation primitives and Anakin command/context architecture.

**Non-Goals:**

- No shell redesign, theme redesign, command palette redesign, Anakin surface redesign, AI provider change, detection engine change, or SOAR engine redesign.
- No automatic population of Analyst Workspace from system events.
- No case-management collaboration, evidence upload, report export, or shared workspace behavior in this phase.

## Decisions

### Decision: One `investigation-workflow` capability

The drawer, Threat Story, and Analyst Workspace share selected-object context, evidence references, persistence ownership, and extension points. Keeping them in one OpenSpec avoids competing representations of investigation state.

Alternative considered: separate specs for drawer, story, and workspace. Rejected because each would need overlapping contracts for object references, saved state, notes, and future collaboration.

### Decision: Investigation Drawer is a contextual surface, not a route replacement

The drawer should open from alerts, incidents, recon/source-IP views, Threat Brief, and Anakin commands while preserving the current workspace history. Desktop should use a right-side drawer or resizable panel built from foundation primitives. Tablet/mobile should use a full-width drawer/modal pattern with Escape/backdrop close and focus return.

The drawer should render sections for alert summary, incident summary, timeline, enrichment summary, related entities, related detections, SOAR response history, recommended next steps, and evidence links. Sections may show unavailable/partial states when authoritative data is absent.

### Decision: Threat Story is a read model over existing evidence

Threat Story should normalize existing event/timeline/correlation inputs into narrative sections: what happened, why it mattered, affected entities, attack progression, detections triggered, SOAR actions, analyst observations, and current investigation status.

It must not redefine detection, incident, approval, or response business logic. Where existing data is missing, it should state that the story is incomplete rather than inventing a progression.

### Decision: Analyst Workspace is private, manual, and persisted

Workspace content should be analyst-owned and private by default. Supported object references include alerts, incidents, recon activities, source IPs, investigations, evidence links, notes, hypotheses, and manual tasks. Nothing automatically appears in the workspace; every pin or note is analyst-initiated.

The workspace is not an incident queue, playbook state machine, or dashboard aggregation. Removing an item from the workspace must not mutate the underlying system object.

### Decision: Backend contracts are scoped and auditable

Add backend contracts for workspace items, investigation records, evidence references, notes, hypotheses, tasks, and saved drawer/story state. Records must include owner identity, object type, object identifier, timestamps, optional labels/status, and audit metadata. APIs must enforce authenticated ownership and role visibility for referenced system objects.

Future collaboration should be anticipated by fields such as visibility/scope, but shared/collaborative behavior remains disabled or reserved.

## Component Relationships

- `App` continues to own global section state and passes selected investigation context into the drawer/workspace providers.
- `InvestigationProvider` normalizes selected alert, incident, source IP, recon, timeline, enrichment, response history, and workspace references.
- `InvestigationDrawer` consumes provider context and uses foundation `Panel`, `SectionHeader`, chips, status/severity pills, grouped feed, and responsive overlay behavior.
- `ThreatStory` consumes the same read model and renders narrative sections plus attack progression.
- `AnalystWorkspace` uses dedicated service functions for pins, notes, hypotheses, tasks, and saved state.
- Anakin commands may open drawer/story/workspace actions through existing registry extension slots, but this phase does not redesign Anakin.

## Persistence Strategy

Use normalized records rather than embedding opaque blobs as the primary model:

- `analyst_workspaces`: owner, name/default marker, timestamps.
- `workspace_items`: owner/workspace, item type, referenced object type/id, label, status, ordering, timestamps.
- `investigations`: owner, optional linked alert/incident/source IP, title, status, summary, timestamps.
- `investigation_notes`, `investigation_hypotheses`, `investigation_tasks`: owner, investigation/workspace link, body/title/status, timestamps.
- `evidence_references`: owner, parent type/id, referenced object type/id or URL-like internal evidence locator, label, source, timestamps.

Implementation may adjust table names to match repository conventions, but ownership and reference semantics must remain explicit.

## Ownership Model

- Workspace data is private to the creating analyst by default.
- Super admins may retain operational/admin visibility only if existing policy requires it, and such access must be explicit and auditable.
- Users must not access workspace records they do not own unless a future collaboration spec enables sharing.
- Referencing an incident or alert does not grant visibility beyond existing RBAC for that system object.

## Rollout Strategy

1. Add backend schema/API/service contracts and tests for private workspace persistence.
2. Add frontend service layer and provider/read models.
3. Add Investigation Drawer using existing object data and partial-state handling.
4. Add Threat Story read model and UI.
5. Add Analyst Workspace UI for manual pins, notes, hypotheses, tasks, and evidence references.
6. Wire scoped Anakin/palette extension actions without broad redesign.

## Risks / Trade-offs

- **Workspace state could be confused with incident state** -> Keep labels, APIs, and UI copy explicit: private workspace changes never mutate incidents, alerts, SOAR state, or playbooks.
- **Duplicated business logic in Threat Story** -> Build story sections from existing service/read-model inputs and mark missing evidence honestly.
- **RBAC leakage through references** -> Resolve referenced objects through existing authorization checks and fail closed.
- **Scope growth into case management** -> Reserve collaboration/shared/export fields but keep behavior disabled.
- **Migration risk** -> Add focused migration/schema tests and a VM handoff after Mac implementation only.

## Regression Strategy

- Backend tests for ownership, RBAC denial, CRUD, audit events, reference validation, and migration/schema behavior.
- Frontend tests for drawer open/close/focus, responsive presentation, partial states, story derivation, workspace pins/notes/tasks, and removal without system mutation.
- Integration tests for selected alert/incident/source-IP context, existing workspace history, existing Anakin affordances, and command extension slots.
- Run focused tests, frontend build, backend/migration tests, `git diff --check`, and strict OpenSpec validation before handoff.

## Extension Points

- Collaborative investigations and shared workspaces.
- Case management and assignment workflows.
- Evidence uploads and external artifact storage.
- Reporting/export packages.
- Future AI investigation assistants that draft hypotheses, summarize evidence, or suggest tasks through the existing command registry.
