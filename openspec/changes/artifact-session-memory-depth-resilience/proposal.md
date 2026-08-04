## Why

Artifact Generation can complete successfully but fail while persisting a generated preview when nested artifact list entries exceed the session-memory JSON depth guard. Trusted generated artifacts need a bounded storage representation without weakening validation for arbitrary session data.

## What Changes

- Normalize generated artifact previews at the conversation persistence boundary into a depth-bounded representation.
- Preserve meaningful artifact fields, provenance, auditability, preview-only safety labels, and thread context.
- Record which artifact paths were flattened or truncated and the before/after payload depth.
- Keep the global session-memory depth limit and fail-closed validation for arbitrary or unsafe nested input unchanged.
- Verify persistence in both fresh and long-lived threads without applying an operational action.

## Capabilities

### New Capabilities
- `artifact-session-memory-normalization`: Defines safe, auditable persistence of generated artifact previews within session-memory limits.

### Modified Capabilities

None.

## Impact

The change is limited to the server-owned artifact-to-session-memory persistence boundary and focused unit, PostgreSQL, orchestration, and acceptance tests. It adds no schema, API, provider, planner, routing, frontend, or workflow changes.
