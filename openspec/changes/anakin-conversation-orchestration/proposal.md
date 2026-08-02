## Why

Anakin's durable thread foundation is not connected to canonical SIEM workflows, so each request still executes as an isolated prompt and async results cannot become ordered conversation turns. Analysts therefore cannot safely ask follow-ups, correct an inference, recover an investigation after refresh, or rely on deterministic continuity.

## What Changes

- Add owner-scoped conversation orchestration for Quick Explain, Deep Investigate, Decision Support, Ask Anakin auto-routing, and Generate Artifact.
- Resolve follow-up intent and entity references deterministically from active entities, corrections, unresolved questions, and recent turns; ask for clarification instead of guessing when a reference is ambiguous.
- Select and compact thread context under each workflow's existing prompt budget without sending the complete thread or silently truncating it.
- Atomically persist and link user turns, async requests, terminal assistant turns, structured state, and artifact-preview safety labels.
- Recover thread state and async progress from PostgreSQL after refresh while preserving request idempotency, sequence ordering, ownership, and stale-completion protection.
- Revalidate user eligibility in workers and keep stored conversation text explicitly untrusted in prompts.
- Keep Repo Assistant and SOC Briefing isolated from SIEM conversation memory.

## Capabilities

### New Capabilities
- `anakin-conversation-orchestration`: Multi-turn SIEM workflow orchestration, bounded context selection, reference resolution, correction handling, async continuity, and workflow isolation over the existing session-memory foundation.

### Modified Capabilities

None.

## Impact

The change affects the canonical workflow orchestrator, async request service/store/worker, session-memory service/store, AI prompt builders, authenticated AI routes, and focused React request plumbing needed to retain authoritative thread identity across refresh. It adds PostgreSQL constraints only where required for terminal idempotency and orchestration linkage. Existing stateless callers remain compatible, and no model, tool, persistence boundary, or operational apply behavior changes.
