## Why

Anakin planner observability currently persists safe `prompt_tokens` and `completion_tokens` usage counts as `[REDACTED]` because the session-memory sanitizer treats every key containing `token` as credential-bearing. Accounting and planner behavior remain correct, but per-turn reliability metadata loses useful numeric telemetry.

## What Changes

- Preserve narrowly approved numeric planner token-usage counts during session-memory sanitization.
- Keep credential-bearing token fields, passwords, secrets, API keys, authorization data, and unknown suspicious token-bearing fields redacted.
- Add focused sanitizer, nested-metadata, planner-persistence, depth, and artifact-normalization regression coverage.
- Make no changes to provider routing, accounting, planner behavior, prompts, session-depth handling, RBAC, or AI workflows.

## Capabilities

### New Capabilities

- `anakin-token-observability-redaction`: Distinguishes explicitly approved numeric token-usage telemetry from credential-bearing token fields while preserving fail-closed session-memory secret redaction.

### Modified Capabilities

None.

## Impact

- `core/ai/session_memory_store.py`
- Focused Anakin session-memory and conversation-orchestration tests
- No API, schema, provider, accounting, routing, deployment, or runtime configuration changes
