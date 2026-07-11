## ADDED Requirements

### Requirement: Correlation-preserving presentation destination
Cross-workspace response navigation SHALL carry both canonical correlation context and an explicit presentation destination without altering API request semantics.

#### Scenario: Incident opens Response Registry
- **WHEN** an analyst opens Response Registry from an incident
- **THEN** the target SHALL retain related incident and source-IP context while scrolling/focusing the relevant registry region

#### Scenario: Playbook opens Response Registry
- **WHEN** an analyst opens Response Registry from a playbook execution
- **THEN** the target SHALL retain all available alert, incident, and indicator identifiers while scrolling/focusing the relevant registry region

