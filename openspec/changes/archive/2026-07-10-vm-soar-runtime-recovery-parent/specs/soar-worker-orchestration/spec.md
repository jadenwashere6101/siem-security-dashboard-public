## MODIFIED Requirements

### Requirement: Deployment safety
The system SHALL define deployment practices for daemonized execution that preserve current runtime safety constraints and expose deterministic environment precedence.

#### Scenario: systemd deployment is prepared
- **WHEN** deployment artifacts are installed
- **THEN** they SHALL include environment requirements, precedence rules, logging expectations, restart policy, graceful shutdown semantics, and descriptions that match effective behavior

#### Scenario: Real-delivery kill-switch is invoked
- **WHEN** an operator activates the documented kill-switch
- **THEN** the effective worker process environment SHALL disable every real notification adapter and verification SHALL fail closed if that state cannot be proven

#### Scenario: Simulation-only integrations remain disabled
- **WHEN** the daemonized worker is deployed or restarted
- **THEN** it SHALL NOT enable autonomous real firewall actions, real Teams notifications, or real execution for monitor or flag_high_priority
