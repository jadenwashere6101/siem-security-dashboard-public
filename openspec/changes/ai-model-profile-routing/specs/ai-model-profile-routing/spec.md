## ADDED Requirements

### Requirement: Backend-owned AI model profiles
The system SHALL route AI generation requests through backend-owned semantic profiles rather than client-selected model names or timeout values.

#### Scenario: Quick AI actions use fast triage
- **WHEN** dashboard, alert, source-IP, incident, recon, response registry, command-palette, or general chat quick AI actions request generation
- **THEN** the backend SHALL select `fast_triage`
- **AND** the provider request SHALL use the configured fast model, timeout, prompt budget, output budget, and temperature.

#### Scenario: Guided analysis uses guided profile
- **WHEN** a guided investigation or review-only AI draft requests generation
- **THEN** the backend SHALL select `guided_analysis`.

#### Scenario: Briefings use deep briefing
- **WHEN** manual or scheduled SOC briefing synthesis requests generation
- **THEN** the backend SHALL select `deep_briefing`
- **AND** paid fallback SHALL remain disabled for that request.

#### Scenario: Repo assistant uses developer profile
- **WHEN** Repo Architecture Assistant chat requests generation
- **THEN** the backend SHALL select `developer_assistant`
- **AND** SHALL NOT route repository/source-code assistance through `fast_triage`.

### Requirement: Complete AI invocation inventory
The system SHALL maintain a machine-readable inventory mapping every known AI invocation path to exactly one approved profile.

#### Scenario: Inventory covers backend allowlists
- **WHEN** supported explain actions, draft types, guided investigation workflows, SOC briefing synthesis, or repo assistant chat are added or changed
- **THEN** tests SHALL fail unless the inventory maps the path to an approved profile.

#### Scenario: Clients cannot select arbitrary models
- **WHEN** a client payload includes arbitrary model, timeout, or profile fields
- **THEN** the backend SHALL ignore or reject those fields and use trusted action/task-to-profile mapping.

### Requirement: AI button contract correctness
Every frontend AI button SHALL send an action/context/draft/investigation payload accepted by the backend.

#### Scenario: SOC Command Center recon explain works
- **WHEN** the SOC Command Center "Explain recon" button sends `context_type=recon_activity` and `action=explain_recon_activity`
- **THEN** the backend SHALL accept the action
- **AND** route it to `fast_triage`.

#### Scenario: SOC Command Center recon guided actions work
- **WHEN** SOC Command Center guided investigation or draft buttons are used
- **THEN** the backend SHALL accept `recon_activity` context with `activity_id`
- **AND** route guided investigation to `guided_analysis`
- **AND** route drafts to `guided_analysis`.

#### Scenario: Generic workspace commands normalize safely
- **WHEN** a command-palette Anakin command uses a frontend workspace section ID
- **THEN** the backend SHALL normalize it to a supported context type or safe general context
- **AND** SHALL NOT fail solely because the frontend section ID contains hyphens or is not a domain object type.

### Requirement: Profile metadata and failure clarity
AI responses SHALL include sanitized profile/model metadata and preserve existing disabled, unavailable, timeout, fallback-blocked, and failed states.

#### Scenario: Successful response shows profile
- **WHEN** a provider returns successfully
- **THEN** response metadata SHALL include provider, model, status, profile, task category, timeout seconds, and max output tokens.

#### Scenario: Timeout is profile-specific
- **WHEN** a local provider times out
- **THEN** response metadata SHALL include the selected profile and timeout
- **AND** the user-facing error SHALL distinguish local provider timeout from provider unavailable.

### Requirement: Local-only and no paid fallback
Profile routing SHALL NOT introduce paid fallback or production mutation paths.

#### Scenario: Paid fallback remains blocked
- **WHEN** a profile-routed local request fails and the profile is local-only or paid fallback disabled
- **THEN** the gateway SHALL NOT attempt paid fallback
- **AND** metadata SHALL report no paid request.

#### Scenario: No production action is introduced
- **WHEN** AI explain, chat, draft, investigation, briefing, or repo assistant requests run
- **THEN** they SHALL preserve read-only, RBAC, tool-boundary, audit, and no-direct-SQL/no-shell/no-production-mutation constraints.
