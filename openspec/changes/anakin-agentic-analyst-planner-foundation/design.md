## Context

The canonical SIEM conversation path currently classifies `workflow:auto` in `workflow_request_service` before `conversation_orchestration_service` resolves the thread, entity, corrections, conclusions, unresolved questions, or verified evidence. Explicit workflow values bypass reinterpretation entirely. `workflow_orchestrator` classifies again at execution, while `investigation_planner` deterministically chooses a predeclared sequence of SOC read tools for Deep Investigate; the model cannot request tools.

Session memory already separates analyst statements, corrections, model inferences with confidence/provenance, unresolved questions, and verified evidence with freshness. Planner input can therefore be assembled from authoritative server state without trusting browser history. Canonical `/ai/workflows` and `/ai/workflows/requests` conversation envelopes are the eligible boundary. Legacy stateless routes remain compatible. Repo Assistant, SOC Briefing, action preview/confirm, response execution, and all mutation paths remain isolated.

## Goals / Non-Goals

**Goals:**

- Reinterpret every eligible current turn after server-owned context/entity resolution and before capability selection.
- Produce a strict, bounded, validated, read-only plan and dispatch it through existing capabilities.
- Distinguish direct answers, one bounded evidence lookup, bounded investigation, decision support, artifact preview, comparison, clarification, and boundary responses.
- Prevent prior workflow labels, unsupported claims, stale evidence, or model-proposed entities/tools from becoming authoritative.
- Measure planner packet, prompt, output, repair count, and repeated-run contract performance.

**Non-Goals:**

- An iterative tool loop, autonomous investigation, more than one planner-selected evidence action, new SOC tools, workflow removal, full capability conversion, changes to non-planner model/profile assignments, frontend redesign, long-term memory, embeddings/RAG, mutation, or workspace writes.

## Decisions

### Planning occurs after authoritative resolution and before persistence/dispatch

`conversation_orchestration_service` exposes a read-only planning preparation step that validates owner/thread/version/entity and selects compact thread context without appending a turn. The planner call occurs outside a database transaction. Submission then reopens the authoritative thread, requires the original expected version, persists the turn using the validated plan, and dispatches the selected capability. This prevents a slow model call from holding row locks and makes concurrent state changes fail with the existing optimistic conflict.

The current request's explicit validated entity remains authoritative. A proposed entity must match the server-resolved entity set; a model cannot switch focus or invent an entity. Alternative: plan before entity resolution. Rejected because model-selected identity could conflict with ownership and execution payloads.

### One strict plan proposal, one bounded repair, deterministic authority

The model produces a strict proposal containing only: `current_turn_intent`, `evidence_sufficiency`, `required_evidence`, `proposed_strategy`, `proposed_tool_categories`, `clarification_question`, `reasoning_summary`, `stopping_condition`, and `confidence`. The server compiles that validated reasoning proposal into the full `AgenticAnalystPlan` by attaching authoritative entities, derived prior-turn relationship, strategy-mapped capability, and immutable read-only safety. Text is parsed as one JSON object; arbitrary objects are never executed or stringified into analyst output.

Validation requires exactly the model-owned fields and rejects model-supplied server-owned fields as unknown rather than ignoring or rewriting them. It enforces enumerated strategies, strategy/tool/evidence relationships, one approved read-tool category at most, authoritative entity requirements, owner/namespace boundaries, evidence/provenance rules, size limits, stopping conditions, and preview-only artifact safety. An invalid first result receives one repair request containing only bounded validation errors and the original compact packet. A second invalid result, timeout, or provider failure returns a concise planner-unavailable or clarification response and preserves prior state. It never invokes the prior workflow as fallback.

### Planner contract ownership

| Field | Owner | Reason |
|---|---|---|
| `current_turn_intent` | Model | Interpreting the analyst's present objective requires semantic reasoning. |
| `evidence_sufficiency` | Model | Assessing whether current evidence can answer the question is a reasoning decision constrained by freshness metadata. |
| `required_evidence` | Model | Identifying the missing information is part of investigation planning. |
| `proposed_strategy` | Model | Selecting the bounded analytical approach is the planner's central responsibility. |
| `proposed_tool_categories` | Model | Choosing one approved evidence category, when lookup is needed, follows from the evidence gap. |
| `clarification_question` | Model | A concise semantic clarification may be needed when ambiguity reaches the planner; deterministic resolver clarifications still bypass model generation. |
| `reasoning_summary` | Model | Records why the strategy and evidence decision fit the current turn. |
| `stopping_condition` | Model | Defines when the bounded analytical task has answered the current question. |
| `confidence` | Model | Expresses confidence in the reasoning proposal, not confidence in authoritative identity. |
| `resolved_entities` | Server | Entity identity and comparison membership are already validated by ownership-aware resolution. |
| `relationship_to_prior_turn` | Derived by server | Existing reference-resolution intent deterministically maps to continuation, new question, entity switch, comparison, or clarification response. |
| `proposed_capability` | Derived by server | `STRATEGY_CAPABILITY` is the authoritative one-to-one bounded dispatch mapping. |
| `read_only` / `mutation_allowed` | Server | Safety policy is immutable application authority, never a model choice. |
| Profile, model, provider, lifecycle, workflow request, and execution metadata | Server | These are observed application/runtime facts and are not part of planner reasoning. |

The compiled plan remains the internal/downstream contract, so execution and audit metadata retain the complete shape without asking the model to reproduce known values. A later optimistic-concurrency alignment check still compares compiled entities with the current resolved execution context before dispatch.

Current explicit shortcut intent is a non-authoritative hint. When the planner provider is unavailable, an explicit current-turn shortcut may continue through its existing safe capability because it is a user action on this turn, not inherited history; `workflow:auto` fails safely without keyword routing.

### Planner packet is fit by construction

The packet uses the current message, server-resolved primary/comparison entities, compact conclusions, one unresolved question, corrections, fresh verified-evidence summaries with timestamps, selected recent turns, available capabilities/read-tool categories, safety boundaries, and latency/budget class. Stored text is labeled untrusted data and cannot supply instructions.

Fixed schema/safety/provenance overhead is measured first. Optional categories have deterministic item/text limits and are admitted in priority order: resolved entity, corrections, unresolved question, conclusions, fresh evidence, recent turns, secondary entities. Stale evidence is represented only by identity/freshness metadata and cannot satisfy evidence requirements. The final serialized packet and full prompt are checked before generation; a mandatory-skeleton overflow is a configuration error, not ordinary user overflow. The entire thread and raw tool results are never sent.

### Existing capabilities remain execution authorities

Validated strategies map to current paths: `direct_answer` and `quick_evidence_lookup` to Quick Explain, `bounded_investigation` and `compare_entities` to Deep Investigate, `decision_support` to Decision Support, and `artifact_draft` to Generate Artifact. Clarification and boundary plans create assistant turns without model/tool workflow execution. One planner-selected tool category is translated into bounded execution context; the existing workflow implementation and SOC tool allowlists remain authoritative.

`workflow_orchestrator` receives the validated capability in server-only planner metadata and does not reclassify it from stale request labels. Response metadata records plan strategy, capability, entities, evidence sufficiency, and whether repair occurred, but not hidden reasoning.

### Planner selects task shape, not prose template

The planner's reasoning summary is audit metadata, not the answer. Downstream prompts receive the current intent and strategy so direct lookups answer directly, comparisons compare, evidence requests cite evidence, recommendations lead with the recommendation, and deep investigations retain structured analysis. Existing persona safety and evidence grounding remain. Fact/inference/confidence headings are not forced onto every response.

### Provider capabilities and original workflow boundaries are pre-dispatch contracts

Every capability emitted by an application service must be registered explicitly by the intended provider. The local Ollama provider advertises `agentic_analyst_planning`; the gateway continues to reject every unadvertised capability before generation. Contract tests exercise the real gateway/provider boundary and prove that a planner request reaches Ollama generation while paid fallback remains unavailable for the local-only planning profile.

The original workflow value from the SIEM conversation request is validated before context selection, planner generation, repair, classification, or degraded shortcut fallback. `auto` and the four SIEM conversation capabilities are allowed. Repo Assistant and SOC Briefing are rejected as isolated namespaces, and unknown workflow names are rejected as unsupported. The validated plan is checked again after planning, but no transformed workflow may erase an explicit original boundary violation.

### Planner uses a dedicated local 8B profile

The planner requests the approved `agentic_planning` profile through the profile registry and gateway for both its initial proposal and its single repair attempt. The profile defaults to `llama3.1:8b`, is local-only, disables paid fallback, and owns an 8,000-character prompt budget, 1,024-token output budget, 90-second timeout, and low deterministic temperature. Provider response metadata records the selected profile and model.

`fast_triage` remains assigned to Quick Explain and other existing short-triage paths with `llama3.2:3b`; Guided Analysis, Deep Briefing, and Developer Assistant retain their existing assignments. Planner prompt instructions make strategy/capability/tool relationships explicit, but deterministic validation remains authoritative and performs no intent-changing correction. At most one model repair remains permitted.

## Failure-Class Table

| Failure class | General invariant | Deterministic enforcement location | Model responsibility | Variants tested |
|---|---|---|---|---|
| New question trapped in prior workflow | Every eligible current turn is planned independently; prior workflow is context only | Conversation submission and dispatch | Classify current relationship/intent | Lookup, topic switch, evidence-gap request |
| Same intent phrased differently | Plan contract is semantic, not an exact-sentence router | Planner prompt/evaluation suite | Return equivalent strategy | Three phrasings for ten intent classes |
| No tool despite missing evidence | Insufficient evidence requires one approved lookup, investigation, or clarification | Plan validator | Identify required evidence | No/partial/stale evidence |
| Tool despite sufficient evidence | Direct answer forbids tool categories | Plan validator | Assess sufficiency | Existing current evidence, prior conclusion |
| Forbidden tool/capability | Only mapped capabilities and approved read categories pass | Plan validator/dispatch | Propose within boundary | Mutation, Repo, SOC, unknown tool |
| Wrong or switched entity | Model cannot propose identity; compiled entities come from server-resolved accessible context and are rechecked before dispatch | Plan compiler and execution alignment validator | Reason about only the packet entities | Explicit switch, stale focus, attempted model override |
| Ambiguity answered | Ambiguous resolution requires clarification and no execution | Resolver/validator | Ask concise clarification | Multiple IPs/alerts, missing referent |
| Stale evidence treated as current | Stale evidence cannot satisfy evidence sufficiency | Packet builder/validator | Request refresh or qualify | Expired and mixed-freshness evidence |
| User claim or inference promoted to fact | Assertion provenance is immutable in packet and plan | Context builder/validator | Treat claims as statements/inferences | Scanner, owned IP, service account |
| Invalid or repaired-invalid schema | Exactly one repair; then fail closed without sticky fallback | Parser/validator/planner service | Produce/repair strict JSON | Missing fields, bad enum, malformed JSON |
| Plan/prompt over budget | Mandatory packet fits; optional content compacts; final sizes checked against the dedicated planner profile | Packet/prompt builder and `agentic_planning` profile | Stay within output contract | Production-sized thread/evidence/entity state, initial and repair prompts |
| Planner assigned an undersized or shared workflow model | Planner always selects its dedicated local-only 8B profile; other workflow assignments remain unchanged | Profile registry, config, planner request, provider metadata tests | Satisfy the existing plan contract | Initial plan, repair, Quick Explain regression, all profile inventory defaults |
| Deterministic metadata causes otherwise useful plan rejection | Model emits reasoning fields only; server-owned fields are compiled from authoritative state or strategy mapping | Strict proposal parser and plan compiler | Return exactly the reasoning proposal | Omitted deterministic fields, attempted overrides, full compiled metadata |
| Timeout/provider failure | Preserve prior state and return planner unavailable; no old dispatch | Planner service/orchestration | None after failure | Timeout, disabled, provider error |
| Repeated ineffective strategy/answer | Current intent and strategy are recorded; identical prior answer is not reused as current response | Planner validation/response metadata | Select current task | New lookup after explain; topic switch |
| Workflow label used as content | Previous/current labels are typed hints, never analyst evidence or prompt instructions | Packet builder | Weigh current hint only | Auto after Quick Explain/Decision Support |
| Repo/SOC/mutation boundary bypass | Ineligible namespace/action returns boundary plan, never SIEM dispatch | Route/orchestration/validator | Identify unsupported boundary | Repo query, briefing continuation, apply request |
| Application capability rejected before generation | Every emitted capability is explicitly advertised by its intended provider; unadvertised capabilities remain fail-closed | Provider capability declaration and gateway contract tests | None | Planner capability accepted by Ollama; arbitrary capability rejected |
| Original forbidden workflow erased by classification/fallback | Validate the original requested workflow before planning or fallback and retain it as authoritative boundary input | Conversation orchestration entry point and defensive post-plan validation | May identify textual boundary requests, but cannot override explicit workflow | Repo Assistant, SOC Briefing, unknown workflow, unavailable/malformed planner, working planner reclassification |

## Transaction and Concurrency Boundaries

1. Planning snapshot: owner-scoped read validates thread, expected version, entity access, and context; no mutation and no open lock during model generation.
2. Planner generation: local-only gateway call and optional one repair; no database transaction.
3. Submission: existing owner thread lock revalidates version/entity, persists the validated plan with the queued turn, and atomically creates/links async work.
4. Execution/completion: existing worker role revalidation, version guards, response normalization, and turn/state transactions remain authoritative.

## Risks / Trade-offs

- [The dedicated 8B local model may still fail cross-field validation] -> Keep deterministic validation and one repair, measure real-model runs after deployment, and stop before Spec 2 if the valid-plan rate remains weak.
- [A planner call adds latency] -> Use the dedicated bounded planning profile and compact packet; preserve explicit latency metadata and timeout handling.
- [Existing capabilities cannot execute every ideal plan] -> Validate only Spec 1 mappings and at most one bounded evidence category; defer iterative plans and complete capability conversion.
- [Two-phase planning can race with another tab] -> Require the planning snapshot's expected version at submission and replan after the client reloads.
- [Direct answer may still be stylistically repetitive downstream] -> Pass task shape without imposing prose; broader capability response conversion remains Spec 3.

## Migration Plan

No database migration or persistent runtime configuration edit is required because the dedicated profile has a source-owned default. Deploy later only after an approved commit and the documented Mac-to-VM process. Rollback restores the prior source commit; thread records remain valid and no stored plan is treated as evidence.

## Open Questions

The verified 3B model does not meet the planner contract. The dedicated 8B profile is an implementation correction based on measured local-model evidence, but its production valid-plan rate remains a deployment acceptance question. Failure after one repair is reported as a model capability limitation and does not authorize validator weakening or Spec 2 work.
