## Context

`investigation-workflow` introduced the Investigation Drawer, Threat Story, saved investigations, and private Analyst Workspace persistence. `post-deployment-ux-remediation` made those surfaces usable and discoverable, but deliberately deferred the deeper workspace redesign. The current workspace now exposes pins, notes, hypotheses, tasks, evidence references, and saved investigations; however, those objects still feel like independent storage buckets.

The next evolution should make the workspace model the way a SOC analyst reasons through an incident: start from a trigger, collect evidence, form and challenge hypotheses, track open questions, and record a conclusion. This is an architectural UX change, not a visual polish pass.

## Goals / Non-Goals

**Goals:**

- Make the active investigation the organizing object for Analyst Workspace.
- Demonstrate analyst reasoning rather than merely storing analyst-created records.
- Support a realistic workflow: Alert -> Investigation -> Evidence -> Hypotheses -> Tasks -> Conclusion.
- Preserve private analyst ownership, audit logging, RBAC, and no-system-mutation boundaries.
- Keep the implementation portfolio-realistic and maintainable.
- Provide clear future extension points without exposing enterprise case-management behavior.

**Non-Goals:**

- No multi-user collaboration, assignments, approvals, SLA tracking, reporting engines, enterprise case ownership, heavy automation, source-IP watchlists, or major SOAR changes.
- No complex graph database or generalized entity knowledge graph.
- No automatic mutation of alerts, incidents, detections, SOAR queues, approvals, or response actions from workspace edits.
- No AI provider redesign or broad Anakin redesign.
- No attempt to make Analyst Workspace replace the SOAR incidents page.

## Decisions

### Decision: Active investigation is the workspace container

Analyst Workspace should present a list/rail of saved investigations and a dominant active investigation detail area. Notes, evidence, hypotheses, tasks, pins, and conclusions should render in relation to the active investigation. Unscoped legacy/private records may remain available in a secondary "Unassigned workspace items" view, but they should not define the main page.

Alternative considered: keep the six-card grid and add cross-links. Rejected because equal-weight buckets preserve the storage-widget feel and do not teach the analyst how to work an investigation.

### Decision: Model reasoning with simple normalized relationships

Evidence should have analyst rationale and a relationship to hypotheses: `supports`, `refutes`, or `context`. Tasks should belong to an investigation and may optionally reference a hypothesis or evidence item. This provides enough structure to show reasoning without building a graph database.

Alternative considered: a generic graph of entities and edges. Rejected as too broad for the portfolio scope and likely to distract from analyst workflow.

### Decision: Investigation story is analyst-authored plus evidence-derived

The investigation detail should show structured fields for trigger, what happened, key entities, current assessment, open questions, and conclusion. The system may derive read-only context from linked alerts/incidents/source IPs, but analyst-authored assertions must remain distinct from source facts.

Alternative considered: fully auto-generated investigation stories. Rejected because it can fabricate confidence and hides the analyst reasoning the portfolio should demonstrate.

### Decision: Lifecycle stays lightweight

Use a small status/disposition vocabulary:

- Status: `new`, `investigating`, `awaiting_evidence`, `ready_for_review`, `closed`
- Disposition: `true_positive`, `false_positive`, `benign_expected`, `needs_monitoring`, `escalated`, `undetermined`
- Confidence: `low`, `medium`, `high`

These values support progress visibility without becoming SLA/case-management state.

### Decision: Navigation remains object-aware, not workspace-owned

Linked alerts, incidents, source IPs, evidence sources, and response registry targets should navigate back to existing authoritative views. Analyst Workspace stores the analyst's private interpretation and references; it does not own or duplicate the source object.

### Decision: CRUD gaps are secondary but included where scoped

Deleting saved investigations and evidence references is useful, but it is not the main design value. Include deletion only for private workspace records and make copy/tests explicit that deletion does not delete underlying alerts, incidents, logs, detections, or SOAR history.

## Proposed UX Architecture

- **Investigation rail:** searchable/filterable list of saved investigations with status, severity/source context, last updated time, and progress indicators.
- **Active investigation header:** title, status, disposition, confidence, linked trigger, key entities, and last updated metadata.
- **Investigation summary:** editable analyst summary plus read-only trigger/source context.
- **Timeline:** merged investigation timeline from linked alert/incident/source context and analyst milestones such as evidence saved, hypothesis changed, task completed, and conclusion recorded.
- **Evidence board:** evidence references with rationale, source link, relationship badges, and quick navigation back to the originating object.
- **Hypothesis panel:** hypotheses with confidence/status and grouped supporting/refuting/context evidence.
- **Task list:** investigation-scoped tasks, optionally tied to a hypothesis or evidence gap.
- **Conclusion panel:** final disposition, confidence, summary, and unresolved caveats.
- **Unassigned area:** legacy notes/tasks/evidence/pins without an investigation relationship remain accessible but visually secondary.

## Data Model Implications

Implementation should first inspect the existing `investigations`, `investigation_notes`, `investigation_hypotheses`, `investigation_tasks`, `evidence_references`, and `workspace_items` contracts. Prefer small additive changes over replacement.

Likely additions:

- Investigation fields for `disposition`, `confidence`, `summary`, `conclusion`, `closed_at`, and possibly `last_activity_at`.
- Evidence fields for analyst `rationale`, `relationship_type`, and parent investigation linkage.
- A small relationship table if one evidence item must relate to multiple hypotheses.
- Task fields for optional `hypothesis_id` or `evidence_reference_id`.
- API responses that bundle active investigation detail with linked private records and resolved source-object metadata.

Migration should be introduced only after implementation validates the minimal schema shape. No schema change should be used to implement enterprise collaboration or case ownership.

## API / State Shape

Prefer a dedicated active-investigation read model:

- `GET /investigations` for the private investigation list.
- `GET /investigations/:id/workspace` for the active investigation bundle.
- Mutations for investigation status/summary/conclusion, evidence rationale, hypothesis-evidence links, investigation-scoped tasks, and private deletion flows.

The frontend should consume the bundle rather than independently stitching six unrelated collections at render time.

## Risks / Trade-offs

- **Risk: Workspace becomes a second incident system** -> Keep labels and behavior private, analyst-authored, and non-authoritative for system state.
- **Risk: Relationship modeling grows too complex** -> Limit relationships to investigation, evidence, hypothesis, and task references.
- **Risk: Migration scope expands** -> Add only validated fields/tables needed for the active investigation workflow.
- **Risk: Derived story implies unsupported facts** -> Separate source facts from analyst assertions and mark incomplete context clearly.
- **Risk: Portfolio becomes CRUD-heavy** -> Prioritize reasoning flow, evidence rationale, and conclusion quality over administration screens.
- **Risk: Legacy unscoped records are orphaned** -> Keep them visible in an unassigned area with optional move/attach actions.

## Verification Strategy

- Backend/API tests for ownership, RBAC, audit logging, active investigation bundle shape, relationship validation, and no mutation of source objects.
- Migration/schema validation if schema additions are required.
- Frontend tests for active investigation selection, story sections, lifecycle edits, evidence rationale, support/refute mapping, investigation-scoped tasks, conclusions, deletion of private records, and linked-object navigation.
- Accessibility tests/review for keyboard navigation, focus behavior, live feedback, responsive layout, and no overlapping text.
- Production frontend build, focused backend tests, `git diff --check`, and strict OpenSpec validation before handoff.

## Open Questions

- Should legacy workspace notes/tasks/hypotheses remain creatable without an investigation, or should new creation require selecting/creating an investigation?
- Should one evidence reference be allowed to support multiple hypotheses in the first implementation, or should it have one relationship to keep scope smaller?
- Should closing an investigation require a disposition and conclusion, or merely warn when either is missing?
