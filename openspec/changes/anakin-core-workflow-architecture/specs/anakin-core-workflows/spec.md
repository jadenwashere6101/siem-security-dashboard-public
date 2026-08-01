## ADDED Requirements

### Requirement: Canonical Anakin workflow orchestration
The system SHALL route every Anakin AI interaction through exactly one backend-owned canonical workflow: `quick_explain`, `deep_investigate`, `decision_support`, `generate_artifact`, `soc_briefing`, or `repo_assistant`.

#### Scenario: Canonical workflow envelope is accepted
- **WHEN** an authenticated analyst submits a canonical workflow request with `workflow`, `context_type`, and a bounded `prompt` or workflow-specific payload
- **THEN** the backend SHALL validate the shared envelope
- **AND** dispatch to exactly one workflow engine
- **AND** return `workflow`, `classification`, `lifecycle`, `result`, and `metadata` in the canonical response envelope.

#### Scenario: Clients cannot choose execution profile
- **WHEN** a request includes client-supplied `model`, `profile`, `provider`, `timeout`, or output budget fields
- **THEN** the backend SHALL ignore or reject those fields
- **AND** SHALL use backend-owned workflow-to-profile routing.

### Requirement: Conservative auditable auto-routing
Natural-language requests MAY use `workflow=auto`; classification SHALL be deterministic, auditable, and conservative.

#### Scenario: Auto-routing returns classification metadata
- **WHEN** a request uses `workflow=auto`
- **THEN** the response SHALL include `requested_workflow`, `classified_workflow`, `confidence`, and `reason`.

#### Scenario: Auto-routing never reaches privileged capabilities
- **WHEN** a normal auto-routed request mentions repo architecture, SOC briefing generation, preview, confirm, apply, save, block execution, or another privileged/mutating capability
- **THEN** the backend SHALL NOT route to `repo_assistant`, `soc_briefing`, `/ai/actions/preview`, or `/ai/actions/confirm`
- **AND** SHALL return either `quick_explain` with conservative guidance or `chooser_required` with safe workflow options.

#### Scenario: Low-confidence auto-routing fails conservatively
- **WHEN** classifier confidence is low
- **THEN** the backend SHALL route to `quick_explain` by default
- **OR** return `chooser_required` with explicit allowed options.

### Requirement: Workflow-specific contracts
Each canonical workflow SHALL define accepted context, output schema, validation, failure behavior, profile, token bounds, lifecycle mode, and latency target.

#### Scenario: Quick Explain contract
- **WHEN** `quick_explain` runs
- **THEN** it SHALL use `fast_triage`
- **AND** SHALL return a concise explanation using only supplied/bounded context
- **AND** SHALL preserve insufficient-context and provider failure behavior.

#### Scenario: Deep Investigate contract
- **WHEN** `deep_investigate` runs
- **THEN** it SHALL use `guided_analysis`
- **AND** SHALL include support, contradiction or benign possibilities, missing evidence, confidence, and read-only next steps when evidence allows
- **AND** SHALL expose truthful lifecycle stages suitable for polling.

#### Scenario: Decision Support contract
- **WHEN** `decision_support` runs
- **THEN** it SHALL recommend one of `block`, `monitor`, `escalate`, `ignore`, or `gather_more_evidence`
- **AND** SHALL include reasoning, confidence, prerequisites, risks, alternatives, and missing evidence
- **AND** SHALL NOT generate artifacts, preview actions, confirm actions, or mutate state.

#### Scenario: Generate Artifact contract
- **WHEN** `generate_artifact` runs
- **THEN** it SHALL use `guided_analysis`
- **AND** SHALL validate the requested artifact type and context with strict draft schemas
- **AND** SHALL allow no more than one bounded repair attempt before returning validation failure.

#### Scenario: SOC Briefing contract
- **WHEN** `soc_briefing` runs
- **THEN** it SHALL be reachable only through explicit SOC briefing routes/jobs
- **AND** SHALL use `deep_briefing`
- **AND** SHALL preserve briefing lifecycle, RBAC, worker readiness, and delivery guard behavior.

#### Scenario: Repo Assistant contract
- **WHEN** `repo_assistant` runs
- **THEN** it SHALL be reachable only through explicit repo assistant routes
- **AND** SHALL require super-admin authorization
- **AND** SHALL use `developer_assistant`
- **AND** SHALL preserve cited repository evidence validation.

### Requirement: Legacy AI routes remain compatible
The existing AI routes SHALL remain functional through compatibility adapters during this phase.

#### Scenario: Existing explain actions map to canonical workflows
- **WHEN** a legacy `/ai/explain` request uses a supported action ID
- **THEN** the route SHALL process successfully through the workflow orchestrator
- **AND** the response SHALL identify the canonical workflow in metadata.

#### Scenario: Existing draft route maps to Generate Artifact
- **WHEN** a legacy `/ai/drafts` request uses a supported draft type
- **THEN** the route SHALL process through `generate_artifact`
- **AND** SHALL preserve strict draft output and validation behavior.

#### Scenario: Existing investigation route maps to Deep Investigate
- **WHEN** a legacy `/ai/investigations` request is submitted
- **THEN** the route SHALL process through `deep_investigate`
- **AND** SHALL include lifecycle stage metadata without fabricating progress.

### Requirement: Production safety and permission boundaries
Workflow orchestration SHALL NOT weaken local-only policy, no-paid-fallback behavior, RBAC, sanitization, bounded tools, audit logging, or mutation gates.

#### Scenario: Preview and confirm remain separate
- **WHEN** Generate Artifact creates a draft
- **THEN** generation SHALL remain read-only
- **AND** any preview or confirm action SHALL continue through separate gated routes with existing permission, idempotency, and confirmation checks.

#### Scenario: Offline acceptance inventory covers workflows
- **WHEN** AI action inventory or workflow mapping changes
- **THEN** the offline acceptance harness SHALL fail unless every known AI action maps to one canonical workflow and approved profile.
