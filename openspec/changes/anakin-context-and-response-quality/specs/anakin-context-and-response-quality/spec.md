## ADDED Requirements

### Requirement: Interactive AI actions use bounded task-specific context
Every in-scope SOC-facing Anakin action SHALL build a bounded evidence package before prompt serialization.

#### Scenario: Entity actions do not receive full dashboard context
- **WHEN** an alert, source-IP, incident, recon activity, response registry, draft, or guided-investigation button is clicked
- **THEN** the frontend SHALL send stable entity identifiers and concise command metadata
- **AND** SHALL NOT automatically include full visible dashboard metrics, timeline, map markers, or recent-alert arrays.

#### Scenario: Backend bounds evidence before serialization
- **WHEN** backend context is built for alert, source-IP, incident, recon activity, response registry, dashboard, or general context
- **THEN** the builder SHALL limit rows and fields before JSON prompt serialization
- **AND** SHALL NOT serialize full raw domain objects directly into prompts
- **AND** SHALL report included counts, omitted counts, and truncation state.

#### Scenario: SOC Command Center prompt remains within limit
- **WHEN** recon activity explain, cluster investigation, guided investigation, or draft actions are requested with large realistic recon evidence
- **THEN** the prompt SHALL remain within the selected profile prompt limit
- **AND** the response context metadata SHALL describe omitted or truncated evidence.

### Requirement: Profile-specific prompt budgets are authoritative
Interactive AI services SHALL apply the selected profile's prompt limit consistently before provider invocation.

#### Scenario: Service-level and provider-level limits align
- **WHEN** an explain, chat, draft, or guided investigation prompt is assembled
- **THEN** the service SHALL select the semantic profile first
- **AND** SHALL compare the prompt length against that profile's `max_prompt_chars`
- **AND** SHALL return a clear bounded-context failure if the prompt still exceeds the selected profile limit.

#### Scenario: Clients cannot alter model or timeout
- **WHEN** client payloads include arbitrary `model`, `profile`, `timeout`, `max_prompt_chars`, or provider fields
- **THEN** the backend SHALL ignore or reject those fields
- **AND** SHALL use only backend-owned action/profile mapping.

### Requirement: Correlation-heavy actions use guided analysis
The profile inventory SHALL route correlation-heavy interactive actions to `guided_analysis`.

#### Scenario: Heavy explain actions are reassigned
- **WHEN** recon interpretation, noisy source-IP analysis, incident reasoning, alert investigation recommendation, or response-registry review actions request AI
- **THEN** the backend SHALL use `guided_analysis`.

#### Scenario: Fast actions remain fast
- **WHEN** dashboard summary, dashboard graph quick explanation, short alert explanation, or general floating chat requests AI
- **THEN** the backend MAY use `fast_triage` if the context package is bounded and low reasoning.

### Requirement: Read-only stale responses remain viewable
Read-only AI explanations SHALL remain visible when normal UI refreshes occur.

#### Scenario: Background refresh only marks advisory stale state
- **WHEN** a read-only AI explanation succeeds and dashboard filters, selected alert state, or background data refreshes afterward
- **THEN** the UI SHALL keep the answer visible
- **AND** MAY show an advisory stale notice.

#### Scenario: Confirmable previews remain strictly protected
- **WHEN** a confirmable or mutating AI action preview becomes stale
- **THEN** the UI SHALL block confirmation until the preview is regenerated.

### Requirement: AI responses add analytical value
Interactive prompts SHALL request concise, evidence-grounded analysis rather than robotic field repetition.

#### Scenario: Prompt prohibits repetitive output
- **WHEN** an in-scope prompt is generated
- **THEN** it SHALL instruct the model not to repeat alert descriptions, list every visible field, provide generic security definitions, or use generic filler.

#### Scenario: Prompt requests useful analyst content
- **WHEN** an in-scope prompt is generated
- **THEN** it SHALL request assessment, standout observations, environment-specific relevance, correlations, supporting evidence, contradicting or benign evidence, uncertainty/confidence, missing evidence, and specific read-only next steps as appropriate for the task.

### Requirement: Complete in-scope action inventory
The system SHALL maintain tests that map every in-scope SOC-facing AI action to exactly one approved profile and bounded context builder.

#### Scenario: Inventory catches unmapped actions
- **WHEN** a new in-scope frontend action, backend explain action, draft type, or guided workflow is added
- **THEN** tests SHALL fail unless it is assigned an approved profile and bounded context behavior.

#### Scenario: No production mutation path is introduced
- **WHEN** any in-scope AI action runs
- **THEN** it SHALL remain read-only/advisory
- **AND** SHALL NOT approve, execute, mutate production, add paid fallback, or expose provider secrets.
