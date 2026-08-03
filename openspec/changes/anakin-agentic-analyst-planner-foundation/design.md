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

- An iterative tool loop, autonomous investigation, more than one planner-selected evidence action, new SOC tools, workflow removal, full capability conversion, model/profile changes, frontend redesign, long-term memory, embeddings/RAG, mutation, or workspace writes.

## Decisions

### Planning occurs after authoritative resolution and before persistence/dispatch

`conversation_orchestration_service` exposes a read-only planning preparation step that validates owner/thread/version/entity and selects compact thread context without appending a turn. The planner call occurs outside a database transaction. Submission then reopens the authoritative thread, requires the original expected version, persists the turn using the validated plan, and dispatches the selected capability. This prevents a slow model call from holding row locks and makes concurrent state changes fail with the existing optimistic conflict.

The current request's explicit validated entity remains authoritative. A proposed entity must match the server-resolved entity set; a model cannot switch focus or invent an entity. Alternative: plan before entity resolution. Rejected because model-selected identity could conflict with ownership and execution payloads.

### One strict plan proposal, one bounded repair, deterministic authority

The planner produces JSON with: `current_turn_intent`, `relationship_to_prior_turn`, `resolved_entities`, `evidence_sufficiency`, `required_evidence`, `proposed_strategy`, `proposed_capability`, `proposed_tool_categories`, `clarification_question`, `reasoning_summary`, `stopping_condition`, `confidence`, and a read-only safety declaration. Text is parsed as one JSON object; arbitrary objects are never executed or stringified into analyst output.

Validation enforces enumerated strategy/capability mappings, one approved read-tool category at most, entity equality, owner/namespace boundaries, evidence/provenance rules, size limits, stopping conditions, and preview-only artifact safety. An invalid first result receives one repair request containing only bounded validation errors and the original compact packet. A second invalid result, timeout, or provider failure returns a concise planner-unavailable or clarification response and preserves prior state. It never invokes the prior workflow as fallback.

Current explicit shortcut intent is a non-authoritative hint. When the planner provider is unavailable, an explicit current-turn shortcut may continue through its existing safe capability because it is a user action on this turn, not inherited history; `workflow:auto` fails safely without keyword routing.

### Planner packet is fit by construction

The packet uses the current message, server-resolved primary/comparison entities, compact conclusions, one unresolved question, corrections, fresh verified-evidence summaries with timestamps, selected recent turns, available capabilities/read-tool categories, safety boundaries, and latency/budget class. Stored text is labeled untrusted data and cannot supply instructions.

Fixed schema/safety/provenance overhead is measured first. Optional categories have deterministic item/text limits and are admitted in priority order: resolved entity, corrections, unresolved question, conclusions, fresh evidence, recent turns, secondary entities. Stale evidence is represented only by identity/freshness metadata and cannot satisfy evidence requirements. The final serialized packet and full prompt are checked before generation; a mandatory-skeleton overflow is a configuration error, not ordinary user overflow. The entire thread and raw tool results are never sent.

### Existing capabilities remain execution authorities

Validated strategies map to current paths: `direct_answer` and `quick_evidence_lookup` to Quick Explain, `bounded_investigation` and `compare_entities` to Deep Investigate, `decision_support` to Decision Support, and `artifact_draft` to Generate Artifact. Clarification and boundary plans create assistant turns without model/tool workflow execution. One planner-selected tool category is translated into bounded execution context; the existing workflow implementation and SOC tool allowlists remain authoritative.

`workflow_orchestrator` receives the validated capability in server-only planner metadata and does not reclassify it from stale request labels. Response metadata records plan strategy, capability, entities, evidence sufficiency, and whether repair occurred, but not hidden reasoning.

### Planner selects task shape, not prose template

The planner's reasoning summary is audit metadata, not the answer. Downstream prompts receive the current intent and strategy so direct lookups answer directly, comparisons compare, evidence requests cite evidence, recommendations lead with the recommendation, and deep investigations retain structured analysis. Existing persona safety and evidence grounding remain. Fact/inference/confidence headings are not forced onto every response.

## Failure-Class Table

| Failure class | General invariant | Deterministic enforcement location | Model responsibility | Variants tested |
|---|---|---|---|---|
| New question trapped in prior workflow | Every eligible current turn is planned independently; prior workflow is context only | Conversation submission and dispatch | Classify current relationship/intent | Lookup, topic switch, evidence-gap request |
| Same intent phrased differently | Plan contract is semantic, not an exact-sentence router | Planner prompt/evaluation suite | Return equivalent strategy | Three phrasings for ten intent classes |
| No tool despite missing evidence | Insufficient evidence requires one approved lookup, investigation, or clarification | Plan validator | Identify required evidence | No/partial/stale evidence |
| Tool despite sufficient evidence | Direct answer forbids tool categories | Plan validator | Assess sufficiency | Existing current evidence, prior conclusion |
| Forbidden tool/capability | Only mapped capabilities and approved read categories pass | Plan validator/dispatch | Propose within boundary | Mutation, Repo, SOC, unknown tool |
| Wrong or switched entity | Proposed entities exactly match server-resolved accessible entities | Plan validator | Refer only to packet entities | Explicit switch, stale focus, fabricated ID |
| Ambiguity answered | Ambiguous resolution requires clarification and no execution | Resolver/validator | Ask concise clarification | Multiple IPs/alerts, missing referent |
| Stale evidence treated as current | Stale evidence cannot satisfy evidence sufficiency | Packet builder/validator | Request refresh or qualify | Expired and mixed-freshness evidence |
| User claim or inference promoted to fact | Assertion provenance is immutable in packet and plan | Context builder/validator | Treat claims as statements/inferences | Scanner, owned IP, service account |
| Invalid or repaired-invalid schema | Exactly one repair; then fail closed without sticky fallback | Parser/validator/planner service | Produce/repair strict JSON | Missing fields, bad enum, malformed JSON |
| Plan/prompt over budget | Mandatory packet fits; optional content compacts; final sizes checked | Packet/prompt builder | Stay within output contract | Production-sized thread/evidence/entity state |
| Timeout/provider failure | Preserve prior state and return planner unavailable; no old dispatch | Planner service/orchestration | None after failure | Timeout, disabled, provider error |
| Repeated ineffective strategy/answer | Current intent and strategy are recorded; identical prior answer is not reused as current response | Planner validation/response metadata | Select current task | New lookup after explain; topic switch |
| Workflow label used as content | Previous/current labels are typed hints, never analyst evidence or prompt instructions | Packet builder | Weigh current hint only | Auto after Quick Explain/Decision Support |
| Repo/SOC/mutation boundary bypass | Ineligible namespace/action returns boundary plan, never SIEM dispatch | Route/orchestration/validator | Identify unsupported boundary | Repo query, briefing continuation, apply request |

## Transaction and Concurrency Boundaries

1. Planning snapshot: owner-scoped read validates thread, expected version, entity access, and context; no mutation and no open lock during model generation.
2. Planner generation: local-only gateway call and optional one repair; no database transaction.
3. Submission: existing owner thread lock revalidates version/entity, persists the validated plan with the queued turn, and atomically creates/links async work.
4. Execution/completion: existing worker role revalidation, version guards, response normalization, and turn/state transactions remain authoritative.

## Risks / Trade-offs

- [The configured local model may not reliably satisfy the contract] -> Measure repeated controlled and available-local runs honestly; fail safely and recommend a controlled stronger-local-model evaluation rather than growing keyword rules.
- [A planner call adds latency] -> Use the existing fast local planning profile and compact packet; preserve explicit latency metadata and timeout handling.
- [Existing capabilities cannot execute every ideal plan] -> Validate only Spec 1 mappings and at most one bounded evidence category; defer iterative plans and complete capability conversion.
- [Two-phase planning can race with another tab] -> Require the planning snapshot's expected version at submission and replan after the client reloads.
- [Direct answer may still be stylistically repetitive downstream] -> Pass task shape without imposing prose; broader capability response conversion remains Spec 3.

## Migration Plan

No database migration or runtime configuration change is required. Deploy later only after an approved commit and the documented Mac-to-VM process. Rollback removes planner dispatch and server-only plan metadata while leaving thread records valid; no stored plan is treated as evidence.

## Open Questions

Whether the currently configured local model meets the repeated-run contract is an implementation measurement, not an assumed architecture decision. A failure is reported as a model capability limitation and does not authorize a model change in this spec.
