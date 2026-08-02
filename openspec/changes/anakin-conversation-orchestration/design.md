## Context

Commit `ddc4f33` provides owner-scoped SIEM threads, immutable ordered turns, derived state, entities, hypotheses, bounded evidence, reset/expiry, optimistic versions, idempotent client request IDs, and nullable owner-safe async links. Focused PostgreSQL validation confirms those behaviors. The canonical orchestrator still builds every prompt only from the current request, while async requests store independent payloads and workers authenticate from a queued role snapshot. Existing prompt builders independently allocate SIEM/tool context within profile limits.

Conversation context must enter once at the canonical orchestration boundary, before Quick Explain, Deep Investigate, Decision Support, or Generate Artifact dispatch. Repo Assistant bypasses that boundary through its dedicated worker branch, and SOC Briefing uses a separate scheduled engine; both remain isolated.

## Goals / Non-Goals

**Goals:**

- Make participating SIEM workflows consume an authoritative PostgreSQL thread and produce ordered durable turns.
- Resolve common follow-up references deterministically and return clarification without model invocation when resolution is unsafe.
- Build an explicitly untrusted, provenance-aware context packet from state, entities, bounded recent turns, fresh evidence, corrections, and unresolved questions.
- Reserve a deterministic conversation budget before workflow-specific prompt assembly and report compaction/omission metadata.
- Serialize generation per thread, link async requests atomically, preserve terminal idempotency, and reject stale worker completions.
- Restore turns and async lifecycle after refresh without browser-owned authoritative history.

**Non-Goals:**

- Long-term memory, embeddings, vector search, RAG, learning, model/profile changes, new SOC tools, autonomous actions, or broad frontend redesign.
- Conversation memory for Repo Assistant or SOC Briefing.
- Automatic Analyst Workspace writes or artifact apply/confirm behavior.

## Decisions

### Conversation metadata is an optional canonical workflow envelope

Participating requests may include `conversation` with `thread_id`, `expected_version`, and `client_request_id`. Stateless requests remain compatible. The backend validates ownership and target access; browser-provided history, summaries, resolved references, and evidence are ignored.

Alternative: add a parallel conversation generation endpoint. Rejected because it would duplicate routing, safety, prompt, and async lifecycle logic.

### One orchestration service owns turn and request transitions

The service transactionally appends a queued user turn and, for async workflows, creates/gets and links the workflow request. Explicit idempotency resolves terminal as well as active requests. Quick Explain uses the same queued-turn serialization around synchronous generation. Generation never occurs inside a database transaction.

Workers revalidate the current user and role, load conversation context from PostgreSQL, execute the canonical workflow, then atomically persist the assistant turn, update derived state, and close the user turn only if the submission thread version is still current. Failures terminalize the user turn without inventing an assistant answer. Retry reuses the linked request/turn.

Alternative: write turns before and after existing queue calls in separate transactions. Rejected because a crash could orphan either side or link the wrong request.

### Deterministic resolver returns resolved, clarification, or command state

Resolution uses normalized thread entities, focus state, turn entity snapshots, corrections, and unresolved questions. It recognizes intent classes rather than fixed incident examples: continuation, explanation, comparison, prior focus, correction, reset, and generic pronoun/entity references. A unique candidate resolves; multiple credible candidates return a structured clarification; absent support returns unresolved and never guesses. "Go back" selects the previous distinct focus, and entity switching updates focus only after canonical target validation.

Model inference is not used to decide whether a reference is resolvable.

### Context selection is provenance-first and budget-reserved

The selector receives the selected profile limit and allocates a bounded fraction to conversation context while leaving fixed headroom for persona, current SIEM context, tools, schemas, and output instructions. Selection order is: current corrections, active entity/focus, fresh verified evidence, unresolved questions, compact summary, prior conclusions/recommendations, then newest complete turn pairs. Generate Artifact consumes the same structured state/evidence packet but excludes conversational filler.

If content does not fit, deterministic compaction drops lowest-priority items and emits included/omitted counts and reasons. It never slices serialized JSON or silently truncates. A corrupt summary is ignored and state is rebuilt from authoritative bounded turns/evidence. If the minimum safe packet cannot fit, the request fails before model invocation with `conversation_context_too_large`.

Stored content is wrapped as untrusted analyst/assistant data and prompt policy states it cannot override system, safety, tool, workflow, or artifact instructions.

### Production correction: packet construction is fit-by-construction

The packet builder first serializes a mandatory skeleton containing the resolved primary entity, compact reference status, provenance markers, and final bounds fields. That measured fixed size includes the bookkeeping that will be returned. Optional categories are then admitted in this order: corrections, one current unresolved question, compact conclusions, fresh evidence, recommendations, recent relevant turns, analyst statements, and secondary entities. Every category has deterministic item, text, and category limits.

When an optional item does not fit, the builder retries its compact representation and otherwise omits the whole item while incrementing the reserved omission counter. Lower-priority categories are never allowed to displace the current resolved entity. The final packet is serialized again after all measurements are populated. A mandatory skeleton overflow is an internal configuration defect with measured required and available sizes; ordinary thread content is compacted and cannot cause that error. Conversation or workflow profile budgets are not increased.

### Production correction: one resolved execution context owns entity identity

The orchestration service constructs one normalized resolved execution context after validating the current request and thread. Entity precedence is: explicit validated request entity, deterministically resolved reference, existing active focus, then clarification. This object owns the active entity, comparison entities, bound conclusion/unresolved item, normalized context type, workflow identifiers (`alert_id`, `incident_id`, `source_ip`, host/entity identity, and investigation identity), and entity snapshot.

The same object is used to append the user turn, update focus, build conversation metadata, and rewrite the server-side workflow payload before model or tool execution. A final invariant check rejects execution when thread entity, workflow payload entity, and response metadata entity disagree. Inferred references may enrich an explicit entity but cannot replace it.

### Production correction: Deep Investigate terminal output is schema-tolerant

Deep Investigate completion classifies the canonical result as full success, usable partial/degraded output, terminal provider/tool failure, or malformed/no-content output. Assistant prose is composed only from validated scalar/list fields already present in the investigation contract: summary or assessment, correlated evidence/findings, hypotheses and contradictions, evidence gaps, confidence, and prioritized next steps. Arbitrary objects are never stringified.

Usable partial output produces a completed assistant turn whose structured payload records `partial` or `degraded`, missing sections, and available provider/error status. It does not claim full success. A terminal failure or malformed result creates no assistant inference and does not update prior thread conclusions.

## Production Correction Failure Matrix

| Failure class | Invariant | Enforcement location | General variants tested |
|---|---|---|---|
| Packet overflow after selection | Final bookkeeping is reserved and every returned packet is reserialized at or below its assigned budget | `conversation_context._build_packet` | Empty, first, second, eight-turn, multi-entity, correction/evidence, and all workflow budgets |
| Explicit entity displaced by pronoun | Valid current-request identity always outranks inferred references | `conversation_orchestration_service._resolve_execution_context` | Explicit alert switch with generic pronoun; explicit source/incident identity |
| Resolved focus differs from execution | One resolved context rewrites turn snapshot, workflow payload, and response metadata; mismatch fails closed | Submission and worker preparation in `conversation_orchestration_service` | Go back, why/evidence, one/many IPs, continue, compare |
| Usable degraded result rejected | Semantic terminal normalizer accepts supported useful fields without fabricating or stringifying | `conversation_orchestration_service` completion normalization | Full, structured-only, partial/degraded, provider failure, malformed output |

### Existing prompt builders accept a separately bounded conversation block

The orchestrator injects a server-built `conversation_context` packet. Explain, investigation, and drafting builders render it in a labeled untrusted-data section and include its serialized size in their current budget calculations. They never discover or query thread data independently.

### PostgreSQL remains authoritative for recovery

Thread reads include active linked async request status so refresh can recover conversation and progress using thread/request IDs. Minimal React plumbing may retain only a thread identifier per entity scope and re-resolve it from the server; it never stores authoritative turns or summaries. No visual redesign is included.

### Workflow boundaries are allowlisted

Quick Explain, Ask Anakin auto-routing, Deep Investigate, and Decision Support both consume and produce conversation state. Generate Artifact consumes state and records only a preview-labeled assistant turn. Repo Assistant and SOC Briefing reject conversation metadata. Legacy endpoints remain stateless in this phase to avoid silently joining unrelated histories.

## Invariant Ownership

| Invariant | Database/store | Orchestration/service |
|---|---|---|
| One generation per thread | Partial unique queued/running turn index; row lock | Every conversational workflow first creates a queued user turn |
| Retry returns original work | Unique owner/thread/client request and turn link | Resolve linked active or terminal request before version checks |
| Ordered completion | Immutable sequence and submission version | Assistant append and user terminal transition share one locked transaction |
| Owner isolation | Composite owner foreign keys | Owner predicates and current-user validation on every load |
| Prompt boundaries | No cross-domain thread schema | Workflow allowlist; reject Repo/SOC metadata |
| Provenance | Assertion/evidence constraints | Selector labels every item and never promotes user claims |
| Artifact safety | Artifact cross-column check | Generate Artifact forces preview labels |
| Budget | N/A | Deterministic allocation, whole-item compaction, explicit metadata |

## Failure-Class Handling

| Failure class | Deterministic result |
|---|---|
| Ambiguous reference / multiple entities | `clarification_required`; no model call or focus mutation |
| Missing reference/evidence | Unresolved response identifying what is missing; no guessed fact |
| Stale version / two tabs | `409`; caller reloads authoritative thread |
| Duplicate submission / worker retry | Original turn and linked request/result returned |
| Deleted/inaccessible entity | Target-unavailable conflict; no substitution |
| Expired/reset/closed thread | Existing `410`/conflict lifecycle behavior; no context injection |
| Failed generation | User turn becomes failed; no assistant inference/state mutation |
| Out-of-order completion | Submission-version guard rejects completion and state overwrite |
| Corrupt/missing summary or state | Ignore derived data, rebuild bounded packet from turns/evidence, mark rebuild metadata |
| Oversized prompt | Whole-item compaction with metadata; fail before generation if minimum packet cannot fit |
| Stale evidence | Exclude from verified-current evidence and label as stale context only when needed |
| Entity switch/go back | Validate canonical target, then update ordered focus; otherwise preserve current focus |
| User correction | Store as correction; suppress superseded inference in selected conclusions, never alter evidence |
| Prompt injection in memory | Sanitize at rest and frame retrieved text as untrusted data beneath immutable policy |
| Role loss/disabled user | Worker revalidates current account before tools/model; request fails closed |
| Cross-namespace request | Repo/SOC conversation metadata rejected before persistence or generation |

## Transaction Boundaries

1. Submission transaction: lock owner thread, resolve duplicate, validate target/version/reference, append queued user turn, create/link async request when applicable, commit.
2. Generation phase: load a versioned context snapshot, release all database locks, execute existing read-only context/tools/model path.
3. Completion transaction: lock owner thread and linked turn, verify submission version/current active execution, append assistant turn, terminalize user turn, update state/entities/summary metadata, commit.
4. Failure transaction: terminalize only the linked user turn/request under owner and lease guards; preserve prior state.

## Risks / Trade-offs

- [Heuristic references cannot resolve every natural phrase] -> Return clarification rather than widening model authority; extend intent classes with regression tests.
- [Existing builders have separate budget formulas] -> Central packet declares a hard maximum and builders subtract actual packet size before allocating SIEM/tool context.
- [Long-running async evidence can become stale] -> Record selection time and evidence freshness; workers rebuild the packet at execution and completion rejects stale versions.
- [Minimal frontend plumbing does not provide a full chat redesign] -> Preserve existing response panel and polling while exposing durable turns/recovery for a later focused UI change.
- [Summary generation without another model call is less fluent] -> Use deterministic bounded extraction from completed turns; model-driven summarization remains deferred.

## Migration Plan

1. Add migration `0034` only for orchestration-specific uniqueness/index or linkage metadata that cannot be enforced by `0033`.
2. Deploy later using the documented migration helper after explicit commit/push/deployment authorization.
3. Existing stateless workflow requests remain valid; conversational fields are optional.
4. Rollback disables conversation envelope handling first. Preserve thread/turn history and use a forward migration rather than deleting conversation records.

## Open Questions

None. Full conversational UI, explicit New Thread controls, long-term memory, and production cleanup scheduling remain dependent work.
