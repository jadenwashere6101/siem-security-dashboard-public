## ADDED Requirements

### Requirement: SOC assistant read tools are explicit and read-only
The system SHALL provide a fixed set of API-backed SOC investigation read tools and SHALL NOT allow AI providers, prompts, or clients to invoke raw database access, shell commands, file access, production writes, VM access, deployment, migrations, commits, pushes, or unsupported tools.

#### Scenario: Supported tool set is fixed
- **WHEN** a tool-assisted SOC AI request is processed
- **THEN** only `search_alerts`, `get_alert_detail`, `get_related_events`, `get_source_ip_context`, `search_incidents`, `get_incident_timeline`, `list_playbook_executions`, `read_audit_log`, and `get_response_registry_context` are eligible for execution

#### Scenario: Unsupported tool is rejected
- **WHEN** a tool plan or client request names a tool outside the fixed allowlist
- **THEN** the executor rejects that tool before any backend helper is called and records a safe unsupported-tool status

#### Scenario: Mutation-like tool is rejected
- **WHEN** a tool plan asks to update status, add notes, execute a playbook, approve SOAR, block an IP, execute a registry command, change configuration, run a migration, or perform a shell/file operation
- **THEN** the system rejects the request as outside the read-only SOC tool contract

### Requirement: Canonical read-tool contract is centralized
The system SHALL define tool names, descriptions, input schemas, output source metadata, minimum roles, result limits, timeout/limit policy, and canonical source helpers in one backend location under `core/ai`.

#### Scenario: Tool definitions are discoverable by executor and tests
- **WHEN** the executor validates a tool request
- **THEN** it reads the canonical definition for that tool rather than relying on route-local hardcoded behavior

#### Scenario: Tool argument validation fails safely
- **WHEN** required arguments are missing, malformed, out of range, or exceed configured limits
- **THEN** the executor returns a validation failure without calling the canonical read helper

#### Scenario: Tool results share a common shape
- **WHEN** any supported tool returns data
- **THEN** the result includes status, data, source attribution, truncation state, omitted count when known, latency, error code when applicable, and `read_only=true`

### Requirement: Tool executor reuses canonical SIEM read paths
The system SHALL execute SOC read tools through existing SIEM read APIs, services, or narrowly extracted read-only helpers and SHALL NOT duplicate source-of-truth query logic where a reusable helper exists.

#### Scenario: Alert search uses alert list semantics
- **WHEN** `search_alerts` is executed with filters
- **THEN** it applies the same validation, filtering, sorting, and bounded list behavior used by the canonical `/alerts` read path

#### Scenario: Alert detail uses alert detail semantics
- **WHEN** `get_alert_detail` is executed with an alert id
- **THEN** it returns the canonical alert detail payload with available response outcome and investigation intelligence

#### Scenario: Related events use existing event filters
- **WHEN** `get_related_events` is executed for an alert, recon activity, source IP, or event filter
- **THEN** it uses existing related-event or `/events/search` filtering semantics with bounded results

#### Scenario: Source IP context uses existing aggregation
- **WHEN** `get_source_ip_context` is executed with a source IP
- **THEN** it uses the canonical source-IP aggregation for alerts, incidents, queue, blocklist, reputation, playbook executions, returning-attacker evidence, campaign data, internet-noise assessment, and response outcomes

#### Scenario: Incident search uses incident list semantics
- **WHEN** `search_incidents` is executed with status, severity, operational scope, or pagination filters
- **THEN** it uses the canonical incident list helper behavior and bounded result limits

#### Scenario: Incident timeline uses read-only timeline helper
- **WHEN** `get_incident_timeline` is executed with an incident id
- **THEN** it uses canonical incident detail plus `build_readonly_incident_timeline()` and read-only response outcome timeline entries

#### Scenario: Playbook execution list uses execution read helpers
- **WHEN** `list_playbook_executions` is executed
- **THEN** it uses canonical playbook execution list/detail serialization and response-outcome enrichment without creating, retrying, abandoning, resuming, or modifying executions

#### Scenario: Audit log uses existing super-admin read path
- **WHEN** `read_audit_log` is executed
- **THEN** it follows the existing `/admin/audit-log` read semantics and returns only bounded audit metadata

#### Scenario: Response registry context excludes commands
- **WHEN** `get_response_registry_context` is executed
- **THEN** it uses canonical response registry list/detail helpers and never calls `/response-registry/commands` or response command execution helpers

### Requirement: Tool execution is bounded and non-autonomous
The system SHALL run read tools only for explicit authenticated AI requests and SHALL bound each request by maximum tool calls, per-tool result limits, time windows, serialized evidence size, and one non-recursive execution pass.

#### Scenario: No background tool execution
- **WHEN** the backend application starts or AI configuration is loaded
- **THEN** no SOC read tool is executed until an authenticated analyst or super administrator explicitly submits an AI chat or explanation request

#### Scenario: Maximum tool calls are enforced
- **WHEN** a model-generated or deterministic tool plan requests more than the configured maximum number of tool calls
- **THEN** the executor executes only the allowed bounded set or fails safely with truncation metadata

#### Scenario: Broad searches receive safe defaults
- **WHEN** a search tool is requested without a narrower visible context or time window
- **THEN** the executor applies a safe default time window and result limit instead of scanning unbounded history

#### Scenario: Recursive tool loops are disallowed
- **WHEN** tool results have been gathered for a request
- **THEN** the system performs at most one final answer generation pass and does not allow additional recursive tool planning loops

### Requirement: Tool-assisted AI uses existing Phase 1 gateway and Phase 1B response flow
The system SHALL extend existing `POST /ai/chat` and `POST /ai/explain` service behavior for tool-assisted investigations while preserving Phase 1A gateway routing/metadata and Phase 1B grounded response semantics.

#### Scenario: Analyst asks a tool-assisted SIEM question
- **WHEN** an authenticated analyst submits a valid SIEM chat or explanation request with tool assistance enabled
- **THEN** the backend validates and executes allowed read tools, builds a grounded prompt from current context plus tool evidence, calls the Phase 1A gateway, and returns the existing AI response shape extended with tool metadata

#### Scenario: Gateway disabled remains safe
- **WHEN** the AI gateway is disabled or unavailable
- **THEN** the system returns the gateway status and metadata without executing unnecessary tool calls or presenting an unexpected server error

#### Scenario: Final answer uses only supplied evidence
- **WHEN** the final AI answer is generated
- **THEN** the prompt instructs the model to use only supplied SIEM context and tool results and to state uncertainty rather than invent missing facts

### Requirement: Tool evidence is source-attributed
The system SHALL attach source metadata to every tool result and SHALL return tool evidence summaries to the frontend without exposing secrets or unbounded raw records.

#### Scenario: Tool sources are returned
- **WHEN** a tool-assisted AI response is returned
- **THEN** the response includes tool source metadata identifying tool name, source path or helper, relevant record ids, generated timestamp where available, status, truncation, and omitted count

#### Scenario: Tool evidence is truncated safely
- **WHEN** tool evidence exceeds the configured serialized evidence or prompt-size limit
- **THEN** lower-priority evidence is truncated before prompt construction and the response records truncation metadata

#### Scenario: Credentials are redacted
- **WHEN** tool results or visible context contain credential-like keys or values
- **THEN** those values are redacted before logging, prompt construction, and API response serialization

### Requirement: Tool access follows existing authentication and RBAC boundaries
The system SHALL protect tool-assisted SOC AI requests with existing authentication and analyst/super-admin authorization and SHALL enforce stricter role requirements for tools whose canonical source requires them.

#### Scenario: Analyst can use analyst-readable tools
- **WHEN** an authenticated analyst requests allowed alert, event, source-IP, incident, playbook-execution, or response-registry read tools
- **THEN** the backend allows the read-only request according to existing analyst/super-admin boundaries

#### Scenario: Analyst cannot read audit log through tools
- **WHEN** an authenticated analyst request includes `read_audit_log`
- **THEN** the executor rejects that tool because the canonical audit-log source is super-admin only

#### Scenario: Super administrator can read audit log through tools
- **WHEN** an authenticated super administrator request includes `read_audit_log`
- **THEN** the executor may execute the bounded audit-log read tool using the canonical audit-log semantics

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated user submits a tool-assisted AI request
- **THEN** existing authentication behavior rejects the request before tool execution

### Requirement: Tool planning fails closed
The system SHALL validate any model-generated tool plan before execution and SHALL fail safely when the plan is malformed, unsafe, excessive, or unsupported.

#### Scenario: Invalid JSON plan fails safely
- **WHEN** the AI gateway returns an invalid tool plan
- **THEN** the service returns a safe tool-planning failure or falls back to deterministic allowed routing without executing unsafe model text

#### Scenario: Plan with unsafe arguments fails safely
- **WHEN** a tool plan includes invalid IP addresses, non-positive ids, unsupported statuses, excessive limits, credential-bearing strings, or impossible time windows
- **THEN** the executor rejects or clamps the arguments according to the canonical tool schema before any read helper is called

#### Scenario: Deterministic routing is allowed
- **WHEN** the implementation uses deterministic keyword routing instead of model-generated planning for the first Phase 3 release
- **THEN** it still executes tools only through the same canonical contract and returns the same tool metadata

### Requirement: Tool logs and audit metadata are secret-safe
The system SHALL log only safe metadata for tool-assisted AI requests and SHALL NOT log prompt text, chat history, full tool results, credentials, credential-bearing URLs, or sensitive evidence bodies.

#### Scenario: Tool request failure is logged safely
- **WHEN** a tool-assisted request fails
- **THEN** logs include only safe fields such as route, actor identifier, tool names, statuses, counts, latency, and error code

#### Scenario: Prompt and evidence are not logged
- **WHEN** a tool-assisted request succeeds or fails
- **THEN** prompt text, raw chat history, and raw tool evidence are not written to application logs

### Requirement: Frontend displays read-tool evidence without changing analyst workflow
The frontend SHALL reuse the existing SIEM AI chat/explanation surfaces and shared response presentation to show tool usage, tool status, evidence source counts, truncation, read-only state, retry, cancellation, and safe failure states.

#### Scenario: Tool-assisted answer shows tools used
- **WHEN** a tool-assisted AI response is displayed
- **THEN** the shared AI response UI shows that read-only investigation tools were used and lists tool names, statuses, source counts, truncation state, provider/model metadata, latency, and cost metadata

#### Scenario: Tool failure is analyst-readable
- **WHEN** a tool is unavailable, forbidden, invalid, truncated, or returns no evidence
- **THEN** the UI displays a non-destructive explanation and does not imply that a response action was taken

#### Scenario: Existing cancellation and stale-response behavior is preserved
- **WHEN** the analyst cancels, retries, or navigates away during a tool-assisted request
- **THEN** existing AbortController and stale-response protections prevent old results from overwriting newer UI state

#### Scenario: Repo assistant remains separate
- **WHEN** an analyst uses the floating SIEM chat or contextual AI buttons
- **THEN** those surfaces do not retrieve repository files and do not call Phase 2 repo-assistant endpoints
