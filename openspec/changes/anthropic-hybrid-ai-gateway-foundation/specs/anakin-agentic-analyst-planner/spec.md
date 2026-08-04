## RENAMED Requirements

- FROM: `### Requirement: Planner capability is registered with the configured local provider`
- TO: `### Requirement: Planner capability is registered with the configured provider`
- FROM: `### Requirement: Planner uses a dedicated local planning profile`
- TO: `### Requirement: Planner uses a dedicated planning profile`

## MODIFIED Requirements

### Requirement: Planner repair preserves strict semantic relationships
The system SHALL provide at most one repair attempt with precise schema and cross-field validation feedback. The repair SHALL use the same Anthropic provider/model profile as the initial proposal, preserve the first valid planner decisions wherever possible, and count as an independently authorized, logged, and accounted paid request. The repaired plan MUST satisfy the unchanged strict contract; malformed field types, unsupported sort semantics, missing clarification fields, contradictory strategy/evidence combinations, and changes to repair-stable fields MUST remain rejected. The system MUST NOT silently switch repair to Ollama or another provider, and MUST fail gracefully without a repair call when remaining budget cannot authorize it.

#### Scenario: Contradictory repaired plan
- **WHEN** a repair changes strategy to `direct_answer` while retaining insufficient evidence or a tool requirement
- **THEN** deterministic validation rejects the repaired plan and no capability executes

#### Scenario: Repair preserves valid decisions
- **WHEN** an initial Anthropic proposal contains a valid action classification or other repair-stable planner decision but fails another validation rule
- **THEN** the repair request SHALL identify the precise defect and require the valid decision to remain unchanged
- **AND** a repair that changes that decision SHALL fail validation

#### Scenario: Repair is separately budgeted and logged
- **WHEN** an invalid initial proposal is eligible for repair and sufficient daily budget remains
- **THEN** the gateway SHALL authorize, record, and account the same Anthropic provider/model repair as a distinct request linked to the initial attempt

#### Scenario: Repair budget is insufficient
- **WHEN** the remaining daily budget cannot support the conservative cost of the one repair call
- **THEN** Anthropic SHALL not be contacted, no local provider SHALL be substituted, and the planner SHALL return its truthful non-executing failure outcome

### Requirement: Planner capability is registered with the configured provider
The system SHALL register `agentic_analyst_planning` through the normal provider capability contract. The configured Anthropic provider SHALL accept that capability and reach generation only through the gateway, while providers and capabilities that are not explicitly registered MUST continue to fail closed. The planning profile SHALL prohibit Ollama fallback and SHALL require gateway mode, readiness, and daily budget authorization for both proposal and repair.

#### Scenario: Planner reaches Anthropic generation
- **WHEN** the gateway receives an `agentic_analyst_planning` request using the trusted `agentic_planning` profile and all paid-use guards succeed
- **THEN** Anthropic capability validation SHALL accept it and invoke generation with normalized gateway metadata

#### Scenario: Paid guard blocks planner generation
- **WHEN** mode, configuration, readiness, or daily budget authorization blocks the `agentic_planning` request
- **THEN** no provider generation SHALL occur and the planner SHALL receive the corresponding normalized gateway failure

#### Scenario: Unknown capability remains blocked
- **WHEN** the gateway receives an unregistered capability
- **THEN** it returns provider-incapable without invoking generation

### Requirement: Planner uses a dedicated planning profile
The system SHALL route initial and repair planner requests through the approved `agentic_planning` profile using its backend-configured Anthropic provider and approved Anthropic model. The profile SHALL retain an 8,000-character prompt limit, 1,024-token output limit, 90-second per-generation timeout, and `0.1` temperature unless a separately validated profile change updates those existing contract bounds. It SHALL prohibit local fallback, and each proposal and repair SHALL independently satisfy paid-mode, readiness, and budget policy. Existing Quick Explain and other workflow profile assignments MUST remain unchanged and Ollama-only.

#### Scenario: Planner profile is observable
- **WHEN** the planner submits a proposal or its one bounded repair
- **THEN** the gateway and provider metadata SHALL identify profile `agentic_planning`, provider Anthropic, and the backend-approved Anthropic model

#### Scenario: Planner repair uses an independent timeout and budget authorization
- **WHEN** an invalid initial result requires the one bounded repair
- **THEN** the provider SHALL apply the planner timeout independently to the initial and repair generations
- **AND** the gateway SHALL independently authorize and account the repair against the daily budget

#### Scenario: Quick Explain profile is unchanged
- **WHEN** Quick Explain executes outside the planner generation stage
- **THEN** it SHALL continue using `fast_triage` and its existing Ollama `llama3.2:3b` assignment without paid fallback

#### Scenario: Contradictory Anthropic plan
- **WHEN** the model combines `direct_answer` with a tool category, omits required evidence for a lookup, leaves reasoning or stopping conditions empty, or otherwise violates strategy relationships
- **THEN** deterministic validation SHALL reject the plan, permit at most one bounded same-provider repair, and fail closed if repair is blocked or remains invalid

#### Scenario: Anthropic failure has no weak-model fallback
- **WHEN** proposal or repair is unavailable, times out, is budget-blocked, or fails validation
- **THEN** the planner SHALL return its existing graceful unavailable or invalid-plan outcome without routing to Ollama
