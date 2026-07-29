## 1. Discovery and Contract Finalization

- [x] 1.1 Inspect existing investigation/workspace frontend services, components, API routes, database tables, tests, and OpenSpec contracts without broadening scope.
- [x] 1.2 Confirm the minimal active-investigation read model and relationship model needed to support the spec.
- [x] 1.3 Decide whether evidence-to-hypothesis relationships are single-link fields or a small relationship table.
- [x] 1.4 Decide whether new workspace content must be investigation-scoped or whether unassigned creation remains supported.
- [x] 1.5 Document any final implementation constraints before editing source.

## 2. Backend and Data Model

- [x] 2.1 Add only the minimal schema migration required for investigation lifecycle, evidence rationale, hypothesis-evidence relationships, investigation task links, and conclusions.
- [x] 2.2 Preserve ownership, RBAC, audit logging, and no-system-mutation boundaries for all new and changed records.
- [x] 2.3 Add or update backend helpers/services to load an active investigation bundle with permitted source-object metadata.
- [x] 2.4 Add mutation endpoints for investigation summary/status/confidence/disposition/conclusion.
- [x] 2.5 Add mutation endpoints for evidence rationale, source metadata, delete evidence reference, and hypothesis-evidence link/unlink.
- [x] 2.6 Add mutation endpoints for investigation-scoped task create/update/delete and optional hypothesis/evidence references.
- [x] 2.7 Add delete support for private saved investigations when safe under ownership rules.
- [x] 2.8 Add backend tests for ownership, RBAC denial, audit events, relationship validation, private deletion, and no underlying alert/incident/SOAR mutation.
- [x] 2.9 Run migration dry-run/schema validation locally if a migration is introduced.

## 3. Frontend Services and State

- [x] 3.1 Add frontend service functions for investigation list, active investigation bundle, lifecycle updates, evidence rationale, relationship mutations, task mutations, and private deletion.
- [x] 3.2 Add an active-investigation state model that consumes the bundle instead of rendering unrelated collections independently.
- [x] 3.3 Preserve existing workspace navigation/history and linked-object navigation behavior.
- [x] 3.4 Add consistent loading, success, idempotent, and failure feedback for new investigation workspace mutations.
- [x] 3.5 Ensure stale or unauthorized source-object metadata is represented explicitly without fabricating facts.

## 4. Investigation-Centered Workspace UI

- [x] 4.1 Replace the equal-weight storage-card layout with an investigation rail plus dominant active investigation detail layout.
- [x] 4.2 Add empty/no-investigation state that guides the analyst to start from an alert, incident, or source context.
- [x] 4.3 Add active investigation header with title, status, confidence, disposition, linked trigger, key entities, and last activity.
- [x] 4.4 Add investigation summary/story sections for trigger context, what happened, current assessment, evidence summary, open questions, and conclusion.
- [x] 4.5 Add evidence board with rationale, source type/id, relationship badges, timestamps, delete action, and navigation back to source objects.
- [x] 4.6 Add hypothesis panel with confidence/status and grouped supporting, refuting, and contextual evidence.
- [x] 4.7 Add investigation-scoped task list with optional hypothesis/evidence reference, complete/reopen, and delete actions.
- [x] 4.8 Add investigation timeline that distinguishes source-object events from analyst milestones.
- [x] 4.9 Add conclusion/disposition editing with caveats for unresolved tasks, missing disposition, or low confidence.
- [x] 4.10 Keep unassigned legacy workspace content discoverable but secondary.

## 5. Integration with Existing Investigation Flow

- [x] 5.1 Update Save/Open Investigation flows so saved investigations can be opened directly in the active workspace detail.
- [x] 5.2 Preserve the single-overlay Alert Details -> Investigation Drawer behavior from post-deployment remediation.
- [x] 5.3 Preserve Investigation Drawer context while avoiding a second competing investigation model.
- [x] 5.4 Ensure Anakin/palette extension points, if touched, use existing command registry patterns without redesign.
- [x] 5.5 Ensure alerts, incidents, source IPs, response registry items, and evidence sources navigate back to authoritative existing views.

## 6. Frontend Tests and Accessibility

- [x] 6.1 Add focused tests for active investigation selection, empty state, and unassigned content handling.
- [x] 6.2 Add focused tests for summary/story rendering and source-fact versus analyst-authored distinction.
- [x] 6.3 Add focused tests for lifecycle status, confidence, disposition, conclusion, and closed-investigation caveats.
- [x] 6.4 Add focused tests for evidence rationale, source navigation, private evidence deletion, and no underlying source mutation.
- [x] 6.5 Add focused tests for hypothesis support/refute/context relationships and unlink behavior.
- [x] 6.6 Add focused tests for investigation-scoped task create/update/delete and optional relationship context.
- [x] 6.7 Add focused tests for investigation timeline source labels and partial-data states.
- [x] 6.8 Verify keyboard navigation, focus order, live feedback, responsive layout, dark-theme readability, and text containment.

## 7. Scope and Verification Gates

- [x] 7.1 Verify no multi-user collaboration, assignment workflow, approvals, SLA tracking, reporting engine, enterprise case ownership, source-IP watchlist, heavy automation, or major SOAR change is introduced.
- [x] 7.2 Verify Analyst Workspace records remain private analyst context and do not become authoritative alert, incident, SOAR, detection, or response state.
- [x] 7.3 Run focused backend tests and migration/schema validation if backend/schema changes are introduced.
- [x] 7.4 Run focused frontend tests for the investigation-centered workspace scope.
- [x] 7.5 Run frontend production build.
- [x] 7.6 Perform practical visual and accessibility verification for desktop and narrow viewports.
- [x] 7.7 Run `git diff --check`.
- [x] 7.8 Run `openspec validate investigation-centered-workspace --strict`.
- [x] 7.9 Run `openspec status --change investigation-centered-workspace`.
