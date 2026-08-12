## Context

The agentic planner already separates model-owned language interpretation from backend-owned validation and permits exactly one repair. Its current contract is distributed across prompt prose, `planner_output_schema()`, semantic constants, and handwritten validators. That distribution has drifted: the prompt under-describes required arrays, conditional fields, scalar formats, bounds, and entity binding. Validation returns strings, repair infers preservation by searching those strings, and the Anthropic adapter concatenates text while discarding `stop_reason`. Consequently, output exhaustion can enter ordinary parsing and different reliability failures collapse into generic planner errors.

The Mac repository is the only implementation source. This change must preserve planner-owned interpretation, strict safety validation, one repair, paid accounting, provider routing, entity-bound evidence lookup, and compact conversation persistence. It must make no real provider calls, VM changes, deployment, commit, or push.

## Goals / Non-Goals

**Goals:**

- Make one serializable planner contract authoritative for model instructions and validation-oriented tests.
- Classify provider completion before parsing, with deterministic safe extraction of Anthropic text blocks and no thinking exposure.
- Return bounded structured validation errors and use explicit validated-field state for repair preservation.
- Retain enough sanitized attempt metadata to distinguish initial/repair completion and validation failures.
- Add deterministic offline coverage and acceptance fixtures for success, repair, failure, and truncation.

**Non-Goals:**

- Weakening semantic, grounding, entity-binding, capability, artifact, correction, or tool safety rules.
- Adding deterministic interpretation of user language, regex intent parsing, server-side meaning correction, or phrase-specific fixes.
- Changing routing, budget/accounting semantics, output-token ceilings, repair count, request concurrency, workers, RBAC, or approval boundaries.
- Persisting prompts, raw failed plans, hidden reasoning, secrets, or provider authorization data.

## Decisions

### One contract assembled from validator authorities

`planner_output_contract()` will serialize field presence, types, nullability, enums, lengths/list bounds, conditionals, evidence-filter schemas by tool, entity bindings, and action/strategy semantics. Existing constant tables remain the implementation authorities; prompts and tests consume the assembled contract rather than maintaining a second prose schema. Validation continues to execute explicit Python checks because those checks normalize scalar values and enforce cross-field safety, while equivalence tests prove the serialized contract matches those checks.

Alternative: adopt a second JSON Schema validator. Rejected because it would create another independently maintained contract unless the complete validator were rewritten, increasing scope and regression risk.

### Typed bounded validation results

Validation failures use an immutable shape with `stage`, `code`, `path`, and bounded `message`. Stages distinguish `parse`, `schema`, `semantic`, `entity_binding`, and `provider_completion`. At most twelve errors are retained; paths and messages are length-bounded and sanitized. `parse_and_validate_plan()` returns typed errors, and public metadata serializes only their bounded dictionaries.

The validator also returns explicit preservation state for fields proven safe before a later validation stage fails. Repair-stable `current_turn_intent` remains enforced when valid. Other fields are requested for preservation only when their field-level validation and relevant dependencies succeeded; no message substring matching is used.

Alternative: continue string errors plus better wording. Rejected because wording remains an unstable control surface.

### Completion state precedes planner validation

Normalized request metadata gains `provider_completion_state` and `provider_stop_reason`. Anthropic maps a recognized normal stop to `complete`, `max_tokens` to `output_exhausted`, non-exhausted no-text/thinking-only responses to `malformed_no_text`, and transport/provider failures to `provider_error`. Text blocks are selected in response order and joined deterministically; thinking and all other block types are ignored. `max_tokens` remains a normalized successful transport response so paid token accounting can settle normally, but planner orchestration checks completion state before content/validation and returns a typed truncation outcome. The same check applies to repair.

Alternative: map `max_tokens` to a generic provider failure status. Rejected because it would obscure successful transport and token accounting while still losing the precise completion cause.

### One bounded repair with safe proposal inclusion

The repair packet contains the parsed invalid object when available, otherwise a bounded proposal string, typed errors, explicit preserved field values, the same authoritative contract, and bounded authoritative facts. It demands one bare corrected object and undergoes the unchanged full validator. No loop is added; repair exhaustion is terminal.

### Bare JSON only

The parser will reject all code fences, surrounding prose, arrays, multiple objects, and malformed JSON. This matches existing prompt language and the narrow behavior already required by the planner foundation spec.

### Bounded observability and temperature

Planner outcomes retain per-attempt sanitized metadata: stage, provider status/completion state/stop reason, token counts, accounting attempt ID, plan character count, typed validation errors, and whether repair occurred. Compact conversation state keeps only bounded diagnostic fields; logs use the same safe summaries. No raw proposal is persisted.

The Anthropic adapter will continue omitting `temperature`. Current repository code proves `0.1` is profile configuration but provides no provider/model compatibility contract for sending it; making a speculative request-shape change would exceed this reliability fix. The decision is documented and tested while the configured value remains available for other providers and future validated changes.

## Risks / Trade-offs

- [The serialized contract increases prompt size] → Keep keys compact where possible, retain existing prompt-fit checks, and test production-shaped packet budgets.
- [A provider may emit multiple JSON fragments across text blocks] → Deterministic concatenation preserves provider order, but strict bare-object parsing rejects structurally invalid combinations and permits one repair only when completion was normal.
- [Preservation can over-constrain repair] → Preserve only fields whose own shape/value and required dependency checks passed; always rerun the full contract after repair.
- [New metadata increases persisted payload depth/size] → Store a compact bounded attempt list with capped errors and no raw content, then exercise conversation normalization tests.
- [Normal stop-reason variants may evolve] → Preserve the sanitized raw stop reason and map unknown values conservatively without treating output exhaustion as complete.

## Migration Plan

No database migration is required. Implement and validate on the Mac, run offline focused and affected regression suites plus the acceptance harness, then hand off for a separately authorized commit/push and VM synchronization. Rollback is a source revert of planner/provider/model metadata changes; no persisted secret or schema cleanup is required. Production behavior remains unverified until separately authorized browser-path acceptance.

## Open Questions

None for Mac implementation. Any future decision to transmit Anthropic temperature or alter the 4,096-token ceiling requires a separately validated provider/model contract and is outside this change.
