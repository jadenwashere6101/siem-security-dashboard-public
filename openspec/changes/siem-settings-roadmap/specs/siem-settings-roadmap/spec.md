## ADDED Requirements

### Requirement: Parent Roadmap Tracks Settings Suite
The project SHALL maintain a parent roadmap for the SIEM Settings feature suite that lists the planned child specs, their sequencing, their scope boundaries, and their validation/deployment gates without implementing application behavior.

#### Scenario: Child specs are listed
- **WHEN** the roadmap is reviewed
- **THEN** it SHALL list `siem-settings-foundation`, `siem-display-preferences`, and `siem-alert-notification-preferences` as future child specs.

#### Scenario: Roadmap remains coordination-only
- **WHEN** this parent change is reviewed
- **THEN** it SHALL NOT modify application source files, tests, backend schema, migrations, deployment scripts, or runtime configuration.

### Requirement: Defaults Preserve Current UI Behavior
The roadmap SHALL state that future settings defaults preserve the current SIEM UI look and behavior unless the user changes a setting.

#### Scenario: Dark UI remains default
- **WHEN** a future settings child spec is created from this roadmap
- **THEN** it SHALL preserve the current dark UI as the default.

#### Scenario: No theme switch is planned
- **WHEN** the roadmap scope boundaries are reviewed
- **THEN** they SHALL state that no light/dark theme setting or theme switch will be added.

### Requirement: Storage Scope Is Explicit
The roadmap SHALL clearly separate frontend-only localStorage v1 settings from backend-dependent or future backend/user-scoped settings.

#### Scenario: v1 storage direction is localStorage
- **WHEN** the roadmap storage recommendation is reviewed
- **THEN** it SHALL state that v1 settings should use frontend localStorage with safe defaults and malformed-storage handling.

#### Scenario: Backend preferences are out of scope for v1
- **WHEN** the roadmap backend scope is reviewed
- **THEN** it SHALL state that backend DB/user-scoped settings are out of scope for v1 unless a child spec explicitly adds them.

### Requirement: Risks And Unknowns Are Tracked
The roadmap SHALL preserve known risks and unknowns so future child specs can either fix them or implement around them.

#### Scenario: Timestamp and polling risks are visible
- **WHEN** the roadmap risks are reviewed
- **THEN** fragmented timestamp rendering and separate alert/Live Logs pollers SHALL be listed as risks.

#### Scenario: Backend-dependent setting risks are visible
- **WHEN** the roadmap risks are reviewed
- **THEN** backend query limits, user-scoped persistence, notification triggering, and localStorage limitations SHALL be listed as risks or unknowns.

### Requirement: Phase Checklist Is Included
The roadmap SHALL include checklists for audit, child spec creation, implementation sequencing, validation, deployment/rebuild, and future backend/user-preference expansion.

#### Scenario: Required phases are present
- **WHEN** `tasks.md` is reviewed
- **THEN** it SHALL include checklist sections for audit, child spec creation, implementation sequencing, validation, deployment/rebuild, and future backend/user-preference expansion.
