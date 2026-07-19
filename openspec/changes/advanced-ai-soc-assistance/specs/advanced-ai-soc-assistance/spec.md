## ADDED Requirements

### Requirement: Advanced SOC assistance is explicit and bounded
The system SHALL run advanced AI SOC assistance only after an explicit authenticated analyst or super-administrator request and SHALL bound each investigation by allowed workflow steps, maximum depth, tool-call limits, timeout budgets, retry limits, cancellation behavior, and prompt-size limits.

#### Scenario: No autonomous investigation starts
- **WHEN** the backend application starts, AI readiness is checked, alerts are ingested, detections fire, or dashboards refresh
- **THEN** no advanced AI investigation, tool chain, draft, provider request, production action, or background analysis is started without an explicit analyst or super-administrator AI request

#### Scenario: Workflow step set is fixed
- **WHEN** an advanced investigation is planned
- **THEN** only `build_context`, `plan_read_tools`, `execute_read_tool`, `validate_evidence`, `correlate_evidence`, `suggest_response_plan`, `generate_transient_draft`, and `finalize_summary` are valid step types

#### Scenario: Unsupported workflow step is rejected
- **WHEN** a planner output, client request, or provider response names any other step type
- **THEN** the investigation rejects that step before execution and records a safe validation failure

#### Scenario: Depth and loop limits are enforced
- **WHEN** a workflow would exceed the configured maximum step depth, tool-call count, planning pass count, final-answer generation count, or automatic-draft count
- **THEN** the system stops or truncates the workflow with partial-result metadata and does not recursively plan additional tool loops

#### Scenario: Timeout stops the investigation safely
- **WHEN** the total investigation budget or a per-step budget is exhausted
- **THEN** the system stops remaining steps, returns timeout or partial status, preserves completed read-only evidence, and does not continue into drafts or production actions unless those steps already completed safely

#### Scenario: Cancellation prevents stale completion
- **WHEN** an analyst cancels an in-flight advanced investigation or navigates away from the target context
- **THEN** the frontend aborts the request and stale or cancelled results do not overwrite newer visible AI state

### Requirement: Planner is separate from provider adapters
The system SHALL keep investigation planning and tool chaining in backend planner/service modules and SHALL NOT place planner ownership, tool handles, service objects, database handles, shell/file handles, mutation callbacks, or approval callbacks inside AI provider adapters.

#### Scenario: Provider receives prompt-only requests
- **WHEN** an investigation calls an AI provider
- **THEN** the provider receives only a bounded generation request and metadata, not executable tool definitions, database handles, cursors, shell/file handles, production services, or mutation callbacks

#### Scenario: Planner validates model-assisted plans
- **WHEN** model-assisted planning is used
- **THEN** the planner parses the plan as structured data and validates every step and tool request against backend allowlists before execution

#### Scenario: Invalid provider plan fails closed
- **WHEN** a provider returns malformed planning output, unsupported steps, unsafe tools, excessive depth, or mutation-like operations
- **THEN** the planner rejects the unsafe plan or falls back to a deterministic allowed workflow without executing unsafe content

### Requirement: Tool chaining uses only existing read-only SOC tools
The system SHALL chain only existing fixed SOC read tools through the canonical read-tool executor and SHALL NOT add raw database access, shell access, file access, VM access, write tools, registry commands, SOAR execution controls, approval decisions, migrations, commits, pushes, deployments, or unsupported tools.

#### Scenario: Existing read-tool allowlist is reused
- **WHEN** an investigation needs deeper evidence
- **THEN** it uses only the existing `search_alerts`, `get_alert_detail`, `get_related_events`, `get_source_ip_context`, `search_incidents`, `get_incident_timeline`, `list_playbook_executions`, `read_audit_log`, and `get_response_registry_context` tools through the canonical executor

#### Scenario: Mutation-like tool request is rejected
- **WHEN** a workflow asks to add notes, update status, execute a playbook, approve or deny SOAR, block an IP, execute a registry command, retry a queue item, change configuration, run SQL, execute shell commands, write files, migrate, commit, push, deploy, or access the VM
- **THEN** the system rejects the request before any production helper is called

#### Scenario: Tool ordering is preserved
- **WHEN** a workflow executes multiple read tools
- **THEN** results are recorded in execution order with status, latency, source metadata, truncation, omitted count, and read-only marker

#### Scenario: Tool failures produce partial results
- **WHEN** a non-critical read tool fails, is forbidden, is truncated, or returns no evidence
- **THEN** the investigation may continue with validated remaining evidence and the final result identifies missing or incomplete evidence

### Requirement: Later steps consume only validated evidence
The system SHALL validate context and read-tool outputs before any later correlation, recommendation, or draft step consumes them.

#### Scenario: Evidence source identifiers match the target
- **WHEN** a tool result is used for an alert, incident, source IP, recon activity, response registry, or dashboard workflow
- **THEN** the planner verifies that returned source identifiers match the current context snapshot or excludes the result as unsafe for grounding

#### Scenario: Evidence requires source attribution
- **WHEN** non-empty context or tool evidence is used in a later step
- **THEN** it includes source metadata identifying the context type, source path or helper, relevant record ids where applicable, status, generated timestamp where available, truncation state, and omitted count

#### Scenario: Forbidden evidence is excluded
- **WHEN** a tool result is forbidden for the actor role, including analyst access to audit-log evidence
- **THEN** the result is not provided to later model prompts and the final analyst-facing result records the forbidden evidence state

#### Scenario: Oversized evidence is bounded
- **WHEN** context or tool evidence exceeds configured serialized evidence or prompt-size limits
- **THEN** lower-priority evidence is truncated or compacted before model use and truncation metadata is returned

#### Scenario: Secrets are redacted
- **WHEN** context, tool evidence, prompts, logs, drafts, recommendations, or API responses contain credential-like keys or values
- **THEN** those values are redacted before logging, prompt construction, provider calls, and response serialization

### Requirement: Investigation outputs are grounded and source-cited
The system SHALL generate investigation summaries, evidence correlations, recommendations, and drafts only from supplied SIEM context and validated read-tool evidence and SHALL cite the sources used.

#### Scenario: Final answer cites evidence
- **WHEN** an advanced investigation returns a summary or correlation
- **THEN** it includes source references for material findings and distinguishes direct evidence from inference

#### Scenario: Insufficient evidence is explicit
- **WHEN** required context is missing, inaccessible, too thin, or invalid
- **THEN** the system returns `insufficient_context`, `not_found`, `forbidden`, `partial`, or `failed` state instead of fabricating findings

#### Scenario: Recommendations do not claim action
- **WHEN** the assistant suggests response plans
- **THEN** recommendations are presented as analyst next steps with prerequisites, risks, expected outcomes, and confirmation requirements, and do not claim that remediation, blocking, approval, or SOAR execution happened

#### Scenario: Deterministic detections remain authoritative
- **WHEN** an AI correlation or recommendation differs from existing deterministic detection, correlation, response outcome, approval, or incident state
- **THEN** the UI and API preserve the deterministic SIEM state as authoritative and present the AI output as advisory

### Requirement: Automatic drafts are narrow, transient, and unapplied
The system SHALL generate automatic drafts only for allowed investigation contexts and alert policies, and every automatic draft SHALL remain AI-generated review content that is not persisted, not applied, and not executed.

#### Scenario: Allowed automatic incident-note draft
- **WHEN** an explicit alert or incident investigation has validated high or critical evidence and the alert is linked to an incident
- **THEN** the planner may request one transient `incident_note` draft through the existing drafting service

#### Scenario: Allowed automatic checklist draft
- **WHEN** an explicit high or critical alert, incident, source-IP, or recon-cluster investigation has sufficient validated evidence
- **THEN** the planner may request one transient `investigation_checklist` draft

#### Scenario: Allowed automatic escalation or response draft
- **WHEN** a critical incident or correlated critical alert has sufficient validated evidence
- **THEN** the planner may request one transient `escalation_summary` or `response_recommendation` draft, according to the workflow policy

#### Scenario: Detection and playbook drafts are not automatic
- **WHEN** an investigation would benefit from a detection rule change or playbook design
- **THEN** the assistant may recommend that an analyst request such a draft explicitly, but it does not automatically generate `detection_rule_change` or `playbook_draft`

#### Scenario: Draft labels preserve review-only state
- **WHEN** an automatic draft is returned
- **THEN** it includes `ai_generated=true`, `read_only=true`, `persisted=false`, `applied=false`, and `approval_required_before_apply=true`

#### Scenario: Automatic draft never executes
- **WHEN** an automatic draft is generated successfully
- **THEN** the system does not create or update incidents, notes, detection rules, playbooks, response registry records, approvals, SOAR executions, blocklists, files, commits, deployments, migrations, or database state

### Requirement: Production actions remain explicitly approval-gated
The system SHALL preserve the existing approval-gated AI action boundary and SHALL NOT treat an investigation, recommendation, or draft as authorization to mutate production.

#### Scenario: Existing preview and confirm are required
- **WHEN** an analyst wants to apply content derived from an investigation or draft
- **THEN** the frontend uses the existing AI action preview/confirm flow where available, and the backend revalidates RBAC, target state, exact payload, confirmation token, idempotency key, and audit metadata before mutation

#### Scenario: Cancellation or rejection makes no production change
- **WHEN** an analyst cancels, dismisses, rejects, or does not confirm a recommended action or draft-derived action
- **THEN** no production mutation helper is called and the UI reports that no production change was made

#### Scenario: AI does not control SOAR approval or blocking
- **WHEN** an investigation recommends containment, SOAR review, registry review, or escalation
- **THEN** the assistant does not approve, deny, block, unblock, execute, retry, resume, abandon, or suppress any SOAR, registry, queue, or integration action

### Requirement: Complexity-based routing is observable and fail-closed
The system SHALL classify each advanced investigation by complexity and SHALL use that classification as routing metadata while preserving local-first provider behavior, paid-provider optionality, fallback policy, and safe failure behavior.

#### Scenario: Routing profile records inputs
- **WHEN** an investigation is planned
- **THEN** the system records routing inputs including workflow type, context type, estimated prompt tokens, estimated tool-evidence tokens, planned tool-call count, source count, truncation state, draft need, structured-output need, provider readiness, fallback policy, and remaining timeout budget

#### Scenario: Local provider remains first choice
- **WHEN** local AI is configured, reachable, capable, and within budget for the selected routing profile
- **THEN** the investigation uses the local provider and records zero estimated API cost for that provider response

#### Scenario: Paid fallback follows existing policy
- **WHEN** local AI is unavailable, times out, or is incapable for the selected routing profile
- **THEN** paid fallback is used only when the existing gateway mode and paid fallback configuration allow it; otherwise the investigation returns fallback-required or fallback-blocked metadata

#### Scenario: Routing failure returns evidence safely
- **WHEN** no provider can safely handle the selected routing profile within budget
- **THEN** the system returns available validated read-only evidence and a partial or failed state without fabricating AI conclusions or drafts

### Requirement: Cost, token, latency, and fallback observability is complete
The system SHALL report provider, model, token, cost, latency, retry, timeout, fallback, tool, source, and draft metadata per response and per investigation.

#### Scenario: Per-response metadata is preserved
- **WHEN** any provider response is generated during an investigation
- **THEN** the response records provider, model, gateway mode, status, latency, estimated prompt tokens, estimated completion tokens, estimated cost, local/paid flags, fallback attempted, fallback reason, and error code

#### Scenario: Per-investigation metadata aggregates response metadata
- **WHEN** an investigation finishes, fails, times out, is cancelled, or returns partial results
- **THEN** the result includes aggregate status, total latency, planned and executed step counts, tool statuses, source counts, truncation, omitted count, retry count, timeout state, cancellation state, aggregate estimated tokens, aggregate estimated cost, fallback path, routing profile, automatic draft decision, and draft validation state

#### Scenario: Failed investigations still include metadata
- **WHEN** an investigation cannot complete because AI is disabled, providers fail, fallback is blocked, validation fails, or context is insufficient
- **THEN** the response still includes safe observability metadata for the completed planning/context/tool steps

### Requirement: Analyst experience shows progress, evidence, recommendations, drafts, and incomplete states
The frontend SHALL present advanced investigations in existing AI surfaces or a clearly separated investigation panel with visible progress, source-cited evidence, recommendations, transient drafts, provider metadata, cost/latency metadata, failures, cancellation, stale-context warnings, and incomplete-result states.

#### Scenario: Progress is visible
- **WHEN** an advanced investigation is running or returns staged progress
- **THEN** the UI shows ordered workflow steps with readable statuses such as pending, running, succeeded, skipped, forbidden, failed, timed out, cancelled, partial, and complete

#### Scenario: Evidence and recommendations are distinguishable
- **WHEN** an investigation result is displayed
- **THEN** the UI separates source-cited evidence, AI correlation/inference, recommended analyst next steps, transient drafts, and production action preview controls

#### Scenario: Metadata is visible
- **WHEN** an investigation result is displayed
- **THEN** the UI shows provider, model, local/paid state, estimated cost, token estimates, latency, fallback state, tool usage, source counts, truncation, and incomplete-result indicators

#### Scenario: Draft state is visually clear
- **WHEN** an automatic draft is displayed
- **THEN** the UI visibly labels it as AI-generated, not saved, not applied, read-only, and requiring analyst review before any future workflow

#### Scenario: Failure states are non-destructive
- **WHEN** an investigation has disabled AI, unavailable provider, timeout, fallback blocked, invalid tool output, forbidden evidence, insufficient context, partial results, or cancellation
- **THEN** the UI gives a clear non-destructive explanation and does not imply that remediation or production mutation occurred

### Requirement: Existing safety controls are preserved
The system SHALL preserve existing RBAC, audit logging, idempotency, protected-target checks, fail-closed provider guards, secret redaction, simulated-versus-real outcome labels, deterministic detection/correlation behavior, and human-approved production action boundaries.

#### Scenario: RBAC is enforced throughout the workflow
- **WHEN** an advanced investigation uses context, tools, drafts, or action-preview affordances
- **THEN** each service enforces the same or stricter role boundary as the canonical source or action it reuses

#### Scenario: Audit and logs remain safe
- **WHEN** advanced investigation metadata is logged or audited
- **THEN** it includes only safe metadata such as actor, route, workflow type, step names, statuses, counts, latency, provider/model, fallback state, and error codes, not prompt text, raw chat history, raw evidence bodies, credentials, or full draft bodies

#### Scenario: No safety boundary is bypassed
- **WHEN** advanced AI assistance completes successfully
- **THEN** it has not bypassed deterministic detections, existing correlation engines, approval gates, protected-target checks, idempotency, fail-closed integration guards, or explicit production action confirmation
