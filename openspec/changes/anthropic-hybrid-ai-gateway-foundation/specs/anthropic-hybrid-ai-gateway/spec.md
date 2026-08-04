## ADDED Requirements

### Requirement: Anthropic implements the existing provider contract
The system SHALL register Anthropic as a first-class provider through the existing `AiProvider` abstraction and provider factory. Anthropic-specific request translation, capability checks, readiness, response normalization, usage extraction, timeout handling, and error classification MUST remain inside the provider layer, and the common provider interface MUST remain unchanged unless an implementation-blocking gap is first documented in this change. Existing Ollama behavior MUST remain unchanged.

#### Scenario: Anthropic generation uses the gateway
- **WHEN** a trusted backend profile resolves to Anthropic and gateway policy authorizes the request
- **THEN** the gateway SHALL invoke the registered Anthropic provider through the normal provider contract
- **AND** normalized response metadata SHALL identify the selected provider, model, profile, status, and latency

#### Scenario: Ollama workflows are unchanged
- **WHEN** an Ollama-assigned profile executes before or after Anthropic is configured
- **THEN** its provider capability checks, request behavior, timeout, response normalization, and no-cost metadata SHALL remain governed by the existing Ollama path

#### Scenario: Unknown capability remains closed
- **WHEN** either provider receives a capability it has not registered
- **THEN** generation SHALL not run and the gateway SHALL return the existing provider-incapable outcome

### Requirement: Anthropic credentials are environment-only
The system MUST load the Anthropic API key from the protected process environment and MUST NOT accept or persist it through PostgreSQL, runtime administration payloads, frontend state, source-controlled configuration, API responses, logs, audit records, or status output.

#### Scenario: Credential is present
- **WHEN** Anthropic-enabled startup validation reads a valid protected API key from the environment
- **THEN** the provider SHALL receive the credential without copying its value into persistent runtime configuration or observable metadata

#### Scenario: Credential is submitted to runtime administration
- **WHEN** a client includes an API key or credential-like field in a gateway configuration mutation
- **THEN** backend validation SHALL reject the field
- **AND** audit output SHALL not retain its value

#### Scenario: Secret redaction is exercised
- **WHEN** an Anthropic request or readiness check fails with a provider error that includes credentials, authorization data, or a sensitive endpoint
- **THEN** API, log, status, and audit serialization SHALL expose only a normalized redacted error category

### Requirement: Anthropic startup and readiness fail closed
The system SHALL perform provider-specific startup validation when effective runtime policy enables an Anthropic-assigned profile. Required credentials, model/capability registration, bounded timeouts, pricing policy, and budget policy MUST be valid before paid execution is available. Invalid or unreadable required configuration SHALL prevent Anthropic requests while preserving valid Ollama-only operation when the effective mode permits it.

#### Scenario: Required key is missing
- **WHEN** effective startup configuration enables Anthropic routing and the required environment credential is absent
- **THEN** startup validation SHALL report a configuration error and Anthropic execution SHALL remain disabled

#### Scenario: Ollama-only startup has no Anthropic dependency
- **WHEN** effective mode and profiles permit only local execution
- **THEN** missing Anthropic configuration SHALL not prevent valid Ollama-only startup or requests

#### Scenario: Readiness is provider-specific and non-generating
- **WHEN** the system evaluates Anthropic readiness
- **THEN** Phase 1 SHALL validate enabled state, credential presence, model/capability configuration, bounded timeout, and API version without network traffic or a billable generation request
- **AND** readiness SHALL identify its scope as `configuration_only`
- **AND** it SHALL distinguish disabled, configured, unavailable, timeout, incapable, authentication-error, budget-blocked, and ready states where applicable

#### Scenario: Provider foundation cannot route paid traffic
- **WHEN** Anthropic is registered and its environment configuration is complete during Phase 1
- **THEN** no active profile SHALL select Anthropic and the gateway SHALL keep Anthropic routing disabled
- **AND** provider generation SHALL be reachable only through mocked direct provider tests, not normal application routing

### Requirement: Gateway enforces a daily paid API budget
The gateway SHALL be the sole authority for paid-request authorization. Before every Anthropic generation, including planner repair, it MUST atomically compare a conservative maximum request cost with the shared PostgreSQL-backed daily spending cap and reserve sufficient budget. It MUST NOT call Anthropic when configuration or accounting cannot be read safely, when pricing cannot be calculated, or when the request could exceed the remaining cap.

#### Scenario: Paid request fits the remaining budget
- **WHEN** validated policy authorizes Anthropic and the conservative request cost fits within the remaining daily cap
- **THEN** the gateway SHALL atomically reserve the amount before invoking the provider
- **AND** concurrent processes SHALL observe the reservation

#### Scenario: Request would exceed the cap
- **WHEN** the conservative cost of an Anthropic request is greater than the remaining daily budget
- **THEN** the gateway SHALL return a typed budget-exhausted outcome without contacting Anthropic
- **AND** it SHALL never silently exceed the configured cap

#### Scenario: Accounting is unavailable
- **WHEN** paid accounting, runtime policy, or pricing configuration cannot be read or validated
- **THEN** all paid execution SHALL fail closed
- **AND** an Ollama-only request SHALL continue only when its independent local policy remains valid and cannot authorize paid fallback

#### Scenario: Concurrent requests approach the cap
- **WHEN** multiple web or worker requests attempt to consume the final available budget concurrently
- **THEN** transactional authorization SHALL permit only requests whose combined reservations remain within the cap

### Requirement: Daily budget resets lazily at UTC midnight
The accounting boundary SHALL use UTC calendar days and SHALL atomically initialize or advance the active daily accounting period on the first budget-controlled request after the UTC date changes. Reset MUST NOT depend on a scheduler, service restart, process-local clock state, or client action.

#### Scenario: First request after UTC date change
- **WHEN** the first paid-eligible request arrives after UTC midnight
- **THEN** the gateway SHALL establish the new UTC accounting day before evaluating the request against the full configured daily cap

#### Scenario: No request occurs at midnight
- **WHEN** no budget-controlled request is made at UTC midnight
- **THEN** no background reset job SHALL be required
- **AND** the next request SHALL perform the lazy rollover exactly once under concurrency

### Requirement: Provider usage and cost are durably accounted
Each paid attempt SHALL be independently recorded with provider, model, profile, request status, timing, provider latency, input/output/total token counts or labeled estimates, cost or labeled estimate, UTC accounting day, and correlation sufficient to distinguish an initial request from repair. A pre-call reservation SHALL be reconciled with provider-reported usage when available; if reliable usage is unavailable, the conservative reserved cost MUST remain charged.

#### Scenario: Provider reports token usage
- **WHEN** Anthropic returns normalized input and output token counts
- **THEN** accounting SHALL record the counts, calculate cost from the validated provider/model pricing policy, and reconcile the reservation without allowing the daily total to exceed the cap

#### Scenario: Usage is unavailable
- **WHEN** a paid attempt times out, fails, or returns no reliable token usage
- **THEN** the attempt and latency SHALL still be recorded
- **AND** the conservative reservation SHALL remain charged and identified as estimated

#### Scenario: Repair is independently accounted
- **WHEN** an invalid Anthropic planner proposal receives its one allowed repair
- **THEN** the repair SHALL create a separately authorized and logged paid attempt linked to the initial attempt

### Requirement: Gateway runtime policy is durable and restricted
Non-secret gateway runtime policy SHALL be PostgreSQL-backed and SHALL follow the established detection and pfSense runtime configuration patterns: source-controlled safe defaults, strict validation, super-admin-only mutation, immediate effect without service restart, `updated_by`, `updated_at`, and existing audit logging. Credentials MUST remain excluded.

#### Scenario: Super administrator changes policy
- **WHEN** a super administrator submits a valid gateway mode, profile routing, daily cap, or non-secret provider/model/pricing policy change
- **THEN** the backend SHALL persist the validated change with `updated_by` and `updated_at`
- **AND** subsequent gateway authorizations SHALL use it without service restart

#### Scenario: Non-super-admin attempts mutation
- **WHEN** an analyst or other unauthorized role attempts to change gateway runtime policy
- **THEN** existing RBAC SHALL reject the mutation and no effective configuration SHALL change

#### Scenario: Invalid policy is submitted
- **WHEN** a runtime mutation contains an unknown mode, unregistered provider/model/profile, negative or invalid cap, inconsistent pricing, credential field, or unsafe fallback combination
- **THEN** validation SHALL reject the complete mutation and preserve the last valid policy

#### Scenario: Runtime policy is unreadable
- **WHEN** the durable runtime policy cannot be read safely
- **THEN** the gateway SHALL immediately set its effective mode to `local_only`, disable paid routing, and report a configuration error through status
- **AND** it SHALL set its effective mode to `disabled` instead if validated source-controlled local defaults are unavailable or invalid

### Requirement: Gateway configuration mutations are audited
Every successful and rejected gateway runtime configuration mutation SHALL use the existing configuration audit pattern with actor identity, action, outcome, timestamp, and sanitized old/new or validation details. Audit data MUST NOT contain credentials, authorization headers, raw prompts, sensitive provider responses, or sensitive endpoints.

#### Scenario: Valid change is audited
- **WHEN** a super administrator changes gateway policy
- **THEN** one audit event SHALL identify the actor, successful outcome, and sanitized prior and resulting non-secret values

#### Scenario: Rejected change is audited
- **WHEN** a gateway policy mutation is denied by RBAC or validation
- **THEN** the rejection SHALL be auditable without persisting submitted secret values

### Requirement: AI status exposes sanitized hybrid state
The existing authenticated `/ai/status` endpoint SHALL report the effective gateway mode, provider readiness, active provider and model for every profile, current UTC budget period, daily cap, budget used, budget remaining, and token/cost usage with explicit provenance. Each token or cost value SHALL be labeled `provider_reported` only when the provider returned that exact value; calculated, reserved, or inferred values SHALL be labeled `estimated` and MUST NOT be represented as actual billed usage. The endpoint MUST NOT expose API keys, secrets, authorization material, raw prompts or completions, or sensitive endpoints.

#### Scenario: Authorized status request
- **WHEN** an authenticated authorized user requests `/ai/status`
- **THEN** the response SHALL include sanitized Ollama and Anthropic readiness, the complete profile routing table, effective mode, and current budget/accounting summary with usage provenance

#### Scenario: Provider-reported and estimated usage remain distinct
- **WHEN** status combines provider-reported token usage with derived cost or conservative reservation data
- **THEN** it SHALL label only the exact provider-returned values as `provider_reported`
- **AND** it SHALL label derived cost and reservation values as `estimated` rather than actual billed usage

#### Scenario: Budget is exhausted
- **WHEN** paid usage has exhausted or reserved the daily cap
- **THEN** status SHALL report no remaining paid budget and a budget-blocked Anthropic state without exposing sensitive configuration

#### Scenario: Status is read-only
- **WHEN** `/ai/status` is requested
- **THEN** it SHALL not mutate runtime policy, reset the daily budget, or issue a billable provider generation

### Requirement: Hybrid acceptance covers real execution boundaries
Acceptance SHALL verify provider routing, Ollama-only workflows, Anthropic workflows, hybrid mode behavior, daily budget enforcement and UTC rollover, fail-closed configuration/accounting, readiness reporting, audit logging, token/cost/latency accounting, secret redaction, Gunicorn and worker compatibility, and the browser-path production Anakin workflow. Production deployment or acceptance MUST occur only after separate authorization under the repository source-of-truth policy.

#### Scenario: Forced budget exhaustion
- **WHEN** a controlled test configures remaining budget below the conservative cost of the next Anthropic planner request
- **THEN** no Anthropic call SHALL occur, the planner SHALL degrade gracefully without switching to Ollama, accounting SHALL remain at or below the cap, and status and audit evidence SHALL show the budget outcome

#### Scenario: Ollama continues after paid budget exhaustion
- **WHEN** the daily paid budget is exhausted and gateway mode still permits local execution
- **THEN** Ollama-only profiles SHALL continue without paid fallback or paid accounting

#### Scenario: Web and worker compatibility
- **WHEN** Anthropic-eligible work is invoked through Flask/Gunicorn and supported asynchronous workers
- **THEN** both paths SHALL use the same gateway routing, runtime policy, transactional budget, accounting, redaction, and audit boundaries

#### Scenario: Browser-path production acceptance
- **WHEN** separately authorized production acceptance exercises Anakin from the deployed browser through the backend and worker path
- **THEN** observable provider/profile metadata, graceful failures, and analyst-visible results SHALL match the validated hybrid policy without bypassing the gateway
