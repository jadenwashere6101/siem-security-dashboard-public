## MODIFIED Requirements

### Requirement: Provider-neutral configuration
The system SHALL load AI gateway configuration through a provider-neutral configuration layer that supports `disabled`, `local_only`, `ask_before_paid_fallback`, and `automatic_fallback` modes. Non-secret effective policy SHALL combine source-controlled safe defaults with validated PostgreSQL runtime settings, while provider credentials SHALL remain environment-only. No paid provider is required for valid Ollama-only operation.

#### Scenario: Disabled is the safe default
- **WHEN** no valid AI gateway mode is configured
- **THEN** the gateway runs in `disabled` mode and returns a clear disabled status without contacting any provider

#### Scenario: Invalid or unreadable policy fails closed
- **WHEN** the configured gateway mode or paid policy is invalid or the durable policy cannot be read safely
- **THEN** the gateway SHALL set its effective mode to `local_only`, prevent paid execution, and report a configuration-error state
- **AND** it SHALL set its effective mode to `disabled` instead if validated source-controlled local defaults are unavailable or invalid

#### Scenario: Paid provider is optional
- **WHEN** local AI is configured but Anthropic settings or credentials are absent
- **THEN** valid Ollama-assigned requests can still execute according to local-only policy and no paid provider is required

#### Scenario: Credentials remain outside runtime policy
- **WHEN** effective provider-neutral configuration is persisted, audited, or returned by an API
- **THEN** it contains no provider credential or secret value

### Requirement: Local-first provider routing
The system SHALL replace unconditional global local-first selection with trusted profile-specific provider/model selection while preserving the gateway as the sole routing authority. `disabled` SHALL block all execution; `local_only` SHALL permit only Ollama-assigned profiles; `ask_before_paid_fallback` SHALL require established confirmation before any paid execution; and `automatic_fallback` SHALL permit an explicitly Anthropic-assigned profile only when paid execution, configuration, and budget policy authorize it. Ollama-only profiles MUST NOT become paid-fallback eligible.

#### Scenario: Ollama-assigned profile succeeds
- **WHEN** the gateway mode permits execution and an Ollama-assigned provider is configured, capable, and successful within its timeout
- **THEN** the gateway returns that response with local provider metadata and no paid attempt

#### Scenario: Anthropic profile is blocked in local-only mode
- **WHEN** the gateway mode is `local_only` and the trusted profile is assigned to Anthropic
- **THEN** the gateway returns a clear policy-blocked result without calling Anthropic or substituting Ollama

#### Scenario: Paid execution requires confirmation in ask mode
- **WHEN** an Anthropic-assigned request reaches the gateway in `ask_before_paid_fallback` without established paid confirmation
- **THEN** the gateway returns `fallback_requires_confirmation` and does not contact Anthropic

#### Scenario: Automatic hybrid routing is guarded
- **WHEN** an Anthropic-assigned request reaches the gateway in `automatic_fallback`
- **THEN** Anthropic is called only if the profile assignment, paid enabled state, provider configuration, and atomic daily budget authorization all succeed
- **AND** otherwise the gateway returns the applicable blocked, configuration, provider, or budget outcome

#### Scenario: Client provider choice is ignored
- **WHEN** a client supplies provider, model, profile, fallback, timeout, or budget fields
- **THEN** those fields SHALL be rejected or ignored and SHALL NOT alter trusted gateway routing

### Requirement: Provider capability and readiness detection
The system SHALL expose secret-free readiness and capability information for every registered provider that distinguishes disabled, configured, unavailable, timeout, incapable, authentication-error, budget-blocked, configuration-error, and ready states as applicable. Provider-specific health logic SHALL remain behind the provider abstraction and MUST NOT make a billable generation request merely to serve status.

#### Scenario: Readiness excludes secrets
- **WHEN** provider readiness is serialized for an API response, log, or audit event
- **THEN** it includes provider keys, approved model names, boolean configuration state, missing environment variable names, and normalized status codes but no secret values, authorization material, raw provider errors, or sensitive endpoints

#### Scenario: Capability check prevents unsuitable provider use
- **WHEN** the profile-selected provider reports that it cannot handle the requested capability
- **THEN** the gateway treats the provider as incapable and applies only the profile and mode policy
- **AND** it SHALL NOT invent a provider route outside that policy

#### Scenario: Budget affects paid readiness
- **WHEN** no daily paid budget remains
- **THEN** Anthropic readiness SHALL expose a sanitized budget-blocked policy state even if provider connectivity is otherwise healthy

### Requirement: Standard AI request metadata
The system SHALL return standardized AI request metadata for every gateway response, including provider, model, profile, task category, gateway mode, status, read-only state, latency, input/output/total tokens or labeled estimates, cost or labeled estimate, local/paid flags, fallback attempt, fallback reason, budget outcome, and error code when applicable.

#### Scenario: Local response shows no API cost
- **WHEN** an Ollama provider handles a request
- **THEN** response metadata marks `local_request=true`, `paid_request=false`, and `estimated_cost_usd=0`

#### Scenario: Anthropic response identifies accounting
- **WHEN** Anthropic handles an authorized request
- **THEN** response metadata identifies the paid provider/model/profile, provider latency, token usage or estimates, cost or estimate, and successful budget authorization without exposing sensitive content

#### Scenario: Failed response still has metadata
- **WHEN** no provider successfully handles a request
- **THEN** the gateway still returns metadata describing the mode, trusted provider path, failure status, fallback or budget reason, and error code

### Requirement: Authenticated AI status endpoint
The system SHALL expose a thin authenticated `/ai/status` endpoint using existing Flask blueprint and RBAC conventions. It SHALL report sanitized effective gateway configuration, provider readiness, provider/model assignment for every profile, effective mode, and current UTC budget/accounting summary without mutating policy or issuing billable generation. Token and cost values MUST carry provenance and MUST NOT be represented as actual billed usage unless the provider reported that exact value.

#### Scenario: Analyst or super administrator can read AI status
- **WHEN** an authenticated analyst or super administrator requests AI status
- **THEN** the endpoint returns sanitized effective gateway mode, provider readiness, profile routing, daily budget used and remaining, and token/cost values labeled `estimated` or `provider_reported`

#### Scenario: Usage provenance is explicit
- **WHEN** `/ai/status` serializes token or cost usage
- **THEN** a value SHALL be labeled `provider_reported` only when the provider returned that exact value
- **AND** calculated, reserved, or otherwise inferred values SHALL remain labeled `estimated` and SHALL NOT be described as actual billed usage

#### Scenario: Unauthenticated request is rejected
- **WHEN** a request without a valid session requests AI status
- **THEN** the endpoint is rejected by existing authentication behavior

#### Scenario: Insufficient role is rejected
- **WHEN** an authenticated role outside the analyst/super-admin event-read boundary requests AI status
- **THEN** the endpoint rejects the request through existing RBAC behavior

#### Scenario: Status never exposes secrets
- **WHEN** status is returned in any provider or accounting state
- **THEN** it contains no API key, secret, authorization material, raw prompt/completion, or sensitive endpoint
