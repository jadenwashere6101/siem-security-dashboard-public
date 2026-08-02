## Context

Anakin currently has canonical synchronous workflows and a PostgreSQL-backed async request queue, but interactive SIEM requests are independent operations. Browser-owned history is incomplete and cannot enforce ownership, ordering, retention, provenance, or cross-tab idempotency. Analyst Workspace already owns investigations and analyst-curated records; those tables remain separate because conversation state has different lifecycle and trust semantics.

This change provides storage and APIs only. Stored content is untrusted data and is not added to prompts in this phase.

## Goals / Non-Goals

**Goals:**

- Persist private SIEM threads, immutable ordered turns, entity references, structured state, hypotheses, and bounded evidence.
- Enforce default-thread uniqueness, owner isolation, optimistic concurrency, idempotency, retention, reset, provenance, and artifact-preview safety deterministically.
- Provide authenticated foundation APIs without invoking an LLM or changing existing workflows.

**Non-Goals:**

- Follow-up/reference resolution, prompt injection, context selection, summarization, tool caching, frontend conversation UI, long-term memory, RAG, shared threads, Repo Assistant memory, or SOC Briefing continuation.
- Automatic writes to Analyst Workspace or any artifact confirm/apply behavior.

## Decisions

### PostgreSQL records are authoritative

Use normalized `anakin_threads`, `anakin_turns`, `anakin_thread_entities`, `anakin_thread_state`, `anakin_thread_hypotheses`, and `anakin_thread_evidence` tables. Add `anakin_thread_tombstones` solely to retain non-content deletion metadata after the 90-day hard-delete boundary. Browser state is never accepted as history.

Alternative considered: reuse `ai_workflow_requests` or Analyst Workspace JSON. Rejected because jobs, curated investigations, and conversations have different ordering, ownership, provenance, and retention contracts.

### Default identity is an immutable scope key

A default thread has `scope_key = investigation:<id>` or `entity:<type>:<id>` and a partial unique index on owner, domain, and scope while active. Explicit threads are marked non-default and are not covered by that uniqueness constraint. Creation uses an insert-with-conflict transaction so retries and multiple tabs resolve one default.

`investigation_id` uses `ON DELETE SET NULL`, while the immutable scope key remains. This preserves archived conversation content without blocking investigation deletion. New mutation fails when the associated investigation/entity is gone or inaccessible; it never substitutes another object.

### Turns use row-locked sequence allocation

Turn submission starts a transaction and locks the owner-scoped thread row. It first returns an existing `(owner, thread, client_request_id)` turn, then checks lifecycle and `expected_version`, allocates `next_sequence`, inserts the immutable turn, and advances thread sequence/version/activity/retention timestamps atomically. Stale versions return `409`; expired threads return `410`.

One active async execution per thread is enforced by a partial unique index over queued/running turns. Existing `ai_workflow_requests` gains nullable thread/turn columns and an owner-safe composite foreign key, but existing execution is not rewritten.

### Assertion classes are structurally separated

Public turn submission records user content only as `analyst_statement`, `correction`, or `unresolved_question`. Verified evidence exists only in `anakin_thread_evidence`. Assistant conclusions and hypotheses use `model_inference` provenance. A correction may supersede an inference/analyst statement but service validation rejects attempts to supersede evidence.

JSONB state columns have database type checks and service-level schema validation. State is treated as derived/rebuildable data; malformed state is rejected on write and omitted with `rebuild_required=true` on safe reads.

### Artifact content is conversation-only preview data

Artifact preview turns may retain sanitized text through refresh. A database check requires `preview_only=true`, `persisted=false`, `applied=false`, and `approval_required=true`. No route in this phase applies or saves an operational record.

### Retention is lifecycle-driven

Every accepted write moves `expires_at` to seven days after activity and `delete_after` to 90 days after activity. Lazy lifecycle enforcement marks due active threads expired before reads/writes. Reset row-locks and closes the old thread, immediately excludes it from future context, then creates/resolves a fresh default thread. A bounded cleanup helper hard-deletes due thread content by cascade and records a content-free tombstone.

### Ownership and authorization are request-time requirements

All routes require a currently authenticated analyst or super-admin. Every store read/write includes owner identity. Foreign keys and redundant owner columns enforce owner-safe relationships, including async request linkage. Repo and SOC Briefing domains are rejected by the SIEM thread service.

### Sanitization happens before storage

Content and structured payloads pass deterministic recursive redaction and instruction-like control-marker neutralization with size/depth limits. Audit events contain identifiers and lifecycle outcomes, not turn content, state, evidence snapshots, prompts, or secrets.

## Invariant Ownership

| Invariant | Database enforcement | Service enforcement |
|---|---|---|
| One active default per owner/scope | Partial unique index | Conflict resolves existing row |
| Unique ordered turn | Unique thread/sequence | Row lock allocates sequence |
| Duplicate submission | Unique owner/thread/client ID | Return existing before version check |
| Optimistic concurrency | Version stored atomically | Exact expected-version comparison |
| Owner isolation | Composite owner foreign keys/indexes | Owner predicate on every query |
| Valid lifecycle/assertion/provenance | CHECK constraints | Role-specific allowed transitions |
| No fact promotion | Evidence provenance CHECK | Public API cannot create evidence/inference |
| Artifact preview safety | Cross-column CHECK | Server forces all four labels |
| Async linkage | Composite owner/thread/turn FK | Validate request and turn before link |
| Retention | Timestamp/status constraints and cascade | Lazy expiry, reset transaction, bounded purge |
| Structured state shape | JSONB top-level CHECKs | Recursive schema/type/size validation |

## Transaction Boundaries And Concurrency

- Default create: validate target, insert thread and initial state in one transaction; unique conflicts resolve the active default.
- Turn append: lock thread, expire if due, detect duplicate, validate version/state, insert turn, update thread in one transaction.
- Reset: lock old thread, mark reset/closed, create replacement and state in one transaction.
- State/hypothesis/evidence writes: lock owner-scoped thread and validate lifecycle/version where applicable.
- Purge: select a bounded due set with `FOR UPDATE SKIP LOCKED`, insert tombstones, then cascade-delete.

No transaction spans LLM or tool execution. Future workers must claim the single queued/running turn and may update state only while holding the expected thread version.

## Failure-Class Handling

| Failure class | Deterministic behavior |
|---|---|
| Duplicate default creation | Unique active-default index; return existing thread |
| Duplicate client request | Unique idempotency key; return original turn/request |
| Two-tab/stale write | Row lock serializes; stale expected version returns `409` |
| Out-of-order allocation/completion | Transactional sequence; versioned completion cannot overwrite newer state |
| Cross-user access | Owner-filtered lookup returns non-enumerating `404` |
| Disabled user/role loss | Current request authentication/RBAC rejects access |
| Deleted/inaccessible target | Mutation returns target unavailable; no substitution |
| Expired/archived/reset thread | `410` for expired; closed/archived/reset rejects mutation |
| Reset race | Same row lock orders reset versus append; loser sees lifecycle/version change |
| Malformed state | Reject write; safe read marks rebuild required |
| Unsupported claim promoted to evidence | Public API can create analyst statements, not evidence |
| Inference promoted to fact | Inference and evidence use separate tables/provenance constraints |
| Correction overwrites evidence | Corrections may supersede only non-evidence assertions |
| Artifact mislabeled | Database and service force preview-only/non-applied labels |
| Secret/instruction-like storage | Recursive bounded sanitization before insert |
| Wrong async linkage | Composite owner/thread/turn foreign key and service validation |

## Risks / Trade-offs

- [Lazy expiry alone does not guarantee timely cleanup] -> Provide deterministic maintenance helpers and indexes; production scheduling is a later deployment decision.
- [Generic entity IDs cannot all use database foreign keys] -> Validate supported types against canonical stores and preserve immutable scope identity without substitution.
- [JSONB state can drift] -> Schema version, bounded validators, rebuild metadata, and authoritative turn/evidence records.
- [Archived content increases storage] -> Bounded payload sizes and 90-day hard-delete eligibility.
- [Additional owner columns are redundant] -> Keep them to enable composite ownership-safe foreign keys and database-level leakage prevention.

## Migration Plan

1. Add migration `0033` with additive tables, constraints, indexes, and nullable async linkage columns.
2. Update `schema.sql` to version `0033` and validate snapshot equivalence.
3. Deploy later through the documented migration helper only after commit/push/deployment authorization.
4. Rollback before use may drop the new linkage constraint/columns and new tables. After use, preserve rows and use a forward corrective migration rather than destructive rollback.

## Open Questions

None for this phase. Conversation orchestration, frontend integration, worker role revalidation, and production cleanup scheduling are deliberately deferred to dependent changes.
