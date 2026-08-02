## Why

Anakin has durable async jobs but no server-owned conversation thread, ordered turn history, or structured investigation memory. A PostgreSQL foundation is required before follow-up reasoning can be added without relying on browser history, duplicating work, leaking context across users, or racing concurrent requests.

## What Changes

- Add private, owner-scoped Anakin thread lifecycle records with one idempotently resolved default thread per user and investigation/entity, plus intentionally created non-default threads.
- Add immutable ordered turns with transactional sequencing, optimistic version checks, required client-request idempotency, lifecycle state, optional async-request linkage, and artifact-preview safety labels.
- Add normalized thread entities, structured state, hypotheses, and bounded evidence references that distinguish verified evidence, analyst statements, model inferences, corrections, and unresolved questions.
- Add authenticated APIs to create/read/reset threads, submit foundation-only turns, and retrieve turns with cursor pagination.
- Add deterministic seven-day active-context expiry, reset-to-fresh-thread behavior, 90-day content deletion eligibility, and minimal non-sensitive audit metadata.
- Preserve existing workflow execution, model/profile configuration, Repo Assistant, SOC Briefing, Analyst Workspace, and frontend behavior.

## Capabilities

### New Capabilities

- `anakin-session-memory-foundation`: Durable owner-scoped thread, turn, structured-state, evidence, retention, concurrency, idempotency, and foundation API contracts.

### Modified Capabilities

None.

## Impact

- Adds one PostgreSQL migration and updates the schema snapshot.
- Adds a focused backend store/service and authenticated Flask routes under `/ai/threads`.
- Adds PostgreSQL-backed, migration, RBAC, API, concurrency, retention, and affected Anakin regression tests.
- Does not invoke an LLM, inject history into prompts, reuse tool output, write Analyst Workspace records, alter frontend code, or change production runtime configuration.
