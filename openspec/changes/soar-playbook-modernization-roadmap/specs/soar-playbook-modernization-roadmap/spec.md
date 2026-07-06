## ADDED Requirements

### Requirement: Parent Roadmap Tracking
The project SHALL maintain a single lightweight parent roadmap listing the ordered child specs required for SOAR playbook modernization, with a checkbox per child spec and a dependency note where one child depends on another. The parent roadmap SHALL NOT contain implementation-level design detail — that detail belongs in each child spec.

#### Scenario: Roadmap reflects child-spec order and dependencies
- **WHEN** the parent roadmap's child-spec list is read
- **THEN** it SHALL list each of the eight identified child specs exactly once, in dependency-respecting order, with a note stating what (if anything) each item depends on.

#### Scenario: Child spec completion is tracked by checkbox
- **WHEN** a child spec identified in this roadmap is completed
- **THEN** its corresponding checkbox in this parent roadmap SHALL be marked complete, without adding implementation narrative to the parent document.

#### Scenario: Deferred items remain visible without being scheduled
- **WHEN** the parent roadmap's deferred section is read
- **THEN** it SHALL list items the audit identified but explicitly did not schedule as child specs, without checkboxes implying they are tracked work.

### Requirement: Parent-Only Change Boundary
This change SHALL NOT modify application source code, database schema, migrations, or tests, SHALL NOT create any child implementation OpenSpec changes, and SHALL NOT include implementation steps or technical design content.

#### Scenario: No functional files touched
- **WHEN** this change is reviewed via `git status`/`git diff` after being written
- **THEN** the only files added or modified SHALL be under `openspec/changes/soar-playbook-modernization-roadmap/`, with zero changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.

#### Scenario: No child specs created as part of this change
- **WHEN** this change's artifacts are created
- **THEN** no directory for any of the eight child specs (e.g., `soar-automation-path-consolidation`) SHALL be created under `openspec/changes/`.
