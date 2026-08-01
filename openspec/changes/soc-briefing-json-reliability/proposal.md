# Proposal: SOC Briefing JSON Reliability

## Summary

Add a focused structured-output reliability layer to SOC Briefing synthesis. The worker already reaches the local AI model and gathers evidence; the remaining production defect is that provider output can be malformed, truncated, or schema-incomplete JSON. This change validates the briefing JSON and performs exactly one bounded repair attempt before failing cleanly to deterministic partial briefing content.

## Motivation

Production verification after commit `fa40e05` showed SOC Briefing reaches synthesis but can fail because `_parse_structured_response()` currently performs one strict `json.loads()` and returns malformed output with no repair path. Generate Artifact already has strict validation plus one bounded repair attempt; SOC Briefing should use the same reliability pattern without redesigning worker lifecycle, routing, deployment wiring, model selection, or runtime configuration.

## Goals

- Validate structured SOC briefing output before accepting it.
- Add exactly one bounded repair attempt for malformed or incomplete structured output.
- Fail closed with deterministic partial briefing content if repair fails.
- Preserve evidence integrity, read-only behavior, local-only routing, no paid fallback, and existing worker lifecycle semantics.
- Avoid infinite retries or fabricated evidence.
- Make the minimal justified completion-token budget adjustment if needed to reduce JSON truncation risk.

## Non-Goals

- No SOC Briefing architecture redesign.
- No frontend changes.
- No worker lifecycle, deployment, VM, model, or runtime configuration changes.
- No changes to evidence gathering or tool execution.
- No commit, push, VM access, deployment, or production mutation.

## Production Completion Gate

This change follows `docs/anakin-production-acceptance-policy.md`. Automated tests and local validation are necessary but not sufficient for production readiness. Until deployed browser-path verification through `/siem/` is performed, completion wording must be:

```text
Implementation complete; production behavior unverified.
```
