## Context

### Current architecture summary

Two independent automation paths are both wired into the same trigger point — `routes/ingest_routes.py`, immediately after alerts are committed during ingest:

```
alerts committed
    ├── enqueue_committed_alerts()        (engines/soar_enqueue_orchestrator.py)
    │       → response_actions_queue table
    │       → soar_action_worker.process_next_action()  (engines/soar_action_worker.py)
    │
    └── create_pending_executions_for_committed_alerts()  (engines/soar_playbook_orchestrator.py)
            → playbook_executions table
            → playbook_step_executor.process_playbook_execution_batch()  (engines/playbook_step_executor.py)
```

Both are called for every committed alert, unconditionally, in the same request. Neither path is aware of the other's existence or decision.

### What the response-action queue path currently does

- Trigger: `alert["response_action"]` — a single action string set directly by the detection engine's rule logic at alert-creation time (not a user-authored trigger config).
- Execution model: one action per alert, claimed via `FOR UPDATE SKIP LOCKED` (`core/response_action_queue_store.py`), executed by `engines/soar_action_worker.py`.
- Safety model: `APPROVAL_REQUIRED_ACTIONS = frozenset({"block_ip"})` (`engines/soar_action_worker.py`) forces an approval gate before `block_ip`; `core/soar_protected_targets.require_unprotected_target` is enforced before any block action executes.
- Reliability: real `retry_count` incrementing on failure (`record_action_failure`/`requeue_failed_action`), a fixed 15-minute stale-running timeout, no lease/heartbeat model.
- Scope: effectively a single-action "reflex" mechanism — it cannot express multi-step sequences, notifications-then-containment ordering, or investigation-only flows.

### What the playbook engine currently does

- Trigger: `trigger_config` JSON matched against alert fields (`alert_type`, `min_severity`, `source`, `correlation_flag`, `reputation_score_min`) via `engines/playbook_engine.py` — a general, user-authored matcher, not a detection-engine-set field.
- Execution model: an ordered list of steps (`monitor`, `flag_high_priority`, `require_approval`, `block_ip`, `notify_slack/teams/email/webhook`), executed linearly with lease-based concurrency control, stale-execution recovery, and dead-letter capture (`engines/playbook_step_executor.py`).
- Safety model: `require_approval` step is fully RBAC-enforced and TTL-bound; **`block_ip` does not call `soar_protected_targets` at all** — a confirmed gap, independent of this decision, already scoped into a separate correctness-hardening child spec.
- Reliability: canonical response-outcome event stream (`core/soar_response_outcomes.py`), append-only audit trail, dead-letter capture on terminal failure.
- Scope: a general orchestration framework — multi-step, approval-gated, extensible — but currently has zero real playbook content (per the audit, `playbook_definitions` has no persisted rows).

### Risks of leaving both paths ambiguous

- **Divergent safety enforcement on the same action class.** `block_ip` already means two different things depending on which path an alert happens to route through — one enforces a protected-target check, the other doesn't. This has already drifted out of sync once; nothing prevents it drifting further.
- **No single place to reason about "what will happen to this alert."** An engineer or interviewer asking "what does the SOAR system do with this alert" has to check two independently-maintained code paths and mentally merge the answer.
- **Duplicate maintenance burden.** Any future safety policy change (e.g., tightening the protected-target list, adding a new approval-required action) must be applied twice, in two modules with different data models, or it silently only applies to one path.
- **Compounding risk as content grows.** Every new playbook and every new detection-engine `response_action` mapping added without resolving this first makes a later consolidation strictly more expensive.

## Goals / Non-Goals

**Goals:**
- Produce one exact, unambiguous decision on the target relationship between the two paths.
- Define the boundary a later enforcement spec must operate within, without designing that spec's implementation here.
- Define measurable criteria for when the decision's end-state (a single authoritative path) is safe to finish enforcing.

**Non-Goals:**
- Not a decision about branching, chaining, evidence collection, playbook schedules, or new playbook content — those are separately scoped child specs.
- Not an immediate code change. No file under `engines/`, `core/`, or `routes/` is edited by this spec.
- Not a redesign of either path's internal data model.
- Not a schema change. If the eventual enforcement work turns out to require one (e.g., a shared safety-guard helper module is not itself a schema change, but a future data-linkage need might be), that is scoped and justified in the later enforcement spec, not decided speculatively here.

## Decisions

### Alternatives considered

1. **Merge the paths (single execution engine).** Teach one engine to process both trigger shapes (detection-set `response_action` and user-authored `trigger_config`) through one executor. Rejected as the literal mechanism: it would require rewriting the queue path's detection-engine integration and the playbook engine's step model into a shared abstraction before either is proven necessary — high effort, high risk, no clear win over designating one path authoritative and retiring the other on a criteria-gated timeline.
2. **Permanently keep both paths, separated by a hard boundary** (e.g., queue path only ever handles single immediate reflex actions; playbook path only ever handles multi-step/investigation flows, and no alert type is ever eligible for both). Rejected as a long-term end-state: it requires two safety implementations to be kept in sync forever, which is exactly the failure mode already observed (`block_ip` protected-target enforcement drifted between them once already). It remains useful as a *transitional* state (see Decision below), not a permanent one.
3. **Retire the playbook engine, keep the queue path.** Rejected: the playbook engine is strictly more capable (multi-step sequences, approval gates with TTL, lease-based concurrency, dead letters, canonical response-outcome audit trail) and is the foundation the rest of the modernization roadmap (real playbook content, branching, chaining) is built on. Retiring it would discard materially more engineering investment for a mechanism (the queue) that can only ever express single-action reflexes.
4. **Designate the playbook engine as the single authoritative orchestration layer; freeze and retire the queue path on a criteria-gated timeline.** Selected — see below.

### Decision criteria

The selected option was evaluated against:
- **Capability ceiling** — which path can express the full range of automation the roadmap already commits to (multi-step, approval-gated, eventually branching/chaining)? Only the playbook engine.
- **Safety-maintenance cost** — which option minimizes the number of places a safety policy (protected-target checks, approval-required actions) must be kept correct? A single authoritative path, not two permanently parallel ones.
- **Sunk engineering value** — which path has more built on top of it already worth preserving (leases, dead letters, canonical outcomes)? The playbook engine.
- **Migration risk** — can the transition happen without an unsafe "flip everything at once" cutover? Yes, via a frozen-then-retired queue path, gated on explicit parity/coverage criteria rather than a calendar date.

### Exact decision

**The playbook engine is designated the single authoritative SOAR orchestration layer.** Effective as of this decision:

1. The response-action queue path (`soar_enqueue_orchestrator` → `response_actions_queue` → `soar_action_worker`) is **frozen**: no new alert types, no new `response_action` values, and no new actions are added to it going forward.
2. All new SOAR automation — new alert types, new response logic, new actions — is implemented as playbooks (`playbook_definitions` + `trigger_config` + `steps`), not as queue rules.
3. The queue path continues operating, unchanged, only for the alert types it already serves, until the retirement criteria below are met.
4. Full retirement (removing the queue path's ingest-time trigger and, eventually, its code) is **contingent on** the parity and coverage criteria in Acceptance Criteria being satisfied by later child specs — it is not scheduled on a fixed date.
5. Until retirement, both paths must not be extended to overlap further: no alert type may simultaneously carry a queue-triggering `response_action` and match a new playbook's `trigger_config` for the same action class.

This is a freeze-then-retire decision, not an immediate deletion — consistent with "do not implement code" for this spec, and with de-risking the transition instead of a single risky cutover.

## Implementation Boundaries (for the later enforcement spec)

A later, separately-scoped child spec (not this one) will implement this decision. That spec's boundaries, defined here so it doesn't need to re-litigate the decision:

**In scope for that later spec:**
- Adding the deprecation/freeze notice (docstring/comment) to `engines/soar_enqueue_orchestrator.py` and `engines/soar_action_worker.py` referencing this decision.
- Confirming (via the correctness-hardening child spec) that the playbook engine's `block_ip` step enforces the same `soar_protected_targets` check the queue path enforces, before any coverage migration begins.
- Producing a coverage map of every alert type currently routed to the queue path via `response_action`, and confirming each has (or will have, via the playbook-content child spec) an equivalent playbook.
- Removing the queue path's ingest-time trigger call (`enqueue_committed_alerts`) only once coverage and parity are both confirmed.

**Out of scope for that later spec (and for this one):**
- New playbooks or new playbook content (separately scoped: `Core Playbook Pack v1`).
- New engine features: branching, chaining, ad hoc triggers, enrichment steps (separately scoped).
- Playbook schedules (separately scoped, unrelated to this decision).
- Evidence collection or UI changes (separately scoped, unrelated).
- Schema changes, unless the coverage-migration work later proves one is unavoidable — not assumed or designed here.
- Deleting `response_actions_queue` table/data — freezing and eventually bypassing the trigger is in scope; destructive data/schema removal is a separate, explicitly-approved future step if ever taken.

## Risks / Trade-offs

- **[Risk]** Freezing the queue path before the playbook engine has parity could leave a real gap if the queue path is ever relied upon in real (non-simulated) mode.
  **[Mitigation]** Freeze only stops *new* additions; existing queue-routed alert types keep working unchanged until their playbook equivalents exist and parity is confirmed by the correctness-hardening spec.
- **[Risk]** "Frozen but not retired" can linger indefinitely if later specs stall, leaving the ambiguity this decision was meant to resolve.
  **[Mitigation]** Acceptance criteria below are explicit and checkable, giving a concrete definition of "done" rather than an open-ended freeze.
- **[Risk]** Coverage mapping (every queue-routed alert type has a playbook equivalent) could reveal an alert type whose queue behavior is subtly different from what a playbook can currently express.
  **[Mitigation]** Any such gap becomes a scoped follow-up (e.g., a new engine capability), not a blocker to this decision — it would be handled by the relevant capability spec (e.g., branching) rather than reopening this decision.
- **[Risk]** Two engineers/interviewers reading the code before the freeze notice lands could still be misled.
  **[Mitigation]** Adding the freeze notice is explicitly listed as an in-scope, low-effort first task for the enforcement spec — not deferred with the harder migration work.

## Migration Plan

Not applicable in the schema/deployment sense — this spec makes no code or data changes. The "migration" here is organizational: future child specs proceed under the exact decision and boundaries recorded above. Rollback of this decision itself is simply: do not proceed with the enforcement child spec; both paths remain as they are today (the pre-existing ambiguity), which is the status quo this document was written to move away from.

## Open Questions

- Does any currently queue-routed alert type have safety behavior (beyond protected-target + approval-required `block_ip`) that the playbook engine cannot yet express? To be answered by the coverage-mapping task in the later enforcement spec, not assumed here.
- Should the freeze notice also include a machine-readable marker (e.g., a module-level constant) that a future lint/CI check could assert on, to prevent accidental new `response_action` mappings? Left to the enforcement spec to decide.
