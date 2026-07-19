## ADDED Requirements

### Requirement: Drafting assistant generates review-only AI drafts
The system SHALL generate AI-authored SOC drafts only as reviewable proposed content and SHALL NOT apply, persist, execute, approve, or submit any draft as production state.

#### Scenario: Draft response is clearly review-only
- **WHEN** an authenticated analyst requests a supported draft
- **THEN** the response includes `ai_generated=true`, `read_only=true`, `persisted=false`, `applied=false`, and `approval_required_before_apply=true`

#### Scenario: Draft generation does not write production state
- **WHEN** a draft is generated successfully
- **THEN** the system does not create or update incidents, notes, detection rules, playbooks, response registry records, approvals, SOAR executions, blocklists, files, commits, deployments, migrations, or database state

#### Scenario: Drafts are not background work
- **WHEN** the backend starts, AI status is checked, or read tools are configured
- **THEN** no draft generation occurs until an authenticated analyst or super administrator explicitly submits a draft request

### Requirement: Canonical draft schemas are centralized
The system SHALL define supported draft types, input rules, output schemas, validation rules, labels, limits, and source metadata expectations in one backend location under `core/ai`.

#### Scenario: Supported draft type set is fixed
- **WHEN** a draft request is validated
- **THEN** only `detection_rule_change`, `playbook_draft`, `incident_note`, `escalation_summary`, `response_recommendation`, and `investigation_checklist` are accepted

#### Scenario: Unsupported draft type fails safely
- **WHEN** a request names an unsupported or mutation-like draft type
- **THEN** the system returns a validation failure before context building, read-tool execution, gateway inference, or production helper calls occur

#### Scenario: Draft schema validation is required
- **WHEN** a provider returns draft content
- **THEN** the system validates the content against the selected canonical draft schema before returning it as a usable draft

### Requirement: Draft generation reuses existing AI and SIEM read paths
The system SHALL build drafts from the Phase 1A gateway, Phase 1B canonical context builder, and optional Phase 3 read-tool evidence without introducing parallel SIEM query logic or direct provider data access.

#### Scenario: Context comes from canonical context builder
- **WHEN** a draft request includes a SIEM context type and identifiers
- **THEN** the system gathers draft grounding through the existing AI context builder rather than duplicating route SQL or provider-side data access

#### Scenario: Optional tool evidence uses read-tool executor
- **WHEN** a draft request enables read-tool evidence
- **THEN** the system gathers evidence only through the fixed Phase 3 SOC read-tool executor and returns tool source metadata with the draft

#### Scenario: Provider receives prompt only
- **WHEN** the AI gateway is called for draft generation
- **THEN** providers receive a bounded prompt payload and never receive database handles, cursors, shell/file handles, credentials, mutation callbacks, or direct SIEM service objects

### Requirement: Draft route is thin, authenticated, and RBAC-protected
The system SHALL expose draft generation through a thin authenticated API route protected by existing analyst/super-admin authorization.

#### Scenario: Authenticated analyst requests draft
- **WHEN** an authenticated analyst or super administrator posts valid JSON to `POST /ai/drafts`
- **THEN** the route validates the request through the drafting service and returns the draft service response without route-local draft business logic

#### Scenario: Unauthenticated request is rejected
- **WHEN** an unauthenticated user posts to the draft endpoint
- **THEN** existing authentication behavior rejects the request before context building, read-tool execution, or gateway inference

#### Scenario: Insufficient role is rejected
- **WHEN** a user without analyst or super-admin access posts to the draft endpoint
- **THEN** existing RBAC behavior rejects the request before draft generation

### Requirement: Draft prompts and responses are grounded and bounded
The system SHALL instruct the model to use only supplied SIEM context and read-tool evidence, enforce request/prompt size limits, and return insufficient-context or validation-failure states instead of inventing unsupported drafts.

#### Scenario: Missing context fails safely
- **WHEN** required context identifiers are missing, not found, unauthorized, or too thin for the selected draft type
- **THEN** the system returns an insufficient-context response and does not present fabricated draft content

#### Scenario: Prompt size is bounded
- **WHEN** SIEM context, tool evidence, history, or instruction text would exceed configured AI prompt limits
- **THEN** the system truncates lower-priority evidence with metadata or fails safely before calling the gateway

#### Scenario: Malformed provider output is not accepted
- **WHEN** the provider response cannot be parsed or does not satisfy the selected draft schema
- **THEN** the system returns `draft_validation_failed` with safe validation errors and does not present the malformed output as a valid draft

### Requirement: Drafts are separated from approval and execution paths
The system SHALL keep AI-generated drafts separate from existing production mutation, approval, SOAR, response registry command, and execution APIs.

#### Scenario: Existing mutation helpers are not called
- **WHEN** any supported draft type is generated
- **THEN** incident note creation, incident status updates, detection rule saves, playbook definition creates/updates, playbook execution creates/retries/resumes/abandons, approval actions, response registry commands, blocklist mutations, migrations, shell commands, file writes, commits, pushes, and deployment helpers are not called

#### Scenario: Draft cannot be submitted as action payload in Phase 4
- **WHEN** the frontend receives a valid draft
- **THEN** the UI does not automatically submit it to any production API and does not expose an apply, approve, execute, save-to-production, or run action for the draft

#### Scenario: Future approval boundary is explicit
- **WHEN** a draft describes a possible action or production change
- **THEN** the response labels it as a proposal requiring a separate future approval/execution workflow before anything can happen

### Requirement: Draft output is source-attributed and secret-safe
The system SHALL include source attribution, provider metadata, tool metadata when used, validation state, and secret-safe content handling for every draft response.

#### Scenario: Draft includes sources
- **WHEN** a draft is returned
- **THEN** the response includes context sources and any read-tool sources used to ground the draft

#### Scenario: Credential-like values are redacted
- **WHEN** draft input context, tool evidence, model output, logs, or response serialization contains credential-like keys or values
- **THEN** those values are redacted before prompt construction, logging, and API response serialization

#### Scenario: Logs are metadata-only
- **WHEN** draft generation succeeds or fails
- **THEN** logs contain only safe metadata such as route, actor identifier, draft type, status, validation state, source counts, tool names/statuses, latency, and error code, not prompt text, raw evidence, chat history, credentials, or full draft bodies

### Requirement: Frontend presents drafts as AI-generated proposals
The frontend SHALL reuse the existing analyst AI surfaces where practical and SHALL present draft content with clear review-only labels, validation state, source metadata, gateway metadata, and safe lifecycle controls.

#### Scenario: Draft panel labels non-production state
- **WHEN** a draft is displayed
- **THEN** the UI visibly shows that it is AI-generated, not saved, not applied, read-only, and requires analyst review before any future production workflow

#### Scenario: Draft UI preserves existing AI lifecycle controls
- **WHEN** a draft request is loading, canceled, retried, dismissed, fails, or becomes stale after navigation/context changes
- **THEN** the UI follows existing AI loading, cancellation, retry, dismissal, stale-response, responsive layout, and metadata display behavior

#### Scenario: Draft copy/export remains safe
- **WHEN** the UI offers copy or export of draft text
- **THEN** it copies only displayed review content and preserves the AI-generated draft label without submitting production changes

### Requirement: Drafting remains distinct from repo assistant and SOC read tools
The system SHALL keep Phase 4 drafting separate from the Phase 2 repo assistant and SHALL use Phase 3 SOC read tools only as optional evidence providers, not as draft execution tools.

#### Scenario: Repo assistant is not used for analyst drafts
- **WHEN** an analyst requests a SOC draft
- **THEN** the request does not retrieve repository files and does not call `/ai/repo/chat` or repo-assistant indexing services

#### Scenario: Read tools remain evidence-only
- **WHEN** a draft request uses Phase 3 SOC read tools
- **THEN** the tool results are treated as grounding evidence only and do not cause production writes or autonomous follow-up tool loops
