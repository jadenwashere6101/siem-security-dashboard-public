## ADDED Requirements

### Requirement: Section Navigation Config Source of Truth
The system SHALL define a single `sectionsConfig` data source enumerating all navigable dashboard sections with `id`, `label`, `group`, and role-visibility logic.

#### Scenario: All current sections are represented
- **WHEN** `sectionsConfig` is loaded
- **THEN** it SHALL contain exactly the 12 existing section ids (`dashboard`, `soc-command-center`, `blocklist`, `threat-hunt`, `administration`, `soar-queue`, `soar-incidents`, `soar-approvals`, `soar-playbooks`, `soar-playbook-metrics`, `soar-integrations`, `soar-operations`) and no others

#### Scenario: Role visibility matches existing behavior
- **WHEN** `visibleWhen` is evaluated for a given section entry and a set of role flags
- **THEN** the result SHALL match the original inline gating condition for that section exactly, for super_admin, analyst, and viewer/unauthenticated roles

### Requirement: Single Source of Truth for Nav and Content Gating
The system SHALL drive both section navigation rendering and section content-gating from the same `sectionsConfig` entries, eliminating duplicated inline gating logic.

#### Scenario: Nav and content gating cannot diverge
- **WHEN** a section's visibility rule is defined in `sectionsConfig`
- **THEN** both the navigation button for that section and its corresponding content block SHALL read that same `visibleWhen` result, rather than each maintaining its own separate condition

### Requirement: No Visible UI or URL Behavior Change
This change SHALL NOT alter the rendered navigation UI, its visual style, section ordering, or the single-URL SPA behavior of the application.

#### Scenario: Existing UI test suite passes unmodified
- **WHEN** this change is implemented
- **THEN** `App.test.js` SHALL pass without modification, and no sidebar, hamburger, collapsible layout shell, or routing/URL change SHALL be introduced
