## 1. Persistence and Backend Contracts

- [x] 1.1 Design and add migration/schema for analyst workspaces, workspace items, investigations, notes, hypotheses, tasks, and evidence references.
- [x] 1.2 Add backend models/helpers that enforce owner identity, timestamps, reference types, private default visibility, and future collaboration placeholders.
- [x] 1.3 Add API routes/services for workspace CRUD, pins, notes, hypotheses, tasks, evidence references, and saved investigation state.
- [x] 1.4 Enforce RBAC and fail-closed ownership checks for all workspace and investigation persistence operations.
- [x] 1.5 Add audit logging for workspace creates, updates, deletes, pins, unpins, reorders, and denied access.
- [x] 1.6 Add focused backend and migration tests for CRUD, ownership isolation, RBAC denial, audit evidence, and no SOAR/detection side effects.

## 2. Frontend Services and Investigation Read Models

- [x] 2.1 Add frontend services for workspace, investigation, note, hypothesis, task, pin, and evidence-reference APIs.
- [x] 2.2 Add an InvestigationProvider/read-model layer for selected alert, incident, source IP, recon, timeline, enrichment, related detections, SOAR history, and workspace references.
- [x] 2.3 Add deterministic derivation helpers for drawer sections and Threat Story sections using existing authoritative data.
- [x] 2.4 Add tests for read-model derivation, partial data, unavailable data, unauthorized references, and no fabricated story stages.

## 3. Investigation Drawer

- [x] 3.1 Implement responsive Investigation Drawer/panel using analyst-experience-foundation primitives.
- [x] 3.2 Render alert summary, incident summary, timeline, enrichment summary, related entities, related detections, SOAR response history, recommended next steps, and evidence links.
- [x] 3.3 Support open/close from alert, incident, source IP, recon, Threat Brief, and registry-backed command contexts where available.
- [x] 3.4 Preserve workspace navigation/history and focus behavior while drawer is open and closed.
- [x] 3.5 Add focused frontend tests for drawer content, partial states, responsive behavior, Escape/backdrop close, focus return, and workspace-history preservation.

## 4. Threat Story

- [x] 4.1 Implement Threat Story read model for what happened, why it mattered, affected entities, attack progression, detections, SOAR actions, analyst observations, and status.
- [x] 4.2 Render story view using existing timeline/correlation/entity/response evidence and explicit incomplete states.
- [x] 4.3 Persist analyst observations as analyst-owned investigation/workspace state without mutating system event or incident state.
- [x] 4.4 Add tests for supported progression, missing progression, source attribution, observation persistence, and system-state separation.

## 5. Analyst Workspace

- [x] 5.1 Implement private Analyst Workspace UI for manually pinned alerts, incidents, recon items, source IPs, investigations, and evidence references.
- [x] 5.2 Implement notes, hypotheses, manual tasks/checklists, labels, organization, and removal from workspace without mutating underlying system data.
- [x] 5.3 Add pin/unpin entry points from scoped existing surfaces using existing command registry extension points where appropriate.
- [x] 5.4 Add empty/loading/error/unauthorized states and private-owner messaging.
- [x] 5.5 Add focused frontend tests for manual pinning, no automatic population, notes, hypotheses, tasks, evidence references, removal behavior, and ownership UI states.

## 6. Integration Boundaries and Regression

- [x] 6.1 Verify no shell redesign, theme redesign, Anakin surface redesign, command palette redesign, AI provider change, detection engine change, or SOAR engine redesign is introduced.
- [x] 6.2 Verify workspace mutations do not trigger SOAR actions, approvals, blocking, notifications, detection changes, or incident transitions.
- [x] 6.3 Add regression tests for existing dashboard, incident, recon, SOC command center, workspace history, Anakin command surface, and command palette behavior.
- [x] 6.4 Run focused backend tests, focused frontend tests, migration/schema validation, and affected regression tests.
- [x] 6.5 Run frontend production build if frontend changed.
- [x] 6.6 Run `git diff --check`.
- [x] 6.7 Run `openspec validate investigation-workflow --strict`.
- [x] 6.8 Run `openspec status --change investigation-workflow`.
- [x] 6.9 Prepare VM handoff notes for schema/backend deployment only after implementation is complete and commit/push/deploy are explicitly authorized.
