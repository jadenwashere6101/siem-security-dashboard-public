## ADDED Requirements

### Requirement: AI gateway is on-demand and read-only
The system SHALL provide an AI gateway foundation that runs only in response to an explicit authenticated request and SHALL NOT perform background analysis, schedule recurring inference, mutate production data, execute shell commands, or give providers direct database access.

#### Scenario: No autonomous background inference
- **WHEN** the backend application starts with AI gateway configuration present
- **THEN** no AI provider request is made until an authenticated route or service call explicitly invokes the AI gateway

#### Scenario: Gateway request is read-only
- **WHEN** an AI gateway request is processed
- **THEN** the gateway response metadata marks the request as read-only and no alert, incident, SOAR, configuration, detection, or database mutation is performed by the gateway

### Requirement: Provider-neutral configuration
The system SHALL load AI gateway configuration through a provider-neutral configuration layer that supports `disabled`, `local_only`, `ask_before_paid_fallback`, and `automatic_fallback` modes without requiring any paid provider to be configured.

#### Scenario: Disabled is the safe default
- **WHEN** no AI gateway mode is configured
- **THEN** the gateway runs in `disabled` mode and returns a clear disabled status without contacting any provider

#### Scenario: Invalid mode fails closed
- **WHEN** the configured AI gateway mode is not recognized
- **THEN** the gateway treats the configuration as disabled or configuration-error state and does not contact any provider

#### Scenario: Paid provider is optional
- **WHEN** local AI is configured but paid provider settings are absent
- **THEN** local requests can still be evaluated according to local-only routing and no paid provider is required

### Requirement: Local-first provider routing
The system SHALL attempt the configured local provider first whenever the gateway mode allows AI execution and the local provider is configured, reachable, and capable of the request.

#### Scenario: Local provider succeeds
- **WHEN** the gateway mode allows execution and the local provider returns a successful response within its timeout
- **THEN** the gateway returns that response with metadata indicating the local provider and no paid fallback attempt

#### Scenario: Local provider unavailable in local-only mode
- **WHEN** the gateway mode is `local_only` and the local provider is unavailable, times out, or is incapable
- **THEN** the gateway returns a clear failure status and does not call a paid provider

#### Scenario: Paid fallback requires policy permission
- **WHEN** the local provider cannot satisfy a request and the gateway mode is `ask_before_paid_fallback`
- **THEN** the gateway returns `fallback_requires_confirmation` and does not call a paid provider

#### Scenario: Automatic fallback is guarded
- **WHEN** the local provider cannot satisfy a request and the gateway mode is `automatic_fallback`
- **THEN** a paid provider is called only if paid fallback is explicitly enabled and configured; otherwise the gateway returns `fallback_blocked`

### Requirement: Provider capability and readiness detection
The system SHALL expose secret-free provider readiness and capability information that distinguishes disabled, configured, unavailable, timeout, incapable, and ready states.

#### Scenario: Readiness excludes secrets
- **WHEN** AI provider readiness is serialized for an API response or log
- **THEN** it includes provider keys, model names, boolean configuration state, missing env var names, and status codes but no secret values or credential-bearing URLs

#### Scenario: Capability check prevents unsuitable provider use
- **WHEN** a provider reports that it cannot handle a requested capability
- **THEN** the gateway treats the provider as incapable and applies the configured fallback policy

### Requirement: Bounded timeout behavior
The system SHALL apply explicit per-provider timeouts and classify timeout failures without blocking indefinitely.

#### Scenario: Local timeout is classified
- **WHEN** the local provider does not respond within the configured local timeout
- **THEN** the gateway returns or routes from a `provider_timeout` status and records timeout metadata

#### Scenario: Timeout values are validated
- **WHEN** configured timeout values are missing, non-numeric, or non-positive
- **THEN** the gateway uses safe defaults rather than unbounded waits

### Requirement: Standard AI request metadata
The system SHALL return standardized AI request metadata for every gateway response, including provider, model, gateway mode, status, read-only state, latency, token estimate, cost estimate, local/paid flags, fallback attempt, fallback reason, and error code when applicable.

#### Scenario: Local response shows no API cost
- **WHEN** a local provider handles a request
- **THEN** response metadata marks `local_request=true`, `paid_request=false`, and `estimated_cost_usd=0`

#### Scenario: Failed response still has metadata
- **WHEN** no provider successfully handles a request
- **THEN** the gateway still returns metadata describing the mode, attempted provider path, failure status, and error code

### Requirement: Authenticated AI status endpoint
The system SHALL expose a thin authenticated AI status/readiness endpoint using existing Flask blueprint and RBAC conventions.

#### Scenario: Analyst or super administrator can read AI status
- **WHEN** an authenticated analyst or super administrator requests AI status
- **THEN** the endpoint returns sanitized gateway configuration and provider readiness

#### Scenario: Unauthenticated request is rejected
- **WHEN** a request without a valid session requests AI status
- **THEN** the endpoint is rejected by existing authentication behavior

#### Scenario: Insufficient role is rejected
- **WHEN** an authenticated role outside the analyst/super-admin event-read boundary requests AI status
- **THEN** the endpoint rejects the request through existing RBAC behavior

### Requirement: Phase 1A excludes analyst request surfaces
The system SHALL NOT add analyst-facing AI explanation, chat, contextual-button, prompt-template, context-builder, drafting, approval-gated action, or autonomous-agent behavior as part of Phase 1A.

#### Scenario: No contextual AI explanation route
- **WHEN** Phase 1A is implemented
- **THEN** there is no endpoint that explains alerts, incidents, source IPs, dashboard graphs, recon activity, or response registry records

#### Scenario: No production action route
- **WHEN** Phase 1A is implemented
- **THEN** there is no AI route that blocks IPs, approves SOAR, modifies incidents, changes alerts, changes configuration, creates drafts, or executes actions
