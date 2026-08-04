## MODIFIED Requirements

### Requirement: Backend-owned AI model profiles
The system SHALL route AI generation requests through backend-owned semantic profiles that select provider, model, timeout, prompt budget, output budget, temperature, and paid-fallback eligibility rather than accepting those controls from clients. The gateway SHALL remain the only component that resolves a trusted profile assignment into provider execution.

#### Scenario: Quick AI actions use fast triage
- **WHEN** dashboard, alert, source-IP, incident, recon, response registry, command-palette, or general chat quick AI actions request generation
- **THEN** the backend SHALL select `fast_triage`
- **AND** the gateway SHALL use its Ollama provider assignment and configured fast model, timeout, prompt budget, output budget, and temperature

#### Scenario: Planner uses Anthropic planning profile
- **WHEN** Anakin requests an initial plan or its one allowed repair
- **THEN** the backend SHALL select `agentic_planning`
- **AND** the gateway SHALL use its Anthropic provider/model assignment subject to mode, readiness, and daily budget authorization

#### Scenario: Guided analysis uses guided profile
- **WHEN** a guided investigation or review-only AI draft requests generation
- **THEN** the backend SHALL select `guided_analysis`
- **AND** the gateway SHALL use its Ollama assignment with paid fallback prohibited

#### Scenario: Briefings use deep briefing
- **WHEN** manual or scheduled SOC briefing synthesis requests generation
- **THEN** the backend SHALL select `deep_briefing`
- **AND** the gateway SHALL use its Ollama assignment with paid fallback prohibited

#### Scenario: Repo assistant uses developer profile
- **WHEN** Repo Architecture Assistant chat requests generation
- **THEN** the backend SHALL select `developer_assistant`
- **AND** SHALL NOT route repository/source-code assistance through `fast_triage` or Anthropic

### Requirement: Complete AI invocation inventory
The system SHALL maintain a machine-readable inventory mapping every known AI invocation path to exactly one approved profile and every approved profile to exactly one active provider/model assignment. The initial assignments SHALL be Ollama for `fast_triage`, `guided_analysis`, `deep_briefing`, and `developer_assistant`, and Anthropic for `agentic_planning`.

#### Scenario: Inventory covers backend allowlists
- **WHEN** supported explain actions, draft types, guided investigation workflows, SOC briefing synthesis, repo assistant chat, or planner stages are added or changed
- **THEN** tests SHALL fail unless the inventory maps the path to an approved profile and the profile to a registered provider/model

#### Scenario: Clients cannot select arbitrary routing
- **WHEN** a client payload includes arbitrary provider, model, timeout, profile, fallback, token, cost, or budget fields
- **THEN** the backend SHALL ignore or reject those fields and use trusted action/task-to-profile and profile-to-provider mappings

#### Scenario: Every profile has an explicit assignment
- **WHEN** profile configuration is loaded or startup validation runs
- **THEN** missing, duplicate, unknown, or incompatible provider/model assignments SHALL fail closed rather than falling back to a global provider order

### Requirement: Profile metadata and failure clarity
AI responses SHALL include sanitized profile/provider/model metadata and preserve disabled, unavailable, timeout, incapable, confirmation-required, fallback-blocked, budget-blocked, configuration-error, and failed states.

#### Scenario: Successful response shows trusted route
- **WHEN** a provider returns successfully
- **THEN** response metadata SHALL include provider, model, status, profile, task category, timeout seconds, maximum output tokens, latency, and local/paid classification

#### Scenario: Timeout is profile-specific
- **WHEN** a selected provider times out
- **THEN** response metadata SHALL include the selected profile, provider, and timeout
- **AND** the user-facing error SHALL distinguish provider timeout from provider unavailable or budget blocked

#### Scenario: Planner budget block is explicit
- **WHEN** `agentic_planning` cannot obtain paid budget authorization
- **THEN** metadata SHALL identify the profile and budget-blocked outcome without exposing cap-sensitive credentials or attempting Ollama substitution

### Requirement: Local-only and no paid fallback
Profile routing SHALL preserve read-only and no-production-mutation constraints. Ollama-only profiles SHALL prohibit paid fallback in every gateway mode. The Anthropic-assigned `agentic_planning` profile SHALL be eligible for paid execution only through gateway mode and budget authorization and SHALL prohibit silent local fallback.

#### Scenario: Ollama profile failure remains local
- **WHEN** an Ollama-assigned profile request fails, times out, or is incapable
- **THEN** the gateway SHALL NOT attempt Anthropic
- **AND** metadata SHALL report no paid request

#### Scenario: Anthropic planner failure does not switch provider
- **WHEN** an `agentic_planning` proposal or repair is blocked, unavailable, times out, fails, or returns invalid output
- **THEN** the gateway SHALL NOT attempt Ollama or another weaker provider for that planner call

#### Scenario: No production action is introduced
- **WHEN** AI explain, chat, draft, investigation, briefing, repo assistant, or planning requests run
- **THEN** they SHALL preserve read-only, RBAC, tool-boundary, audit, no-direct-SQL, no-shell, and no-production-mutation constraints
