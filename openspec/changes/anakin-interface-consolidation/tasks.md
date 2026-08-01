## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `anakin-interface-consolidation`.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. Shared Frontend Workflow Plumbing

- [x] 2.1 Add frontend service support for `POST /ai/workflows`.
- [x] 2.2 Add shared workflow control/menu helpers so surfaces do not duplicate action-specific behavior.
- [x] 2.3 Update global Anakin surface to prioritize freeform Ask Anakin with compact workflow shortcuts.
- [x] 2.4 Render workflow classification, model/profile metadata, chooser state, and truthful lifecycle stages.

## 3. Surface Consolidation

- [x] 3.1 Consolidate Dashboard controls to Ask Anakin, Quick Explain, and Deep Investigate.
- [x] 3.2 Consolidate Alert Details controls to Quick Explain, Deep Investigate, Decision Support, and Generate Artifact menu.
- [x] 3.3 Consolidate Source IP controls to Quick Explain, Deep Investigate, Decision Support, and Generate Artifact menu.
- [x] 3.4 Consolidate Incident controls to Deep Investigate, Decision Support, and Generate Artifact menu.
- [x] 3.5 Consolidate SOC Command Center recon controls to Deep Investigate, Decision Support, and Generate Artifact menu.
- [x] 3.6 Consolidate Response Registry controls to Decision Support, Deep Investigate, and supported Generate Artifact menu.
- [x] 3.7 Ensure command palette exposes one canonical entry per workflow and preserves role-aware Repo Assistant/SOC Briefing behavior.

## 4. Inventory And Tests

- [x] 4.1 Update frontend/acceptance inventory expectations for canonical workflow controls.
- [x] 4.2 Add focused tests proving remaining controls, removed duplicates, workflow routing, chooser rendering, artifact menus, and safety boundaries.
- [x] 4.3 Run focused frontend tests and production build.
- [x] 4.4 Run backend compatibility and offline acceptance tests.

## 5. Verification

- [x] 5.1 Run Python compilation for changed backend test/support modules if applicable.
- [x] 5.2 Run `git diff --check`.
- [x] 5.3 Run `openspec validate anakin-interface-consolidation --strict`.
- [x] 5.4 Confirm combined `git status --short`.
