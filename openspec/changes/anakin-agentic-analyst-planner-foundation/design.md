## Context

The canonical SIEM conversation path currently classifies `workflow:auto` in `workflow_request_service` before `conversation_orchestration_service` resolves the thread, entity, corrections, conclusions, unresolved questions, or verified evidence. Explicit workflow values bypass reinterpretation entirely. `workflow_orchestrator` classifies again at execution, while `investigation_planner` deterministically chooses a predeclared sequence of SOC read tools for Deep Investigate; the model cannot request tools.

Session memory already separates analyst statements, corrections, model inferences with confidence/provenance, unresolved questions, and verified evidence with freshness. Planner input can therefore be assembled from authoritative server state without trusting browser history. Canonical `/ai/workflows` and `/ai/workflows/requests` conversation envelopes are the eligible boundary. Legacy stateless routes remain compatible. Repo Assistant, SOC Briefing, action preview/confirm, response execution, and all mutation paths remain isolated.

## Goals / Non-Goals

**Goals:**

- Reinterpret every eligible current turn from bounded server-owned context before capability selection, with all natural-language reference and entity selection performed by the planner.
- Produce a strict, bounded, validated, read-only plan and dispatch it through existing capabilities.
- Distinguish direct answers, one bounded evidence lookup, bounded investigation, decision support, artifact preview, comparison, clarification, and boundary responses.
- Prevent prior workflow labels, unsupported claims, stale evidence, or model-proposed entities/tools from becoming authoritative.
- Measure planner packet, prompt, output, repair count, and repeated-run contract performance.

**Non-Goals:**

- An iterative tool loop, autonomous investigation, more than one planner-selected evidence action, new SOC tools, workflow removal, full capability conversion, changes to non-planner model/profile assignments, frontend redesign, long-term memory, embeddings/RAG, mutation, or workspace writes.

## Decisions

### Planning occurs after authoritative context construction and before resolution, persistence, or dispatch

`conversation_orchestration_service` exposes a read-only planning preparation step that validates owner/thread/version and selects compact thread context without appending a turn. It does not resolve references, rank candidate entities, or reject ambiguity. The planner call occurs outside a database transaction. Submission then reopens the authoritative thread, requires the original expected version, validates the planner-selected entities for existence and access, persists the turn using the validated plan, and dispatches the selected capability. This prevents a slow model call from holding row locks and makes concurrent state changes fail with the existing optimistic conflict.

The context builder emits uniform entity facts with source provenance from the structured request, thread record, stored state, turn snapshots, evidence, and entity index without exposing the source table's conversational labels. The planner selects zero, one, or two entities and may clarify. Every selected entity is validated after planning against supported types, PostgreSQL existence, ownership, and RBAC before execution context is constructed.

### One strict plan proposal, one bounded repair, deterministic authority

The model produces a strict proposal containing only: `current_turn_intent`, `relationship_to_prior_turn`, `resolved_entities`, `evidence_sufficiency`, `required_evidence`, `proposed_strategy`, `proposed_capability`, `proposed_tool_categories`, `evidence_requirements`, `artifact_type`, `clarification_question`, `reasoning_summary`, and `confidence`. `evidence_requirements` expresses bounded semantic constraints, not a query: severity, alert type, source or destination IP, hostname, username, time window, sort, and limit. The server validates schema, cross-field compatibility, entity existence/access, tool compatibility, and immutable read-only safety. Text is parsed as one JSON object; arbitrary objects are never executed or stringified into analyst output.

Validation enforces enumerated actions, relationships, strategies, capabilities, strategy/tool/evidence relationships, one approved read-tool category at most, entity shape and count, owner/namespace boundaries, filter value bounds, size limits, and preview-only artifact safety. It never parses the analyst's sentence to decide whether the model selected the right entity, action, or filter. An invalid first result receives one repair request containing only bounded validation errors and the original compact packet. A second invalid result, timeout, or provider failure returns a concise planner-unavailable response and preserves prior state. It never invokes the prior workflow as fallback.

### Planner contract ownership

| Field | Owner | Reason |
|---|---|---|
| `current_turn_intent` | Model | Interpreting the analyst's present objective requires semantic reasoning. |
| `evidence_sufficiency` | Model | Assessing whether current evidence can answer the question is a reasoning decision constrained by freshness metadata. |
| `required_evidence` | Model | Identifying the missing information is part of investigation planning. |
| `proposed_strategy` | Model | Selecting the bounded analytical approach is the planner's central responsibility. |
| `proposed_tool_categories` | Model | Choosing one approved evidence category, when lookup is needed, follows from the evidence gap. |
| `evidence_requirements` | Model proposes; server validates and translates | Identifying semantic evidence constraints requires reasoning, while accepted keys, scalar types, bounds, category compatibility, and tool arguments are server policy. The model never supplies SQL or backend query syntax. |
| `clarification_question` | Model | A concise semantic clarification is selected by the planner when bounded authoritative context does not support one safe interpretation. |
| `reasoning_summary` | Model | Records why the strategy and evidence decision fit the current turn. |
| `stopping_condition` | Server-derived from validated strategy | The bounded strategy contract already determines its terminal condition; asking the model to restate it adds no reasoning value. |
| `confidence` | Model | Expresses confidence in the reasoning proposal, not confidence in authoritative identity. |
| `resolved_entities` | Model selects; server validates | Reference resolution and comparison membership require interpreting the current turn; the server verifies shape, existence, ownership, and access after selection. |
| `relationship_to_prior_turn` | Model | Continuation, topic switch, comparison, and return-to-prior-focus are natural-language interpretations. |
| `proposed_capability` | Model selects; server validates | Capability choice follows interpreted intent; the server enforces the strategy/capability allowlist. |
| `artifact_type` | Model selects; server validates | Natural artifact wording is interpreted by the planner; the server accepts only registry-backed draft types. |
| `referenced_turn_sequence` | Model selects for corrections; server validates | Selecting which prior inference is corrected is reference interpretation; the server verifies the sequence identifies an owned assistant inference and matches the selected entity. |
| `read_only` / `mutation_allowed` | Server | Safety policy is immutable application authority, never a model choice. |
| Profile, model, provider, lifecycle, workflow request, and execution metadata | Server | These are observed application/runtime facts and are not part of planner reasoning. |

The compiled plan remains the internal/downstream contract, so execution and audit metadata retain the complete shape without asking the model to reproduce known values. A later optimistic-concurrency alignment check still compares compiled entities with the current resolved execution context before dispatch.

Current explicit shortcut intent is a non-authoritative hint. When the planner provider is unavailable, an explicit current-turn shortcut may continue through its existing safe capability because it is a user action on this turn, not inherited history; `workflow:auto` fails safely without keyword routing.

### Planner packet is fit by construction

The packet uses the current message plus bounded facts: uniformly represented entities with source provenance, recent turn records, recent evidence/tool results, the stored conversation summary, conclusions, unresolved questions, corrections, capabilities/read-tool categories, safety boundaries, and latency/budget class. It does not label a current entity, active focus, primary entity, focus history, preferred reference, correction target, intent, priority, or relationship. Stored text is labeled untrusted data and cannot supply instructions.

Fixed schema/safety/provenance overhead is measured first. Optional fact categories have deterministic item/text limits and are admitted in a documented transport order solely to fit the packet; that order is not semantic ranking. Stale evidence is represented only by identity/freshness metadata and cannot satisfy evidence requirements. The final serialized packet and full prompt are checked before generation; a mandatory-skeleton overflow is a configuration error, not ordinary user overflow. The entire thread and raw tool results are never sent.

### Existing capabilities remain execution authorities

Validated strategies map to current paths: `direct_answer` and `quick_evidence_lookup` to Quick Explain, `bounded_investigation` and `compare_entities` to Deep Investigate, `decision_support` to Decision Support, and `artifact_draft` to Generate Artifact. Clarification and boundary plans create assistant turns without model/tool workflow execution. One planner-selected tool category is translated into bounded execution context; the existing workflow implementation and SOC tool allowlists remain authoritative.

`workflow_orchestrator` receives the validated capability in server-only planner metadata and does not reclassify it from stale request labels. Response metadata records plan strategy, capability, entities, evidence sufficiency, and whether repair occurred, but not hidden reasoning.

### Evidence requirements survive bounded tool dispatch

A `quick_evidence_lookup` plan must include a non-empty `evidence_requirements` object. The planner may state only the allowlisted scalar requirements supported by its selected evidence category. Unknown keys, invalid IPs or enums, conflicting generic identity fields, time windows beyond seven days, and result limits above ten fail validation before dispatch. Non-lookup strategies must provide an empty object.

The conversation service translates the validated requirements once into the existing SOC read-tool contract. Alert requirements become canonical `search_alerts` arguments; incident, source-IP, event-family, and response-registry requirements map only to their supported existing tools. A requirement that cannot be represented without being discarded fails closed instead of falling back to an unfiltered newest-ten search. Tool validation and RBAC run again at execution, preserving the existing read-only limits. Full workflow context remains separate and is not copied into planner requirements.

### Planner selects task shape, not prose template

The planner's reasoning summary is audit metadata, not the answer. Downstream prompts receive the current intent and strategy so direct lookups answer directly, comparisons compare, evidence requests cite evidence, recommendations lead with the recommendation, and deep investigations retain structured analysis. Existing persona safety and evidence grounding remain. Fact/inference/confidence headings are not forced onto every response.

### Final synthesis consumes a server-authored evidence envelope

Planner-directed Quick Explain synthesis receives a compact envelope containing the current question, semantic response mode, validated strategy and evidence requirements, the actual bounded tool request, result count, selected analyst-facing record fields, truncation/omission state, observation time, provenance, active context, and evidence sufficiency. The envelope is assembled after tool execution from validated server and tool-result objects. It excludes raw database payloads, secrets, implementation routes, and duplicate workflow context, and labels all retrieved text as untrusted data rather than instructions.

The final prompt leads with the current task and requires a direct answer grounded in the envelope. Lookup responses must identify a returned record with a concrete identifier when one exists; evidence questions summarize returned records; source-IP and time-window answers retain those validated constraints; direct thread-state answers use conversation state without generic alert enrichment. Empty results always produce a truthful no-match answer, and truncated results always disclose incompleteness.

Post-generation normalization is deterministic and fail-closed. A tool-backed answer is accepted only if it cites an identifier from the returned evidence and does not introduce an unreturned IP, alert identity, severity claim, or unsupported reputation, authentication, exploitation, or impact claim. Empty, generic, unsupported, or ungrounded model text is replaced with a concise summary composed only from the normalized envelope. This is one semantic response contract over task classes and record fields, not a list of exact user-sentence templates.

### One final-synthesis builder owns the complete prompt budget

The active workflow profile's `max_prompt_chars` applies to the fully serialized synthesis prompt, not independently to conversation memory, SIEM context, evidence, and persona sections. The synthesis builder first serializes mandatory policy, the complete current question, validated task, authoritative active entity, query parameters, one concrete result when present, zero-result/truncation/observation/provenance state, and grounding/read-only instructions. It then admits optional corrections, same-entity conclusion, unresolved question, thread summary, older turns, additional result records, and compact SIEM context in that priority order only while the complete prompt remains within the profile ceiling. Tool-backed prompts do not repeat the same result records inside generic SIEM context.

The builder measures the final joined prompt after every admission and before gateway generation. If mandatory synthesis cannot fit, a successful lookup bypasses model generation and returns the existing task-aware deterministic answer from the full server-owned evidence envelope, with explicit degraded-synthesis metadata. Empty successful results retain their validated filters. Verified evidence therefore cannot be replaced by a generic context-too-large error. Requests without successful evidence retain the existing fail-closed insufficient-context behavior.

### Current-turn language interpretation is exclusively planner-owned

The planner classifies the current turn into one bounded semantic action: `state_summary`, `fresh_evidence_lookup`, `evidence_explanation`, `decision_support`, `artifact_draft`, `comparison`, `bounded_investigation`, `clarification`, or `unsupported`. It also chooses the prior-turn relationship, resolved entities, capability, evidence requirements, artifact type, or clarification. The server validates their enumerated and cross-field compatibility without independently interpreting the current message.

The first syntactically valid action classification is preserved across the single repair attempt. Repair may correct schema and cross-field defects but cannot change the requested action. `clarification_question` is conditionally model-owned only for `clarification_required`; it may be omitted otherwise. `reasoning_summary` remains required audit reasoning. `stopping_condition` is derived from the validated strategy because the bounded capability already defines its execution stop. Planner confidence is optional descriptive metadata; when absent the server records `unknown`, never an invented positive confidence.

### Entity and filter interpretation is planner-owned; authority remains server-owned

The context builder exposes uniform entity facts from structured request identity, thread records, stored state, completed turn snapshots, fresh verified evidence, and the entity index. It preserves source provenance but does not expose focus, primary, preferred, comparison, or reference-selection labels and does not rank or select entities. Evidence entities are extracted only from structured snapshots and fingerprints, never arbitrary assistant prose. The planner resolves references or returns clarification.

Every accepted evidence requirement records `planner_interpreted` provenance. The server validates only key allowlists, scalar types, IP/hostname/username syntax, bounds, selected-entity access, tool compatibility, and read-only policy. It does not parse the user's sentence to confirm a severity, duration, sort, entity, or alert family. The planner prompt requires fresh lookups not to inherit unrelated prior constraints; semantic correctness is evaluated through paraphrase and production acceptance rather than duplicated backend language rules.

### Provider capabilities and original workflow boundaries are pre-dispatch contracts

Every capability emitted by an application service must be registered explicitly by the intended provider. The local Ollama provider advertises `agentic_analyst_planning`; the gateway continues to reject every unadvertised capability before generation. Contract tests exercise the real gateway/provider boundary and prove that a planner request reaches Ollama generation while paid fallback remains unavailable for the local-only planning profile.

The original workflow value from the SIEM conversation request is validated before context selection, planner generation, repair, classification, or degraded shortcut fallback. `auto` and the four SIEM conversation capabilities are allowed. Repo Assistant and SOC Briefing are rejected as isolated namespaces, and unknown workflow names are rejected as unsupported. The validated plan is checked again after planning, but no transformed workflow may erase an explicit original boundary violation.

### Planner uses a dedicated local 8B profile

The planner requests the approved `agentic_planning` profile through the profile registry and gateway for both its initial proposal and its single repair attempt. The profile defaults to `llama3.1:8b`, is local-only, disables paid fallback, and owns an 8,000-character prompt budget, 1,024-token output budget, 90-second timeout, and low deterministic temperature. Provider response metadata records the selected profile and model.

`fast_triage` remains assigned to Quick Explain and other existing short-triage paths with `llama3.2:3b`; Guided Analysis, Deep Briefing, and Developer Assistant retain their existing assignments. Planner prompt instructions make strategy/capability/tool relationships explicit, but deterministic validation remains authoritative and performs no intent-changing correction. At most one model repair remains permitted.

### Language-understanding boundary cleanup

The pre-planner reference resolver, pronoun/continuation/comparison regexes, candidate ranking, deterministic ambiguity responses, sentence-derived filter extraction, and natural-language artifact-type matching are removed. The context builder may normalize structured identifiers and preserve chronological/provenance labels, but it cannot inspect the current sentence to select an entity, intent, relationship, filter, capability, or clarification.

#### Architectural principle: unrestricted language over facts

The planner is not expected to recognize a predefined set of analyst phrases. It is expected to understand unrestricted natural language using a bounded packet of authoritative facts. Production scenarios and paraphrase matrices verify this boundary; they are never implementation targets, routing inputs, or a source for phrase-specific server behavior.

The context packet is a pure fact packet. It contains recorded entities with provenance, recent tool/evidence results, the stored conversation summary, recorded conclusions, unresolved questions, corrections, recommendations, statements, and recent turns. It does not label any entity as active, primary, preferred, historical focus, or correction target, and it does not encode intent, priority, meaning, or conversational relationships. Ordering and omission exist only for deterministic transport bounds and provenance/recency retention, never as a statement of semantic importance.

#### Permanent future regression rule

If a future natural phrasing fails and a proposed fix adds deterministic conversational logic, the implementation is presumed architecturally incorrect until proven otherwise. Fix the planner boundary, planner contract, or model capability; do not patch the phrasing with regexes, phrase lists, synonym maps, ranking rules, routing rules, or special cases.

#### Model-agnostic server invariant

The server contract is independent of any particular LLM's reasoning style, wording, reference strategy, or language interpretation. Replacing the planner model may change model configuration and measured capability, but it must require no conversational server-code changes. The server accepts only the stable structured plan contract and validates authoritative facts and safety policy.

| Failure class | Invariant | Enforcement location | Planner responsibility | Variants tested |
|---|---|---|---|---|
| Natural turn blocked before planning | Every eligible, owner-valid SIEM turn reaches planner generation | Conversation planning entry point | Interpret or clarify | Pronoun, ellipsis, comparison, topic switch |
| Server chooses a referent | No pre-planner selected entity or ambiguity status exists | Context builder contract | Return resolved entities | Active, primary, prior turn, evidence, history |
| New phrasing requires backend rules | No phrase list, language regex, synonym map, or ranking heuristic participates in planning | Source regression tests | Generalize semantically | Three materially different phrasings per scenario |
| Planner invents or accesses an entity | Selected entities are validated after planning for type, existence, ownership, and RBAC | Conversation orchestration submission transaction | Select only contextual or explicit entities | Missing, deleted, cross-owner, literal IP |
| Planner cannot resolve ambiguity | Clarification is a valid planner action with no execution | Plan validator and non-executing turn persistence | Ask a concise question | Two alerts, two IPs, unclear ellipsis |
| Capability disagrees with intent | Model-selected action, strategy, and capability must satisfy an enumerated compatibility contract | Plan validator | Choose all three consistently | Advice, artifact, lookup, compare, investigate |
| Filter language is reinterpreted by server | Server validates filter syntax/bounds/tool compatibility only | Evidence requirement validator | Translate the current request into semantic filters | Severity, time, sort, literal entity, no constraint |
| Artifact wording is parsed by server | Planner selects a registry-backed artifact type or clarifies | Plan validator and artifact dispatch | Interpret draft intent | Checklist, escalation, incident note, ambiguous artifact |

## Failure-Class Table

| Failure class | General invariant | Deterministic enforcement location | Model responsibility | Variants tested |
|---|---|---|---|---|
| New question trapped in prior workflow | Every eligible current turn is planned independently; prior workflow is context only | Conversation submission and dispatch | Classify current relationship/intent | Lookup, topic switch, evidence-gap request |
| Same intent phrased differently | Plan contract is semantic, not an exact-sentence router | Planner prompt/evaluation suite | Return equivalent strategy | Three phrasings for ten intent classes |
| No tool despite missing evidence | Insufficient evidence requires one approved lookup, investigation, or clarification | Plan validator | Identify required evidence | No/partial/stale evidence |
| Tool despite sufficient evidence | Direct answer forbids tool categories | Plan validator | Assess sufficiency | Existing current evidence, prior conclusion |
| Forbidden tool/capability | Only mapped capabilities and approved read categories pass | Plan validator/dispatch | Propose within boundary | Mutation, Repo, SOC, unknown tool |
| Wrong or switched entity | Planner-selected entities must exist, be accessible, and match the execution payload; semantic selection remains model-owned | Post-plan entity/RBAC validator and execution alignment validator | Select the intended context entity or clarify | Explicit switch, stale focus, return to prior entity, invented identity |
| Ambiguity answered | Only a planner clarification plan may stop for semantic ambiguity; the server never chooses among candidates | Plan schema/cross-field validator | Ask concise clarification | Multiple IPs/alerts, missing referent, ellipsis |
| Stale evidence treated as current | Stale evidence cannot satisfy evidence sufficiency | Packet builder/validator | Request refresh or qualify | Expired and mixed-freshness evidence |
| User claim or inference promoted to fact | Assertion provenance is immutable in packet and plan | Context builder/validator | Treat claims as statements/inferences | Scanner, owned IP, service account |
| Invalid or repaired-invalid schema | Exactly one repair; then fail closed without sticky fallback | Parser/validator/planner service | Produce/repair strict JSON | Missing fields, bad enum, malformed JSON |
| Plan/prompt over budget | Mandatory packet fits; optional content compacts; final sizes checked against the dedicated planner profile | Packet/prompt builder and `agentic_planning` profile | Stay within output contract | Production-sized thread/evidence/entity state, initial and repair prompts |
| Planner assigned an undersized or shared workflow model | Planner always selects its dedicated local-only 8B profile; other workflow assignments remain unchanged | Profile registry, config, planner request, provider metadata tests | Satisfy the existing plan contract | Initial plan, repair, Quick Explain regression, all profile inventory defaults |
| Deterministic metadata causes otherwise useful plan rejection | Model emits reasoning fields only; server-owned fields are compiled from authoritative state or strategy mapping | Strict proposal parser and plan compiler | Return exactly the reasoning proposal | Omitted deterministic fields, attempted overrides, full compiled metadata |
| Evidence filters collapse before tool execution | Every accepted semantic requirement is validated, translated, and present in the one bounded read request, or dispatch fails closed | Plan validator, conversation tool-request translator, SOC tool validator/executor | State only allowlisted scalar evidence requirements; never generate query syntax | Severity, alert type, source/destination IP, hostname, username, time window, sort, limit, unknown and unsupported filters |
| Correct evidence is ignored by synthesis | A successful tool-backed answer cites at least one concrete returned identifier or is replaced by deterministic evidence prose | Evidence-envelope builder and final response normalizer | Answer the current task using only envelope data | Latest alert, filtered alert, source IP, evidence request |
| State summary over-triggers on a fresh lookup | `fresh_evidence_lookup` is compatible only with `quick_evidence_lookup`; thread state cannot authorize `direct_answer` | Plan action/strategy validator | Classify the current requested action | Known IP lookup, repeat search, newer activity |
| State summary under-triggers on an actual state question | `state_summary` uses `direct_answer` when authoritative state is answerable and never requests a SOC tool | Plan validator and dispatch | Recognize a state-summary action | Current investigation, current position, state recap |
| Decision Support or artifact is swallowed by direct answer | Recommendation and artifact actions map only to their dedicated strategy/capability | Plan action/strategy validator | Distinguish advice and drafting requests | Block/monitor, escalation, checklist, note, summary |
| Active, primary, or prior evidence entity is unavailable to a typed pronoun | All authoritative entity sources are labeled in the bounded packet without server selection | Context builder and post-plan entity validator | Resolve the intended entity or clarify | `this IP`, `this alert`, primary alert, latest evidence IP |
| Spurious or stale filter narrows a fresh lookup | Filters remain model-interpreted but must pass strict type, bound, entity-access, and tool-compatibility validation | Plan requirement validator | Propose only constraints supported by the current turn and context | Invented window, stale severity/type, literal IP |
| Planner omits nonessential metadata | Conditional clarification, strategy-derived stopping, and server-owned unknown confidence do not invalidate safe reasoning | Proposal parser and plan compiler | Supply action, strategy, sufficiency, evidence need, and reasoning | Missing confidence, clarification, stopping field |
| Repair changes action or drops valid semantics | The first valid action enum is pinned for repair; repaired output must match it | Planner repair prompt and validator | Correct only reported defects | Missing field, contradictory strategy, unsupported filter |
| Capability and persisted execution metadata disagree | Strategy-capability mapping, execution payload, turn metadata, and entity alignment are checked from one compiled plan | Plan compiler, dispatch alignment, turn serializer | Choose a valid action/strategy | Quick lookup, decision, artifact, comparison, investigation |
| Different evidence produces the same canned answer | Analyst-facing output is validated against and, when necessary, composed from the current result records | Final response normalizer | Select relevant current evidence | Different IDs, IPs, types, timestamps, and empty results |
| Answer invents evidence or unrelated enrichment | Unreturned technical identifiers and unsupported reputation/authentication/impact claims invalidate model synthesis | Grounding validator | Make no claim absent from the envelope | AbuseIPDB, successful login, compromise, exploitation, foreign IP |
| Empty results presented as findings | Zero-result successful lookups always render a no-match response from validated query parameters | Deterministic evidence composer | None | Empty alert, source-IP, and time-window lookups |
| Old evidence presented inside a recent window | Tool query enforces the window and synthesis receives only returned records plus the validated duration | Tool executor and evidence envelope | Describe only envelope records | One-hour match, older exclusion, no match |
| Evidence request repeats a conclusion | Evidence-oriented synthesis enumerates or summarizes returned records instead of reusing prior prose | Task-aware prompt and grounding normalizer | Explain observed records | One and multiple records |
| Source-IP lookup omits requested IP | Source-IP response mode requires the validated IP to appear in accepted or deterministic output | Evidence-envelope builder and grounding validator | Name the scoped IP | Match and no-match |
| Current-alert lookup omits alert identity | Alert lookup with a returned ID requires that identity in the final answer | Grounding validator | Lead with matching alert | Latest HIGH and alert-family lookup |
| State question uses alert template | Direct-answer plans with no tool evidence prioritize current thread state and omit generic alert examples | Prompt construction | Summarize current state | Active investigation, unresolved questions |
| Stale workflow template overrides current task | Planner task and evidence envelope precede persona style; canned Quick Explain examples are not included | Explainer prompt construction | Follow current task | Lookup after explanation, evidence after conclusion |
| Truncated evidence presented as complete | Truncation and omission metadata are preserved and must be disclosed | Evidence envelope and response normalizer | Qualify incomplete results | Tool and prompt compaction |
| Timeout/provider failure | Preserve prior state and return planner unavailable; no old dispatch | Planner service/orchestration | None after failure | Timeout, disabled, provider error |
| Repeated ineffective strategy/answer | Current intent and strategy are recorded; identical prior answer is not reused as current response | Planner validation/response metadata | Select current task | New lookup after explain; topic switch |
| Workflow label used as content | Previous/current labels are typed hints, never analyst evidence or prompt instructions | Packet builder | Weigh current hint only | Auto after Quick Explain/Decision Support |
| Repo/SOC/mutation boundary bypass | Ineligible namespace/action returns boundary plan, never SIEM dispatch | Route/orchestration/validator | Identify unsupported boundary | Repo query, briefing continuation, apply request |
| Application capability rejected before generation | Every emitted capability is explicitly advertised by its intended provider; unadvertised capabilities remain fail-closed | Provider capability declaration and gateway contract tests | None | Planner capability accepted by Ollama; arbitrary capability rejected |
| Original forbidden workflow erased by classification/fallback | Validate the original requested workflow before planning or fallback and retain it as authoritative boundary input | Conversation orchestration entry point and defensive post-plan validation | May identify textual boundary requests, but cannot override explicit workflow | Repo Assistant, SOC Briefing, unknown workflow, unavailable/malformed planner, working planner reclassification |
| Independently bounded sections overflow final synthesis | One builder measures fixed overhead first and admits every optional section against the complete serialized prompt | Explainer synthesis prompt builder | None | Quick Explain, Decision Support, three results, long thread, exact-limit stress |
| Optional history displaces evidence | Question, task, entity, filters, one result or zero-result state, truncation, provenance, and safety precede all optional state | Synthesis section priority and admission checks | None | Corrections, conclusions, unresolved questions, summary, old turns, extra results |
| Successful evidence is lost on mandatory overflow | Successful reads always have a task-aware deterministic envelope-derived answer even when model synthesis cannot run | Explainer service pre-generation fallback | None | Alert lookup, evidence request, source IP, no match, truncated result |
| Intermediate fit passes but final prompt exceeds profile | Only the final joined prompt measurement authorizes gateway generation | Explainer service immediately before gateway call | None | Fixed persona/task overhead and optional section combinations |
| Contradictory repair output executes | Repair feedback names exact schema and cross-field violations; the one repaired proposal still passes the unchanged validator | Planner repair prompt and plan validator | Correct all reported violations in one repair | Object `required_evidence`, direct answer plus insufficient evidence, missing clarification, invalid sort |
| State-summary question invokes an unnecessary read | Fresh authoritative thread state supports `direct_answer` with no tool category | Planner prompt and unchanged strategy validator | Recognize state-summary intent and sufficiency | Active focus, current conclusion, unresolved questions |
| Artifact dispatch lacks a bounded draft type | A structured shortcut type is preserved; otherwise the planner selects one registry-backed type or clarifies | Conversation dispatch and artifact registry | Interpret artifact wording and select a bounded type | Shortcut type, unambiguous note/checklist/escalation request, ambiguous draft |

## Transaction and Concurrency Boundaries

1. Planning snapshot: owner-scoped read validates thread and expected version and constructs bounded authoritative context; it does not resolve or validate a model-selected entity before generation.
2. Planner generation: local-only gateway call and optional one repair; no database transaction.
3. Submission: existing owner thread lock revalidates version, validates every planner-selected entity for existence/access, persists the validated plan with the queued turn, and atomically creates/links async work.
4. Execution/completion: existing worker role revalidation, version guards, response normalization, and turn/state transactions remain authoritative.

## Risks / Trade-offs

- [The dedicated 8B local model may still fail cross-field validation] -> Keep deterministic validation and one repair, measure real-model runs after deployment, and stop before Spec 2 if the valid-plan rate remains weak.
- [A planner call adds latency] -> Use the dedicated bounded planning profile and compact packet; preserve explicit latency metadata and timeout handling.
- [Existing capabilities cannot execute every ideal plan] -> Validate only Spec 1 mappings and at most one bounded evidence category; defer iterative plans and complete capability conversion.
- [Two-phase planning can race with another tab] -> Require the planning snapshot's expected version at submission and replan after the client reloads.
- [Direct answer may still be stylistically repetitive downstream] -> Pass task shape without imposing prose; broader capability response conversion remains Spec 3.
- [The 3B synthesis model may still ignore evidence] -> Validate grounding after generation and use only a deterministic envelope-derived summary when model prose fails; production acceptance still measures the deployed model path.
- [Natural alert-family wording does not map to one canonical alert type] -> Keep exact validated `alert_type` support and defer a bounded family taxonomy; the current repository has multiple distinct brute-force/password-spray/credential-stuffing identifiers, so no phrase alias is silently translated or discarded.

## Migration Plan

No database migration or persistent runtime configuration edit is required because the dedicated profile has a source-owned default. Deploy later only after an approved commit and the documented Mac-to-VM process. Rollback restores the prior source commit; thread records remain valid and no stored plan is treated as evidence.

## Open Questions

The verified 3B model does not meet the planner contract. The dedicated 8B profile is an implementation correction based on measured local-model evidence, but its production valid-plan rate remains a deployment acceptance question. Failure after one repair is reported as a model capability limitation and does not authorize validator weakening or Spec 2 work.
