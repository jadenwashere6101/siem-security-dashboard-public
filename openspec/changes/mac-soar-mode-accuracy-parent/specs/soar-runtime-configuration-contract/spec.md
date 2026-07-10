## ADDED Requirements

### Requirement: Environment values are loaded as data
Worker launch artifacts SHALL load secret-bearing environment values without evaluating them as shell commands and SHALL support passwords containing quotes, whitespace, dollar signs, hashes, and shell metacharacters.

#### Scenario: SMTP password contains shell metacharacters
- **WHEN** a worker starts with a valid password containing shell-significant characters
- **THEN** startup SHALL not execute any portion of the value, SHALL not expose it, and SHALL pass the exact value to the process

### Requirement: Deterministic configuration precedence
Source-controlled service and launcher artifacts SHALL define and test one precedence order for environment files, explicit safety overrides, and operator configuration.

#### Scenario: Explicit kill-switch values are configured
- **WHEN** the service is started with the documented kill-switch layer
- **THEN** the effective process environment SHALL contain disabled real-provider guards regardless of conflicting lower-precedence values

#### Scenario: Service metadata is inspected
- **WHEN** an operator reads the effective unit description and documentation
- **THEN** the wording SHALL accurately describe whether the service is simulation-only, real-capable, or governed by an external kill-switch

### Requirement: Deployment verification handoff
The repository SHALL provide a VM deployment checklist that verifies cleanliness, effective configuration, health, rollback, and intended integration modes without printing secrets.

#### Scenario: VM AI receives a durable fix
- **WHEN** Mac changes are ready for deployment
- **THEN** the handoff SHALL identify changed artifacts, required daemon reload/restarts, sanitized checks, expected Slack/Email/Webhook state, expected Teams/firewall state, and rollback steps
