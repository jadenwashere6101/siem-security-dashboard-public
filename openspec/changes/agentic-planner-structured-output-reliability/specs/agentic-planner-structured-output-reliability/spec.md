## ADDED Requirements

### Requirement: One authoritative planner output contract
The system SHALL expose one serializable planner output contract derived from the same backend authorities used for validation. It MUST represent required and optional top-level fields, scalar and collection types, enums, nullability, conditional requirements, action/strategy/capability compatibility, entity and tool cardinality, required-evidence shape and bounds, per-tool evidence keys, scalar formats and bounds, the seven-day time-window limit, the ten-result limit, hostname/username exclusion, entity/evidence binding compatibility, artifact requirements, clarification requirements, and correction-turn requirements. Initial instructions, repair instructions, and contract tests MUST consume this authority and MUST NOT maintain an independent competing contract.

#### Scenario: Contract and validation remain aligned
- **WHEN** validator-owned enums, bounds, tool filters, entity bindings, or semantic relationships are inspected
- **THEN** the serialized planner contract exposes the same values used by validation
- **AND** regression tests fail if those authorities drift

#### Scenario: Broad valid strategies are represented
- **WHEN** the contract describes direct answer, bounded lookup, clarification, artifact draft, comparison, bounded investigation, decision support, correction, or boundary strategies
- **THEN** it exposes the exact capability nullability, entity/tool cardinality, and conditional fields required for each strategy

### Requirement: Planner instructions match the authoritative contract
Initial and repair prompts SHALL instruct the model to return exactly one bare JSON object conforming to the authoritative contract. They MUST accurately describe `required_evidence` as a bounded array, conditional `artifact_type`, nullable `proposed_capability`, entity and tool maxima, allowed evidence keys per category, scalar types/formats/bounds, entity/evidence identity binding, clarification fields, and correction references while remaining within the configured prompt budget.

#### Scenario: Lookup instructions are complete
- **WHEN** the model is instructed to create a quick evidence lookup
- **THEN** it receives the exact array, tool, filter, value-bound, and entity-binding contract used by validation

#### Scenario: Non-executable strategies use null capability
- **WHEN** clarification or unsupported/boundary output is described
- **THEN** the prompt identifies `proposed_capability` as required with a null value and prohibits tool execution

### Requirement: Anthropic completion metadata is sanitized and deterministic
The Anthropic adapter SHALL preserve sanitized stop reason and normalized completion state sufficient to distinguish normal completion, output exhaustion, malformed/no-text response, and provider transport/error state. It SHALL combine non-empty text blocks deterministically in provider order, SHALL exclude thinking blocks from planner text and metadata, and MUST NOT persist hidden reasoning, prompts, secrets, or authorization material.

#### Scenario: Multiple text blocks complete normally
- **WHEN** Anthropic returns multiple text blocks and a normal stop reason
- **THEN** the adapter joins only text blocks in response order and marks the completion complete

#### Scenario: Thinking-only exhausted response
- **WHEN** Anthropic returns thinking content without text and reports `max_tokens`
- **THEN** no thinking is exposed as planner text or persisted metadata
- **AND** completion is classified as output exhaustion rather than malformed reasoning

#### Scenario: Provider transport fails
- **WHEN** Anthropic times out, rejects, or cannot transport the request
- **THEN** normalized metadata identifies the provider error state without exposing raw provider details

### Requirement: Output exhaustion is classified before validation
Planner orchestration MUST inspect provider completion state before parsing or validating initial and repair content. A `max_tokens` or equivalent output-exhaustion result MUST be classified as a provider-completion failure whether text is partial, absent, or accompanied only by thinking, and MUST NOT be mislabeled as ordinary malformed JSON or `invalid_agentic_plan`. The configured 4,096-token ceiling SHALL remain unchanged by this fix.

#### Scenario: Partial initial JSON is exhausted
- **WHEN** Anthropic returns a partial JSON text block with `stop_reason=max_tokens`
- **THEN** the planner records an initial output-exhaustion failure before JSON parsing
- **AND** no plan executes

#### Scenario: No-text initial output is exhausted
- **WHEN** Anthropic reports `max_tokens` with no usable text
- **THEN** the planner returns the explicit safe output-exhaustion classification rather than provider-malformed-response

#### Scenario: Repair output is exhausted
- **WHEN** the single repair response reports output exhaustion
- **THEN** repair terminates with a repair-stage output-exhaustion classification and no second repair or execution

### Requirement: Validation failures are typed and bounded
Internal planner validation SHALL return bounded structured errors containing a stable stage, code, path, and sanitized message. Error stages or codes MUST distinguish parse failure, schema/shape failure, semantic/cross-field failure, entity/evidence binding failure, and provider completion failure. No error packet may contain secrets, raw prompts, hidden reasoning, or an unbounded failed proposal.

#### Scenario: Malformed JSON fails parsing
- **WHEN** a normally completed response is not one JSON object
- **THEN** validation returns a typed parse failure with a root path

#### Scenario: Schema and semantic failures differ
- **WHEN** one proposal has missing or wrongly typed fields and another violates action/strategy/grounding rules
- **THEN** their typed errors identify schema and semantic stages respectively

#### Scenario: Entity identity is inconsistent
- **WHEN** a resolved entity has a missing or different evidence identity
- **THEN** validation returns an entity-binding error and rejects the plan before execution

### Requirement: Repair remains single, bounded, and safety-equivalent
The planner SHALL permit exactly one repair attempt. Repair SHALL receive bounded typed validation errors, a bounded safe representation of the invalid proposal, explicit values for fields proven valid and repair-stable, and the same authoritative output contract as the initial attempt. Preservation MUST derive from validated field state or an equivalent explicit mechanism, MUST NOT depend on prose-message substring matching, and MUST NOT bypass full schema, semantic, grounding, entity-binding, artifact, correction, or safety validation.

#### Scenario: One repair succeeds
- **WHEN** an initial proposal fails with typed validation errors and one corrected proposal satisfies the complete contract
- **THEN** the repaired plan is accepted after full validation
- **AND** explicitly preserved valid fields remain unchanged

#### Scenario: Repair changes a preserved decision
- **WHEN** a repair changes an explicitly preserved valid action or other repair-stable value
- **THEN** validation rejects the repair and no capability executes

#### Scenario: Repair remains invalid
- **WHEN** the one repair has parse, schema, semantic, grounding, binding, or safety defects
- **THEN** the planner returns a safe terminal failure with both attempt classifications and performs no additional generation

### Requirement: Parser enforces bare JSON only
The planner parser SHALL accept exactly one bare JSON object and MUST reject fenced JSON, surrounding prose, arrays, multiple objects, trailing commentary, and malformed or syntactically truncated JSON. It MUST NOT extract an embedded object or broaden tolerance for conversational text.

#### Scenario: Exactly one fenced object is rejected
- **WHEN** a response contains an otherwise valid object inside a Markdown code fence
- **THEN** parsing returns a typed parse failure

#### Scenario: Bare object is accepted
- **WHEN** a normally completed response consists only of one contract-valid JSON object
- **THEN** parsing proceeds to schema and semantic validation

### Requirement: Planner reliability observability is bounded and sanitized
The system SHALL log and persist bounded planner reliability metadata where existing planner metadata is stored. The metadata SHALL include attempt stage, provider completion state, stop reason, available token counts, plan character count, typed validation stage/code/path, repair-attempt state, final planner classification, and an existing safe accounting or correlation identifier when available. It MUST NOT persist raw prompts, raw hidden reasoning, API keys, secrets, authorization data, or large raw failed plans.

#### Scenario: Initial and repair both fail
- **WHEN** a normally completed initial proposal fails validation and the repair also fails
- **THEN** compact metadata retains sanitized classifications for both attempts and the terminal planner error

#### Scenario: Successful initial plan is observable
- **WHEN** the initial response completes normally and validates
- **THEN** metadata records initial completion and validation success without a repair attempt or raw plan copy

### Requirement: Final failures remain fail-closed and distinguishable
If initial and repair attempts do not produce a validated plan, the system MUST NOT execute a proposed capability, tool, artifact, or mutation. It SHALL return concise safe analyst-facing failure text while retaining typed internal metadata that distinguishes completion, parsing, schema, semantic, binding, and repair failures. A documented explicit shortcut fallback MAY apply only to a true provider-unavailable result permitted by the existing planner boundary and MUST NOT convert invalid or truncated planner output into execution.

#### Scenario: Invalid repair cannot trigger shortcut execution
- **WHEN** an explicitly hinted request receives an invalid initial proposal and invalid repair
- **THEN** no deterministic shortcut executes and the analyst receives a safe planner failure

#### Scenario: Truncation cannot trigger execution
- **WHEN** either planner attempt is output-exhausted
- **THEN** no partial plan, prior workflow, or unvalidated shortcut is executed

### Requirement: Intentional Anthropic temperature behavior is explicit
The system SHALL keep the planner profile's configured temperature available but SHALL omit Anthropic `temperature` from the outbound request until a validated repository provider/model contract explicitly authorizes it. The adapter MUST NOT make speculative provider request changes, and the existing 4,096 maximum output-token setting SHALL remain unchanged.

#### Scenario: Anthropic request uses established fields
- **WHEN** an offline mocked Anthropic planner request is built
- **THEN** it contains the configured model, 4,096 maximum tokens, and messages
- **AND** it omits temperature by documented design

### Requirement: Offline acceptance covers reliability outcomes
Deterministic offline tests and acceptance fixtures SHALL cover initial success, malformed and syntactically truncated JSON, partial/no-text/thinking-only output exhaustion, deterministic multiple text blocks, schema failure, semantic and grounding failure, entity-binding regression, successful repair, failed repair, repair exhaustion, broad valid planner strategies, safety regressions, and validation independent of user wording. Tests MUST NOT contact Anthropic or any other real provider.

#### Scenario: Acceptance fixture matrix runs offline
- **WHEN** the AI acceptance harness executes its planner reliability fixtures
- **THEN** it reports initial success, repair success, repair failure, and provider truncation with expected typed classifications and zero external traffic

#### Scenario: Safety matrix remains closed
- **WHEN** fixtures request unsupported tools, excess tools or entities, mutation metadata, invalid filters, wrong identity, unsupported capability/action combinations, ungrounded sufficient claims, or invalid correction references
- **THEN** every plan is rejected without deterministic language interpretation or execution
