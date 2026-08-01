# Design: SOC Briefing JSON Reliability

## Structured Validation

SOC Briefing synthesis will parse provider output into a JSON object and validate the required structure before accepting it. A valid briefing response must include:

- `summary`: string, bounded before persistence;
- `sections`: object;
- every section listed in `BRIEFING_SECTIONS`;
- each section value as an array.

Missing sections, non-array sections, non-object payloads, malformed JSON, and truncated JSON are validation failures.

The parser may retain the existing tolerance for Markdown fences or extra text by extracting a JSON object when possible, but acceptance still requires the full schema. Missing sections are not filled from deterministic fallback for successful provider output because that can hide a provider schema failure.

## One Bounded Repair Attempt

When initial provider output is malformed or schema-invalid, SOC Briefing will perform exactly one repair call through the same gateway instance and profile used for synthesis.

The repair prompt is bounded and includes:

- the required briefing schema;
- the validation errors, capped to a small list;
- the original provider response, truncated to a bounded character count;
- explicit instructions to return one JSON object only;
- explicit instructions not to invent evidence and to use only the original response content.

Repair metadata uses `action=soc_briefing_repair`, `repair_attempt=1`, `read_only=true`, and SOC briefing service metadata. If repair succeeds and validates, the repaired JSON is accepted. If repair fails, is non-success, malformed, or still schema-invalid, synthesis returns deterministic partial content with error code `malformed_provider_output`.

## Evidence Integrity

The repair path receives only the provider output and schema errors, not raw tool evidence. It must not add new evidence references. Persisted briefing `evidence_refs` remain the bounded refs generated before synthesis. The final sections are still redacted before persistence.

## Completion Token Budget

The existing SOC briefing completion budget is `800` tokens. The required output is a JSON object with a summary and six arrays, and production showed malformed/incomplete JSON consistent with truncation risk. This change raises the default completion budget narrowly to `1200` tokens for SOC briefing synthesis only. It does not change runtime configuration, model selection, provider timeouts, or prompt limits.

## Failure Behavior

Unrecoverable malformed output remains fail-closed as partial briefing content:

- run/job/window/briefing status remain partial;
- deterministic sections are persisted;
- evidence refs are preserved;
- error code/message identify malformed provider output;
- no additional retries occur.
