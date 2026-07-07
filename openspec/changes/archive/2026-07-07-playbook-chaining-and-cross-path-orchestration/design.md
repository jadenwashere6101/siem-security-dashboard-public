## Executive Summary

This is the last child spec on the roadmap, and it closes two related gaps that only make sense to close once everything before it exists: (1) a playbook still cannot trigger another playbook — every roadmap item so far has extended what a *single* execution can do (parameters, branches, evidence), but never let one execution hand off to a second, independently-tracked one; and (2) the `soar-automation-path-consolidation-decision` named the playbook engine authoritative and froze the response-action queue, but froze it only as a documentation convention — today, both paths still fire unconditionally for every alert, and nothing in code actually enforces "exactly one path acts." This spec designs both: an explicit, depth-limited, fire-and-forget `trigger_playbook` step that reuses the canonical-outcome ledger's existing parent/child linkage column rather than inventing one, and a small precedence guard at the one place both paths are already invoked, so the already-made decision becomes an enforced fact instead of a convention. Both designs lean hard on reuse: the audit below found that nearly every primitive needed (dedup constraints, parent-correlation-id linkage, a unified dead-letter model, an alert-id-based timeline fallback) already exists and already works across both paths — this spec's net-new surface is small by design.

## Current Orchestration Audit

Re-verified directly against the current code:

1. **Two independent orchestrators, one shared trigger point.** `routes/ingest_routes.py` calls, in this exact order, at all five ingest call sites: `enqueue_committed_alerts(alerts_created, conn)` (queue path) → `_create_incidents_for_alerts(alerts_created, conn)` → `_create_playbook_executions_for_alerts(alerts_created, conn)` (playbook path, via `engines/soar_playbook_orchestrator.create_pending_executions_for_committed_alerts`). **The queue enqueue call runs before playbook matching is even evaluated** — today there is no way for one path to know what the other decided, because the playbook match hasn't happened yet when the queue decision is made.

2. **Playbook execution creation already supports linkage fields that go unused for chaining today.** `core/playbook_store.create_pending_playbook_execution_once(conn, playbook_id, alert_id, incident_id=None, *, decision_id=None, soar_correlation_id=None)` already accepts optional `decision_id`/`soar_correlation_id` (used today only for the alert-triggered creation path). A unique index, `idx_playbook_executions_playbook_alert_unique` on `(playbook_id, alert_id) WHERE alert_id IS NOT NULL AND status IN ('pending','running','awaiting_approval')`, already prevents two concurrently-active executions of the *same* playbook against the *same* alert — a real, existing dedup guard, but one that does not by itself prevent a *cross-playbook* cycle (A triggers B, B triggers A), since that involves two different `playbook_id` values.

3. **The canonical outcome ledger already has a parent/child linkage column, currently used one hop, for a different relationship.** `soar_response_decisions.parent_soar_correlation_id` (schema.sql line 575) is already populated today by `engines/soar_playbook_orchestrator._get_parent_soar_correlation_id`, which links a *newly created playbook execution's* decision back to whatever canonical decision already existed for that alert (e.g., the detection engine's original `response_action` decision). This is exactly the mechanism a chained child execution's decision needs — just pointed at the *parent execution's* `soar_correlation_id` instead of the alert's original decision.

4. **`playbook_executions.incident_id` is set at creation but is realistically always `NULL` in the current flow.** `create_pending_executions_for_committed_alerts` always calls `create_pending_playbook_execution_once(..., incident_id=None)`, and no function anywhere back-fills it afterward. This is not a bug this spec needs to fix — `routes/incident_routes.build_readonly_incident_timeline` already compensates for it: it unions executions matching `incident_id = %s` with executions matching `incident_id IS NULL AND alert_id = ANY(linked_alert_ids)` (the `via_alert_fallback` flag), specifically because `incident_id` is usually null. This means any chained child execution that shares its parent's `alert_id` **already** shows up correctly in the same incident's timeline today, with zero changes to that query.

5. **Dead-letter capture and the canonical outcome/audit model are already unified across both paths**, not split. `core/dead_letter_store.py`'s `VALID_SOURCE_TYPES` already includes both `"playbook_execution"` and `"response_action"`; `core/soar_response_outcomes.py`'s decision/event tables are keyed generically (`playbook_execution_id`, `queue_id`, both nullable, both already present on `soar_response_decisions`/`soar_response_outcome_events`). The split between the two paths is purely at the *trigger/execution* layer, not the audit layer — this spec does not need to unify auditing, because it already is unified.

6. **Approval gates are already fully scoped per-execution.** `approval_requests` is keyed by `playbook_execution_id` + `playbook_step_index`; a `require_approval` step pauses only its own execution (`status = 'awaiting_approval'`). Nothing about the current approval model assumes or requires a single execution per alert — it already tolerates multiple independent executions (e.g., two different playbooks matching the same alert today) each pausing independently.

7. **Retry, stale-recovery, and lease mechanics are execution-scoped and chain-agnostic already.** `mark_stale_execution_for_recovery`, `acquire_execution_lease`, `claim_next_pending_playbook_execution_with_lease` all operate on one `playbook_executions` row at a time with no notion of "this execution has children" — a chained child execution is, to all of this existing machinery, just another ordinary pending execution. This spec does not need to touch any of it.

8. **No chaining action exists today.** `engines/playbook_registry.py`'s `CORE_ACTIONS`/`ADAPTER_ACTIONS`/`KNOWN_PLAYBOOK_ACTIONS` contain `monitor`, `flag_high_priority`, `require_approval`, `notify_slack`, `notify_teams`, `notify_email`, `notify_webhook`, `block_ip` (and, per `conditional-branching-primitive`, `branch`) — nothing that creates a second execution. This confirmed gap is exactly what this spec closes.

## Current Response-Action Queue Audit

Re-verified directly against the current code:

1. **The queue's entire decision space is three actions, keyed purely on reputation score.** `core/ip_helpers.determine_response_action(reputation_score)`: `>= 80 → "block_ip"`, `>= 60 → "flag_high_priority"`, else `"monitor"`. It is called unconditionally for every alert at generation time in `engines/detection_engine.py` (11 call sites) and `engines/correlation_engine.py` (2 call sites), and the result is stored as `alert["response_action"]` before the alert dict ever reaches `enqueue_committed_alerts`. There is no severity gate, no alert-type gate — reputation score alone decides.

2. **The queue path's execution model** (`engines/soar_action_worker.py`): `APPROVAL_REQUIRED_ACTIONS = frozenset({"block_ip"})` forces an approval gate before block actions; claims work via `FOR UPDATE SKIP LOCKED` (`core/response_action_queue_store.py`); real `retry_count`/`max_retries` with a fixed 15-minute stale-running timeout; no lease/heartbeat model (confirmed absent from `response_actions_queue`'s schema, unlike `playbook_executions`).
3. **`soar-automation-path-consolidation-decision`'s Acceptance Criterion 1 (protected-target parity) is already satisfied.** Re-confirmed directly: `engines/playbook_step_executor.py` imports `core.soar_protected_targets.require_unprotected_target` and calls it for the `block_ip` action (`if action == "block_ip": require_unprotected_target(params.get("source_ip"))`) — this was closed by `playbook-engine-correctness-hardening` (already merged per that spec's own proposal). No further work is needed for this criterion; this spec only needs to record that it is satisfied.
4. **No freeze/deprecation notice exists yet** in `engines/soar_enqueue_orchestrator.py` or `engines/soar_action_worker.py` — Acceptance Criterion 3 of the consolidation decision (freeze notice present) is **not yet satisfied**. This spec's implementation scope owns adding it.
5. **No coverage map has been produced yet** as a concrete artifact — Acceptance Criterion 2 is **not yet satisfied** as a checked box, though the ingredients for one already exist (see Queue Retirement Strategy below, which builds the actual map from `core-playbook-pack-v1`'s already-designed five playbooks).
6. **`response_actions_queue` and `soar_dead_letters`/`soar_response_decisions` rows referencing it are real, historical data** — nothing about freezing or bypassing the ingest-time trigger requires deleting any of this; `soar_response_decisions.queue_id` and `soar_dead_letters` both already model the queue path as a first-class, permanent citizen of the audit trail, decision already recorded in the consolidation spec that destructive removal is a distinct, separately-approved future step.

## Playbook Chaining Model

**Explicit-only, via one new non-adapter step action: `trigger_playbook`.**

```json
{
  "action": "trigger_playbook",
  "params": {
    "playbook_id": "malicious_ip_containment_v1"
  }
}
```

No playbook ever chains implicitly as a side effect of any other action, trigger match, or branch decision — a `trigger_playbook` step must be explicitly authored, exactly like every other step type. This is the same "smallest viable primitive" posture as `conditional-branching-primitive`'s `branch` step: one new, narrowly-scoped action, handled by the same special-casing pattern `_process_steps` already uses for `require_approval` (and, per that prior spec, `branch`) — not routed through `ADAPTER_ACTIONS`/`execute_playbook_simulated_adapter`, because dispatching a chained playbook is an engine-internal operation (creating a new `playbook_executions` row), not an integration-adapter call.

**Dispatch is asynchronous and fire-and-forget, not synchronous/blocking.** When a `trigger_playbook` step executes:

1. The step creates a new pending execution for the target `playbook_id`, reusing the exact same `core.playbook_store.create_pending_playbook_execution_once` function the ingest-time orchestrator already uses — no new insert path.
2. The child execution inherits the **same `alert_id`** as the parent execution (the scenario this models is "playbook A's response to alert X includes also running playbook B against alert X," not an unrelated alert). This means the existing `(playbook_id, alert_id)` unique-while-active index applies to the child exactly as it would to any independently-triggered execution — if playbook B is *also* separately trigger-matched against the same alert directly, the existing dedup constraint (not a new mechanism) prevents a duplicate concurrent run.
3. The `trigger_playbook` step then immediately records success — its job was "dispatch the child," which it did. **It does not wait for the child to start, run, or complete.** The child is picked up later by the same existing worker batch loop (`process_playbook_execution_batch`) that already processes every other pending execution, on its normal schedule.

This is a deliberate rejection of synchronous chaining (see Alternatives Considered): it requires zero changes to the lease/worker model, introduces no new polling or scheduler behavior, and keeps a chained execution indistinguishable, to every piece of existing reliability machinery (leases, stale-recovery, retries, dead letters), from an ordinary independently-triggered execution.

**Only one hop of chaining is authored at a time — chains of chains are just repeated single hops**, each independently validated and depth-checked (see Safety / Loop Prevention). There is no "workflow" object describing a multi-playbook sequence; there is only "this step dispatches that playbook," which can itself contain a `trigger_playbook` step, subject to the depth cap.

## Cross-Path Orchestration Model

**Goal: exactly one authoritative path acts per alert, enforced in code, not just documented.**

The mechanism is a precedence guard at the one place both paths are already invoked (`routes/ingest_routes.py`), reordered so the already-authoritative path decides first:

1. **Reorder**: run `_create_playbook_executions_for_alerts` (playbook matching + pending-execution creation) *before* `enqueue_committed_alerts` at all five ingest call sites — today it runs last; this spec requires it run first specifically so its match results are known before the queue decision is made.
2. **Thread the match result through**: `create_pending_executions_for_committed_alerts` already returns a `results` list with one entry per alert, each carrying `alert_id` and a `status` in `{"created", "duplicate", "no_match", "skipped", "error"}`. Collect `{alert_id for entries where status in ("created", "duplicate")}` — i.e., every alert for which at least one playbook is now authoritatively handling it.
3. **Pass that set into the queue path**: `enqueue_committed_alerts(alerts_created, conn, exclude_alert_ids=matched_alert_ids)` (new optional parameter, default empty set — fully backward compatible for any other caller). For any alert in `exclude_alert_ids`, `enqueue_committed_alerts` skips the enqueue entirely and records a result with `status: "skipped", skip_reason: "playbook_precedence"` — the same shape it already uses for other skip reasons, no new result shape invented.

This operationalizes, in code, exactly what the consolidation decision already stated as a convention ("no alert type may simultaneously carry a queue-triggering `response_action` and match a new playbook's `trigger_config` for the same action class") — the precedence guard makes that true even for cases the convention alone couldn't prevent (e.g., an alert type that still has *both* a detection-engine-assigned `response_action` *and* happens to match a playbook's `trigger_config`, because the playbook pack and the detection engine's reputation-based logic overlap by construction, as they do for `Malicious IP Containment`/`Reputation-Only Investigation` — see below).

The guard is intentionally one-directional (playbook wins, queue yields) because the consolidation decision already designated the playbook engine authoritative — there is no scenario in this design where the queue path should suppress a playbook match.

## Queue Retirement Strategy

Applying the consolidation decision's three retirement criteria concretely, using what this audit found:

| Criterion | Status | Basis |
|---|---|---|
| 1. `block_ip` protected-target parity | **Already satisfied** | Confirmed in this audit: `playbook_step_executor.py` already calls `require_unprotected_target` for `block_ip`, closed by `playbook-engine-correctness-hardening`. |
| 2. Coverage map | **Built here, one gap identified** | See table below, built directly from `core-playbook-pack-v1`'s already-designed five playbooks against the queue's three reputation bands. |
| 3. Freeze notice present | **Not yet done — owned by this spec's implementation scope** | No notice exists today in `soar_enqueue_orchestrator.py`/`soar_action_worker.py`. |

**Coverage map** (queue's three possible `response_action` values against the playbook pack `core-playbook-pack-v1` already designed):

| Queue band | Queue action | Playbook equivalent | Match? |
|---|---|---|---|
| `reputation_score >= 80` | `block_ip` (approval-gated, protected-target-checked) | Playbook 4, *Malicious IP Containment* — trigger `{"reputation_score_min": 80, "min_severity": "medium"}` | **Partial** — the queue path blocks on reputation alone, with no severity gate; the playbook additionally requires `min_severity: medium`. An alert with `reputation_score >= 80` and `severity: low` would be blocked by the queue today but would **not** match Playbook 4. This is an explicit, named gap, not an oversight of this spec. |
| `60 <= reputation_score < 80` | `flag_high_priority` (no approval, simulated escalation only) | Playbook 5, *Reputation-Only Investigation* — trigger `{"reputation_score_min": 40, "min_severity": "low"}` | **Covered, and broader** — Playbook 5's lower threshold (40) and lower severity floor (`low`) mean it already fires for this entire band and more; it does strictly more investigation-nudging than the queue's silent `flag_high_priority`, not less. |
| `reputation_score < 60` | `monitor` (log-only no-op) | No dedicated playbook required | **Acceptable, trivially** — the queue's `monitor` action performs no state change beyond a log line; there is nothing to replicate. |

**The one real gap (severity floor on the `block_ip` band) must be explicitly resolved or explicitly accepted before full retirement** — this spec does not resolve it unilaterally (that is playbook-content authorship, out of this engine-capability spec's scope), but it names the two concrete options for whoever implements `core-playbook-pack-v1`'s content: (a) loosen Playbook 4's `min_severity` to match the queue's severity-agnostic behavior exactly, or (b) explicitly accept that the playbook engine is deliberately more conservative here (requires severity corroboration before blocking on reputation alone) as an intentional safety improvement, sign off on it, and document the accepted divergence. Either resolution is compatible with this spec; this spec's acceptance criteria require the decision be made and recorded, not which way it goes.

**Staged retirement, gated on criteria, not a calendar date:**

- **Stage 1 (this spec's implementation scope):** add the freeze notice to both queue modules; implement the precedence guard above (queue path is *bypassed* per-alert whenever a playbook already claimed it, without deleting the queue's ingest trigger); record the coverage map and its one named gap.
- **Stage 2 (gated, future, not authorized by this spec):** once the coverage gap is explicitly resolved or accepted, and the precedence guard has been observed (via existing logging — `skip_reason: "playbook_precedence"` counts trending toward "all queue-eligible alerts are now claimed by a playbook") to leave zero real queue activity for a defined bake-in period, remove the `enqueue_committed_alerts(...)` call sites entirely from `routes/ingest_routes.py`. The queue's code and table remain; only the ingest-time trigger is removed.
- **Stage 3 (explicitly out of scope, here and in the consolidation decision):** destructive removal of `response_actions_queue`/`soar_dead_letters` historical rows or the `soar_action_worker.py`/`soar_enqueue_orchestrator.py` modules themselves. Not authorized by this spec; a distinct, explicitly-approved future step if ever taken.

## Parent/Child Execution Tracking

**Two linkage points, both additive, both reusing existing patterns:**

1. **`playbook_executions.parent_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL`** (new column) — direct, cheap, in-table ancestry for the step executor's own loop-prevention check (walking ancestors without a join through the outcome-decision table) and for any future "show me this execution's chain" query. `NULL` for every execution that isn't the result of chaining (i.e., every execution that exists today keeps `parent_execution_id = NULL`, fully backward compatible).
2. **`soar_response_decisions.parent_soar_correlation_id`** (already exists, already nullable, already used for one hop of a different parent/child relationship) — the child execution's canonical decision sets this to the *parent execution's* `soar_correlation_id`, produced via the existing `engines.soar_playbook_orchestrator.create_and_link_playbook_execution_decision` (already a public entry point, already used by the retry route) called with `parent_soar_correlation_id=parent_decision["soar_correlation_id"]` instead of the alert-level parent it uses today for top-level executions.

**A new scalar, `playbook_executions.chain_depth INTEGER NOT NULL DEFAULT 0`**, tracks how many chain hops deep an execution is (0 for any top-level, alert-triggered execution; `parent.chain_depth + 1` for a dispatched child) — this is what Safety / Loop Prevention below enforces a hard ceiling on.

**Outcomes are represented exactly as today's independent-execution model already represents them — nothing new is invented.** The parent's `steps_log` entry for its `trigger_playbook` step records the child's `execution_id`, `playbook_id`, and `chain_depth` at dispatch time (the same pattern `require_approval`'s steps_log entry already uses to record `approval_request_id`). The child's own `steps_log`, status, and canonical outcome events are entirely its own — there is no "rollup" status that merges a parent and its children into one combined outcome; an analyst reads the parent's record to see "a child was dispatched" and the child's own record (linked via `parent_execution_id`) to see what actually happened.

**Timeline visibility requires zero changes.** Because the child inherits the parent's `alert_id`, and `routes/incident_routes.build_readonly_incident_timeline` already unions executions by `alert_id` when `incident_id IS NULL` (which it realistically always is, per the audit above), a chained child execution already appears in the same incident timeline as its parent today, automatically, the moment it exists as a `playbook_executions` row — this spec relies on that existing fallback rather than adding a second code path for it.

## Safety / Loop Prevention

Two independent, layered guards — one static (definition-time), one dynamic (dispatch-time) — deliberately avoiding a full cross-definition graph-reachability analysis (which would be exactly the "graph workflow builder" this spec is told to avoid):

1. **Definition-time (in `engines/playbook_registry.py`, extending `validate_playbook_steps`): reject only the trivial, statically-detectable case.** A `trigger_playbook` step whose `params.playbook_id` equals the playbook's own `id` is rejected at save time — the one cycle that is always cheaply detectable without inspecting any other playbook's content.
2. **Dispatch-time (in `engines/playbook_step_executor.py`, when a `trigger_playbook` step actually executes): two hard checks, both fail-closed.**
   - **Depth cap**: a small constant, `MAX_CHAIN_DEPTH = 3`. If the dispatching execution's `chain_depth >= MAX_CHAIN_DEPTH`, the step fails closed (`chain_depth_exceeded`) and no child is created — this alone makes unbounded chains, including cycles that would otherwise run forever, impossible, regardless of shape.
   - **Ancestor-cycle check**: walk the dispatching execution's own ancestor chain via `parent_execution_id` (bounded by `MAX_CHAIN_DEPTH` hops, so this is always a small, cheap walk — never a full-graph traversal) and check whether the target `playbook_id` already appears among those ancestors' `playbook_id` values. If it does, the step fails closed (`chain_cycle_detected`) rather than dispatching — this catches indirect cycles (A → B → A) that the definition-time self-reference check cannot see, without ever inspecting playbook definitions other than the ones actually in this specific execution's lineage.

Together, these two dispatch-time checks mean a cycle is caught at the exact moment it would first manifest at runtime, not by trying to reason about the full graph of every playbook's `trigger_playbook` steps in advance — consistent with "smallest viable orchestration layer" and explicitly not a workflow-graph validator.

## Approval Behavior

**Unchanged, fully reused, no new cross-execution approval concept.** A `require_approval` step inside a *chained child* execution behaves exactly as it does in any standalone execution: it pauses only that execution (`status = 'awaiting_approval'`), creates an `approval_requests` row keyed to that child's own `playbook_execution_id`, and is decided independently through the existing approval routes/RBAC. The parent execution that dispatched the child is unaffected — having already recorded its `trigger_playbook` step as successful (the dispatch happened), the parent does not block on, wait for, or get notified synchronously about the child's approval decision. An analyst sees the child's `awaiting_approval` state exactly where they'd see any other execution's, and can navigate parent → child via `parent_execution_id` if they want to understand why it exists. No new approval type, no new RBAC surface, and no "approve the whole chain at once" mechanism is introduced — each execution's approval gates remain independently scoped, exactly as `conditional-branching-primitive`'s opt-in `on_denied/on_expired: "branch"` also left approval semantics untouched within a single execution.

## Auditability

- **Every chain hop is traceable in both directions** without new query infrastructure: forward (parent → child) via the parent's `steps_log` entry recording the dispatched `execution_id`; backward (child → parent) via `parent_execution_id` (direct column) and `parent_soar_correlation_id` (canonical-decision level, consistent with how every other parent/child relationship in the outcome ledger is already represented).
- **The precedence guard's every decision is logged and attributable.** `enqueue_committed_alerts`'s existing per-alert result list already has a `status`/`skip_reason` shape (`"skipped"`/`"duplicate"` today) — `"playbook_precedence"` is simply one more value in that same, already-existing shape, requiring no new logging mechanism.
- **The coverage map itself is an auditable artifact** (recorded in this spec's design), not a one-time decision made and forgotten — any future change to `determine_response_action`'s thresholds or to a playbook's trigger config should prompt re-checking this map, exactly as a schema migration prompts re-checking a data contract.
- **Dead-letter capture applies to chained executions with zero new code**, because `capture_failed_execution_dead_letter` already operates per-`playbook_executions` row and already writes `source_type: "playbook_execution"` regardless of whether that row has a `parent_execution_id` — a failed child execution dead-letters exactly like a failed top-level one.

## Alternatives Considered

- **Synchronous/blocking chaining** (parent's `trigger_playbook` step waits for the child to reach a terminal state before the parent's own step is marked complete). Rejected: this would require either recursive, in-process execution of `_process_steps` (breaking the lease/worker model that assumes one execution is processed per claim) or a new polling/wait mechanism inside the executor — exactly the "new scheduler behavior" this spec is told to avoid. Fire-and-forget dispatch, with the child processed by the existing worker batch loop like any other pending execution, needs neither.
- **A new dedicated "chain" table** (separate from `playbook_executions`) to represent multi-playbook workflows as a first-class object. Rejected: there is no "workflow" concept in this design, only individual dispatches; a chain is fully reconstructable from `parent_execution_id` links across ordinary `playbook_executions` rows, which is smaller and reuses every existing execution-lifecycle mechanism (leases, retries, dead letters) without adaptation.
- **Full cross-definition graph-reachability validation at save time** (statically prove no playbook's `trigger_playbook` steps can ever form a cycle, across all playbooks). Rejected as exactly the "graph workflow builder" this spec is told to avoid — it requires re-validating every existing playbook definition whenever any one of them changes, and produces the same practical guarantee (no runtime cycles) that the cheaper combination of a depth cap plus a bounded ancestor walk already provides.
- **Merging the queue and playbook paths into one executor** (revisiting the consolidation decision's rejected "merge" option). Rejected again here for the same reasons the consolidation decision already gave: the two trigger shapes (detection-set `response_action` vs. user-authored `trigger_config`) are different enough that merging them is a rewrite, not an orchestration layer; the precedence guard achieves the actual goal (exactly one path acts) without that rewrite.
- **Immediately removing the queue's ingest-time trigger in this same spec.** Rejected: the coverage map found one real, named gap (the severity floor on the `block_ip` band); removing the trigger before that gap is resolved or explicitly accepted would be an unsafe, unreviewed behavior change, not a "smallest viable" step. The precedence guard is the safe intermediate step; full trigger removal is Stage 2, explicitly gated and explicitly not authorized by this spec.
- **A visual workflow designer / DAG builder for chains.** Rejected outright per this spec's explicit non-goals — a chain in this design is never more than "this step names that playbook," with no editor, no canvas, and no graph object to design one.

## Implementation Scope

(For a later, separately-scoped and explicitly-requested implementation pass — not part of this spec-authoring step.)

- **Migration**: `ALTER TABLE playbook_executions ADD COLUMN parent_execution_id INTEGER REFERENCES playbook_executions(id) ON DELETE SET NULL, ADD COLUMN chain_depth INTEGER NOT NULL DEFAULT 0;` plus an index on `parent_execution_id`; update `schema.sql` to match.
- **`engines/playbook_registry.py`**: add `trigger_playbook` to `CORE_ACTIONS`; add the definition-time self-reference rejection rule.
- **`engines/playbook_step_executor.py`**: special-case `trigger_playbook` in the step-dispatch loop (alongside `require_approval` and `branch`); implement dispatch (create child via `create_pending_playbook_execution_once`, set `parent_execution_id`/`chain_depth`, link canonical decision via `parent_soar_correlation_id`); implement the depth cap and bounded ancestor-cycle walk, both fail-closed.
- **`engines/soar_playbook_orchestrator.py`**: no change required to the public `create_and_link_playbook_execution_decision` entry point — it already accepts `parent_soar_correlation_id`; the chaining dispatch code simply becomes a second caller of it.
- **`engines/soar_enqueue_orchestrator.py`**: add the `exclude_alert_ids` parameter to `enqueue_committed_alerts` and the `"playbook_precedence"` skip path; add the freeze/deprecation notice.
- **`engines/soar_action_worker.py`**: add the freeze/deprecation notice referencing the consolidation decision.
- **`routes/ingest_routes.py`**: reorder the five call sites so `_create_playbook_executions_for_alerts` runs before `enqueue_committed_alerts`, and thread the matched-alert-id set between them.
- **Tests**: registry validation (self-reference rejection), executor tests (successful dispatch, depth-cap fail-closed, ancestor-cycle fail-closed, child inherits `alert_id`, parent step succeeds regardless of child's later outcome), orchestrator tests (precedence guard skips queue enqueue when a playbook claimed the alert, queue still enqueues when no playbook matched), and a full existing-suite regression run confirming zero behavior change for every alert/playbook that doesn't use chaining and every alert the queue path already handles unchanged.
- No new engine, no new adapter, no scheduler, no UI component required for either capability to be functionally complete.

## Non-goals

- New playbooks or new playbook content (the coverage-gap resolution is a `core-playbook-pack-v1` content decision, not this spec's to make).
- Scheduler work of any kind (chaining is fire-and-forget onto the existing worker batch loop, not a new polling mechanism).
- UI redesign or a visual chain/workflow viewer (a later, separate pass may add one; not required for this capability to be complete).
- A visual workflow builder or DAG designer.
- Arbitrary graph execution or full cross-definition cycle validation.
- Recursive loops or unbounded chain depth of any kind.
- New external integrations or adapters.
- Deployment changes.
- New dependencies.
- Evidence-model changes (this spec does not touch `incident-evidence-collection-and-case-enrichment`'s snapshot; a chained child execution's evidence, if its own alert-linkage ever needed one, is out of scope here).
- Ad hoc trigger implementation (a separate, not-yet-created roadmap item; this spec's chaining mechanism is playbook-to-playbook only, not alert-to-ad-hoc-step).
- Immediate, unconditional removal of the queue path's ingest-time trigger (Stage 2, explicitly gated and not authorized here) or destructive removal of queue data/code (Stage 3, explicitly out of scope per the consolidation decision).
- Backend schema redesign beyond the two justified, additive `playbook_executions` columns described above.

## Risks

- **[Risk]** Reordering the five ingest call sites (`_create_playbook_executions_for_alerts` before `enqueue_committed_alerts`) changes an established call order that other code might implicitly depend on.
  **[Mitigation]** Both calls are already independently try/except-wrapped and independently committed in the current code (confirmed in this audit); reordering them changes only which decision is known first, not their independent failure isolation. The acceptance criteria require a regression run confirming identical behavior for every alert that doesn't trigger the new precedence path.
- **[Risk]** The coverage map's one named gap (Playbook 4's severity floor vs. the queue's severity-agnostic `block_ip`) could be overlooked if implementation proceeds straight to Stage 2 without resolving it.
  **[Mitigation]** This spec's acceptance criteria explicitly require the gap be resolved-or-accepted-and-recorded before Stage 2 (full trigger removal) is authorized — Stage 2 is explicitly not authorized by this spec at all, precisely to force that checkpoint.
- **[Risk]** Fire-and-forget dispatch means a parent execution's steps_log shows "success" for a `trigger_playbook` step even if the child later fails — an analyst glancing only at the parent could be misled about the chain's overall health.
  **[Mitigation]** This is a deliberate, named trade-off (see Alternatives Considered) in exchange for avoiding synchronous/blocking chaining's much larger cost; the parent/child linkage makes the child's real status one hop away, and this spec's Auditability section requires that linkage always be present, not optional.
- **[Risk]** A long, legitimate chain (e.g., containment → investigation → evidence-gathering) could hit `MAX_CHAIN_DEPTH = 3` and fail closed unexpectedly for a real, non-cyclic use case.
  **[Mitigation]** `MAX_CHAIN_DEPTH` is a named constant, not a hardcoded magic number scattered through the code, specifically so a future spec can revisit the exact limit with real usage data; failing closed (rather than silently truncating) at the limit is itself the safer default the design philosophy calls for.
- **[Risk]** Adding `parent_execution_id`/`chain_depth` columns, even as nullable/defaulted additions, touches the same `playbook_executions` table every other roadmap item has also extended (reliability metadata, canonical linkage) — cumulative schema growth.
  **[Mitigation]** Both columns are narrowly scoped to this capability alone, follow the exact same additive-column pattern already used for every prior extension of this table, and are the smallest structures that make ancestry/depth checkable without a graph library or a second table.

## Acceptance Criteria

- A `trigger_playbook` step, when it dispatches successfully, creates exactly one new `playbook_executions` row with the target `playbook_id`, the dispatching execution's `alert_id`, `parent_execution_id` set to the dispatching execution's id, and `chain_depth` equal to the dispatching execution's `chain_depth + 1`.
- The dispatching execution's own `trigger_playbook` step is recorded as successful once the child row is created, regardless of what the child execution later does — the parent never blocks on or is retroactively altered by the child's outcome.
- A playbook definition whose `trigger_playbook` step names its own `id` is rejected at save time.
- A dispatch attempt where the dispatching execution's `chain_depth >= MAX_CHAIN_DEPTH` fails closed with a defined error code and creates no child row.
- A dispatch attempt whose target `playbook_id` already appears among the dispatching execution's own ancestor chain (via `parent_execution_id`) fails closed with a defined error code and creates no child row, even though the definition-time check alone would not have caught it.
- The child execution's canonical decision (`soar_response_decisions`) has `parent_soar_correlation_id` set to the parent execution's `soar_correlation_id`.
- A chained child execution appears in the same incident timeline as its parent via the existing `alert_id`-based fallback in `build_readonly_incident_timeline`, with no changes to that function.
- For every alert where `_create_playbook_executions_for_alerts` produces at least one `"created"` or `"duplicate"` result, the subsequent call to `enqueue_committed_alerts` for that alert SHALL be skipped with `skip_reason: "playbook_precedence"`, and no `response_actions_queue` row SHALL be created for it.
- For every alert where no playbook matches, `enqueue_committed_alerts` SHALL behave exactly as it does today (no behavior change for uncovered alert types).
- The coverage map's one identified gap (severity floor on the `block_ip`/reputation-80 band) is explicitly recorded as resolved or explicitly accepted before any future spec is authorized to remove the queue's ingest-time trigger call.
- `engines/soar_enqueue_orchestrator.py` and `engines/soar_action_worker.py` carry a freeze/deprecation notice referencing the consolidation decision.

## Validation Plan

- `openspec validate playbook-chaining-and-cross-path-orchestration --strict` must pass as part of this spec-authoring step (no code involved).
- For the later implementation pass: registry tests (self-reference rejection, `trigger_playbook` shape validation); executor tests (successful dispatch and linkage fields, depth-cap fail-closed, ancestor-cycle fail-closed, parent success independent of child outcome, child inherits `alert_id` and thus timeline visibility); orchestrator/ingest tests (precedence guard skips queue enqueue exactly when a playbook claimed the alert, and behaves identically to today when no playbook matches); a migration smoke test for the two new `playbook_executions` columns against a populated table; and a full run of the existing playbook, queue, and ingest test suites to confirm zero regression for every alert and playbook that predates this capability.

## Overall Assessment

This audit found that both halves of this spec are smaller than they first appear, because the platform already built most of what each needs for a different original purpose. Chaining needs parent/child linkage, a depth/cycle guard, and reuse of the existing pending-execution creation path — the canonical-outcome ledger's `parent_soar_correlation_id`, the existing `(playbook_id, alert_id)` dedup index, and the existing alert-id-based timeline fallback mean the net-new surface is two columns, one new step action, and two dispatch-time checks. Cross-path orchestration needs exactly one code change of consequence — reordering two already-independent calls and threading a set of alert ids between them — because the consolidation decision already did the hard part (deciding which path wins) and the audit/outcome/dead-letter layers were already unified across both paths before this spec was written. This spec is ready for implementation once explicitly requested as a separate pass, and completes the roadmap: every item from `soar-automation-path-consolidation-decision` through this one now has a designed, reuse-grounded path to a single, authoritative, auditable SOAR orchestration layer.
