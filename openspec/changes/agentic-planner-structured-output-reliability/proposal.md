## Why

The agentic planner's prompt, parser, validator, repair feedback, and Anthropic completion handling do not currently share a complete contract. Malformed or truncated output can therefore be misclassified, repaired imprecisely, and persisted with too little sanitized diagnostic detail even though execution remains fail-closed.

## What Changes

- Define one authoritative planner-output contract that drives initial and repair instructions, validation expectations, and contract tests, including conditional fields, cardinalities, filter formats and bounds, and entity/evidence binding.
- Align concise planner instructions with every validator-owned requirement, including array shapes, nullable capabilities, artifact and clarification conditions, correction references, and per-tool evidence keys.
- Preserve sanitized Anthropic completion metadata, including `stop_reason`, deterministic text-block handling, token usage, and explicit normal, exhausted, malformed/no-text, and transport/error states without exposing thinking content.
- Classify output exhaustion before JSON parsing or semantic validation for both the initial proposal and the single repair attempt.
- Replace prose-only validation feedback with bounded typed errors for parse, schema, semantic, entity-binding, and provider-completion stages.
- Keep exactly one bounded repair attempt, use the same authoritative contract, include only a bounded invalid proposal, and derive preservation requirements from explicitly validated field state rather than error-message substring matching.
- Enforce the prompt's existing bare-JSON-only contract and continue rejecting fences, surrounding prose, multiple objects, and unvalidated plans.
- Persist and log bounded sanitized reliability metadata for initial and repair attempts while preserving the existing paid-usage correlation and accounting semantics.
- Retain the 4,096-token planner output ceiling and document the Anthropic adapter's intentional omission of profile temperature because the repository has no current provider/model contract authorizing that request parameter.

## Capabilities

### New Capabilities

- `agentic-planner-structured-output-reliability`: Authoritative structured planner contracts, typed validation and repair, Anthropic completion classification, and bounded diagnostic observability.

### Modified Capabilities

None.

## Impact

Primary impact is limited to the Mac source-of-truth planner, normalized AI request metadata, Anthropic provider adapter, compact conversation planner metadata, offline acceptance fixtures, and focused tests. Routing, paid-budget/accounting policy, workflow execution, evidence grounding, RBAC, mutation boundaries, provider traffic, VM state, and deployment are unchanged.
