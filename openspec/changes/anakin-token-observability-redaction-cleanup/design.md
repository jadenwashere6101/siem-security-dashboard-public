## Context

`core/ai/session_memory_store.py::_sanitize_value()` recursively sanitizes structured session-memory values and redacts keys whose normalized names contain any `_SENSITIVE_KEY_PARTS` substring. The generic `token` substring correctly fails closed for credentials, but it also redacts planner `prompt_tokens` and `completion_tokens`, which are numeric usage telemetry rather than credentials.

## Goals / Non-Goals

**Goals:**

- Preserve explicitly approved numeric token-usage counts in structured session memory.
- Keep access, refresh, API, bearer, session, authentication, and unknown suspicious token fields redacted.
- Preserve recursive size, collection, depth, control-marker, and secret-handling behavior.

**Non-Goals:**

- Changes to provider routing, accounting, planner behavior, prompts, session depth handling, RBAC, or AI workflows.
- Persisting raw prompts, failed plans, hidden reasoning, provider responses, credentials, or secrets.
- Generalizing the allowlist to every key containing `token` or changing shared redaction helpers outside session memory.

## Decisions

### Exact key-and-type allowlist

Define a small immutable allowlist containing only the session-persisted planner fields `prompt_tokens` and `completion_tokens`. A field bypasses generic sensitive-key matching only when its normalized key exactly matches the allowlist and its value is a non-negative integer that is not a boolean.

Token usage counts are telemetry, not credentials. Requiring both exact key identity and numeric type prevents credential text from passing under a safe-looking name. Alternatives such as removing `token` from `_SENSITIVE_KEY_PARTS` or broadly allowing `*_tokens` are rejected because they weaken fail-closed handling.

### Preserve existing credential matching

The existing `_SENSITIVE_KEY_PARTS`, recursive traversal, and `[REDACTED]` contract remain otherwise unchanged. Credential-bearing token fields and unknown token-bearing names therefore continue to match `token` and remain redacted at every supported depth.

### Verify the real persistence shape offline

Focused tests will cover the sanitizer directly and the compact planner metadata persisted into a conversation turn using controlled in-process gateway responses. Tests will assert counts, completion state, stop reason, and typed validation metadata while proving raw prompts, failed plan text, reasoning, and secrets are absent.

## Risks / Trade-offs

- [A future safe usage key is redacted] → Keep fail-closed behavior; add another exact key only through reviewed source usage and regression tests.
- [A credential is placed under an approved key] → Permit only non-negative integer values; strings and all other types remain redacted.
- [Nested normalization changes accidentally] → Keep depth and artifact normalization code untouched and rerun their existing regressions.

## Migration Plan

No schema or data migration is required. Apply the source and test change on the Mac, then deploy only through the separately authorized normal workflow. Reverting the source change restores the prior conservative redaction behavior.

## Open Questions

None.
