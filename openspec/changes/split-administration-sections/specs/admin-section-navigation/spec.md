## ADDED Requirements

### Requirement: Administration group exposes separate workflow items
The system SHALL expose Detection Rules, Users, and Audit Logs as separate sidebar navigation items under the existing Administration group for users who are allowed to access administration features.

#### Scenario: Super admin sees split administration items
- **WHEN** a super-admin user views the sidebar
- **THEN** the Administration group contains `Detection Rules`, `Users`, and `Audit Logs`
- **AND** the bundled `Administration` item is not shown as a normal sidebar destination

#### Scenario: Non-admin users do not see administration items
- **WHEN** a viewer or analyst user views the sidebar
- **THEN** `Detection Rules`, `Users`, and `Audit Logs` are not visible

### Requirement: Split administration items preserve existing role gating
The system SHALL gate each split Administration item with the same super-admin-only frontend visibility behavior used by the previous bundled Administration section unless the live code already defines a different gate before implementation begins.

#### Scenario: Super admin visibility is preserved
- **WHEN** role flags identify the current user as a super admin
- **THEN** `detection-rules`, `admin-users`, and `admin-audit-logs` are visible sections

#### Scenario: Analyst and viewer visibility is preserved
- **WHEN** role flags identify the current user as an analyst or viewer
- **THEN** `detection-rules`, `admin-users`, and `admin-audit-logs` are not visible sections

### Requirement: Administration sections render one matching panel
The system SHALL render only the panel that corresponds to the active split Administration section.

#### Scenario: Detection rules section renders detection rules panel
- **WHEN** a super-admin user activates `Detection Rules`
- **THEN** the content area renders `DetectionRulesPanel`
- **AND** it does not render `AdminUsersPanel` or `AuditLogPanel` for that active section

#### Scenario: Users section renders admin users panel
- **WHEN** a super-admin user activates `Users`
- **THEN** the content area renders `AdminUsersPanel`
- **AND** it does not render `DetectionRulesPanel` or `AuditLogPanel` for that active section

#### Scenario: Audit logs section renders audit log panel
- **WHEN** a super-admin user activates `Audit Logs`
- **THEN** the content area renders `AuditLogPanel`
- **AND** it does not render `DetectionRulesPanel` or `AdminUsersPanel` for that active section

### Requirement: Existing SPA and sidebar behavior is preserved
The system SHALL keep the existing single-URL SPA navigation model and sidebar shell behavior while splitting the Administration items.

#### Scenario: Navigation does not create routes
- **WHEN** a user navigates between `Detection Rules`, `Users`, and `Audit Logs`
- **THEN** the app updates active-section state through the existing sidebar mechanism
- **AND** no React Router route, URL path, query parameter, hash, browser history, or deep-link behavior is introduced

#### Scenario: Sidebar shell behavior remains unchanged
- **WHEN** a user interacts with existing sidebar controls and non-administration items
- **THEN** grouping, active highlighting, collapse behavior, and existing section navigation continue to work as before
