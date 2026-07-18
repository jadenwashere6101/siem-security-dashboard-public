## ADDED Requirements

### Requirement: Read-only AI explanation endpoints
The system SHALL expose read-only authenticated AI explanation and SIEM chat endpoints that reuse the Phase 1A AI gateway for inference and SHALL NOT mutate alerts, incidents, response registry records, SOAR state, configuration, detections, database state, files, or external systems.

#### Scenario: Authenticated analyst requests contextual explanation
- **WHEN** an authenticated analyst or super administrator submits a valid contextual explanation request
- **THEN** the backend builds read-only SIEM context, calls the Phase 1A AI gateway, and returns an explanation response with gateway metadata

#### Scenario: Unauthenticated explanation is rejected
- **WHEN** a request without a valid session submits an AI explanation or chat request
- **THEN** existing authentication behavior rejects the request

#### Scenario: Insufficient role is rejected
- **WHEN** an authenticated role outside the analyst/super-admin boundary submits an AI explanation or chat request
- **THEN** existing RBAC behavior rejects the request

#### Scenario: AI endpoint performs no production mutation
- **WHEN** any Phase 1B AI route handles a request
- **THEN** it does not call alert status, alert note, manual execution, registry command, approval, playbook execution, blocklist, ingest, migration, shell, or production-write paths

### Requirement: Centralized source-grounded context builder
The system SHALL build AI context through a centralized backend context builder that uses canonical SIEM read paths, applies consistent limits, records source attribution, and reports insufficient or truncated context.

#### Scenario: Alert context is built from canonical alert paths
- **WHEN** an alert explanation request includes an alert id
- **THEN** the context builder uses the canonical alert detail data, alert intelligence, available why-fired evidence, and bounded related events as the grounded context

#### Scenario: Incident context is built from canonical incident paths
- **WHEN** an incident explanation request includes an incident id
- **THEN** the context builder uses canonical incident detail and read-only incident timeline data as the grounded context

#### Scenario: Source IP context is built from canonical source-IP aggregation
- **WHEN** a source-IP explanation request includes a source IP
- **THEN** the context builder uses the existing source-IP context aggregation for alerts, incidents, reputation, queue, blocklist, campaigns, returning-attacker evidence, playbook executions, and response outcomes

#### Scenario: Recon activity context is built from canonical recon paths
- **WHEN** a recon activity explanation request includes a recon activity id
- **THEN** the context builder uses canonical recon activity detail plus bounded related events as the grounded context

#### Scenario: Dashboard context is built from visible dashboard state
- **WHEN** a dashboard explanation request is submitted
- **THEN** the context builder uses the current visible dashboard filters, summary metrics, timeline, top IPs, map markers, and bounded recent alert rows supplied or fetched through existing dashboard data paths

#### Scenario: Response registry context excludes command execution
- **WHEN** a response registry explanation request includes a registry id
- **THEN** the context builder uses canonical registry detail and does not call the response registry command execution path

#### Scenario: Detection context uses existing detection explanations
- **WHEN** a detection explanation request includes an alert id or rule id
- **THEN** the context builder uses existing why-fired, alert detection metadata, and severity/response matrix data where available

### Requirement: Bounded context and source attribution
The system SHALL enforce bounded AI context size, per-section limits, prompt-size limits, source attribution, and truncation metadata before sending any prompt to the AI gateway.

#### Scenario: Context sections are limited
- **WHEN** a context source contains more rows than the configured Phase 1B section limit
- **THEN** the context builder includes only the bounded subset and records truncation metadata with omitted count where known

#### Scenario: Prompt size is guarded
- **WHEN** the normalized context plus user question would exceed the configured AI prompt limit
- **THEN** the service truncates lower-priority context before invoking the gateway or returns insufficient-context if a safe prompt cannot be built

#### Scenario: Context source attribution is returned
- **WHEN** an AI response is returned
- **THEN** the response includes source metadata identifying the context type, source path or helper, record ids where applicable, generated timestamp when available, and truncation state

### Requirement: Grounded insufficient-context behavior
The system SHALL return clear insufficient-context responses when available SIEM data is missing, too thin, inaccessible, or not enough to answer safely, and SHALL NOT ask the model to invent missing facts.

#### Scenario: Required context identifier is missing
- **WHEN** an explanation request omits the identifier required for its context type
- **THEN** the backend rejects the request with a safe validation error

#### Scenario: Requested record is not found
- **WHEN** an explanation request references an alert, incident, recon activity, or registry record that does not exist
- **THEN** the backend returns a not-found response rather than generating an explanation

#### Scenario: Context is too thin to answer
- **WHEN** canonical sources return no meaningful context for a valid request
- **THEN** the API returns `insufficient_context=true` with a safe message and source metadata instead of fabricating an answer

### Requirement: AI response contract includes gateway metadata
The system SHALL return AI responses with answer text, status, insufficient-context flag, source/truncation metadata, error information, and the Phase 1A gateway metadata for provider, model, mode, latency, estimated tokens, estimated cost, local/paid flags, fallback state, and error code.

#### Scenario: Local response displays zero API cost
- **WHEN** the AI gateway returns a local-provider response
- **THEN** the API response preserves metadata showing `local_request=true`, `paid_request=false`, and `estimated_cost_usd=0`

#### Scenario: Disabled gateway is a normal AI state
- **WHEN** AI is disabled by configuration
- **THEN** the API returns a structured AI response with disabled status and metadata rather than an unexpected server error

#### Scenario: Provider failure state is preserved
- **WHEN** the gateway returns unavailable, timeout, fallback-blocked, fallback-confirmation-required, configuration-error, or failed status
- **THEN** the API preserves that status and metadata so the frontend can render the correct analyst-facing state

### Requirement: General SIEM chat uses current visible context
The system SHALL provide a floating general SIEM chat that answers natural analyst questions using the current visible SIEM context supplied by the frontend plus bounded backend enrichment for referenced ids or source IPs.

#### Scenario: Chat question is grounded in current dashboard context
- **WHEN** an analyst asks a general question while viewing the dashboard
- **THEN** the chat request includes active dashboard filters, visible summary data, and selected alert/source context when available

#### Scenario: Chat history is client-session only
- **WHEN** the analyst exchanges messages with the floating chat
- **THEN** history is stored only in frontend component state and is not persisted to the backend, database, local storage, or model memory

#### Scenario: Chat history is bounded
- **WHEN** the frontend sends prior chat messages with a new question
- **THEN** the backend truncates the client-provided history before prompt construction and treats it as untrusted user input

### Requirement: Contextual AI entry points
The frontend SHALL expose contextual AI entry points in the existing analyst surfaces without broad UI redesign and SHALL use the shared AI request/response components for consistent behavior.

#### Scenario: Dashboard AI entry point is visible
- **WHEN** an analyst views dashboard metrics, timeline, top IPs, map, or summary cards
- **THEN** the UI offers contextual AI actions such as asking about the graph or explaining an anomaly using current dashboard state

#### Scenario: Alert detail AI entry point is visible
- **WHEN** an analyst opens an alert detail panel
- **THEN** the UI offers actions to explain the alert, explain importance, and recommend investigation steps

#### Scenario: Incident AI entry point is visible
- **WHEN** an analyst opens an incident detail pane
- **THEN** the UI offers actions to summarize the incident and recommend next steps

#### Scenario: Source IP AI entry point is visible
- **WHEN** source-IP context is shown
- **THEN** the UI offers actions to explain the IP, assess reconnaissance, and summarize activity

#### Scenario: Recon activity AI entry point is visible
- **WHEN** recon activity context is shown
- **THEN** the UI offers actions to explain the campaign and investigate the cluster

#### Scenario: Response registry AI entry point is visible
- **WHEN** a response registry record detail is shown
- **THEN** the UI offers an action to explain the response

#### Scenario: Unauthorized users cannot use AI entry points
- **WHEN** a viewer or unauthenticated user reaches a surface that would otherwise support AI
- **THEN** AI entry points are hidden or disabled consistently with backend authorization

### Requirement: Shared AI response user experience
The frontend SHALL provide shared AI response presentation for contextual explanations and floating chat, including loading, retry, cancel, dismiss, stale-response handling, source display, metadata display, and failure-state copy.

#### Scenario: AI request can be cancelled
- **WHEN** an analyst cancels an in-flight AI request or navigates away from the relevant context
- **THEN** the frontend aborts the request and prevents the response from overwriting newer UI state

#### Scenario: Stale response is not applied as current
- **WHEN** an AI response returns after the selected alert, incident, source IP, recon activity, registry record, or dashboard context has changed
- **THEN** the UI marks the response as stale or discards it without replacing the current response

#### Scenario: Retry uses original context snapshot
- **WHEN** an analyst retries a failed AI request
- **THEN** the retry uses the same bounded context snapshot unless the analyst explicitly asks about the new current context

#### Scenario: Metadata is visible
- **WHEN** an AI response is displayed
- **THEN** the UI shows provider, model, local/paid state, estimated cost where applicable, latency, and fallback state from response metadata

#### Scenario: Failure states are analyst-readable
- **WHEN** the API returns disabled, unavailable, timeout, fallback-blocked, confirmation-required, configuration-error, failed, or insufficient-context status
- **THEN** the UI shows a clear non-destructive explanation and an appropriate retry or configuration hint

### Requirement: Phase 1B excludes tools, drafts, actions, and autonomy
The system SHALL NOT introduce repo assistance, AI tool calling, draft generation, approval-gated actions, autonomous background analysis, direct provider database access, shell access, production-write behavior, schema migrations, or broad UI redesign as part of Phase 1B.

#### Scenario: No AI tool execution
- **WHEN** an AI explanation or chat request is processed
- **THEN** the model receives bounded context only and cannot request backend tool execution

#### Scenario: No AI drafting or action endpoint exists
- **WHEN** Phase 1B is implemented
- **THEN** there is no AI endpoint or UI control that creates drafts, blocks IPs, approves SOAR, modifies incidents, changes alerts, changes configuration, or executes response actions
