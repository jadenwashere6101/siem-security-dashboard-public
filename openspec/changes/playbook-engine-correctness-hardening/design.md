## Context

Three independent, verified correctness gaps exist in the playbook engine today. Each was re-confirmed directly against the code as part of writing this spec (not merely carried over from the audit):

1. **Missing protected-target enforcement on `block_ip`.** `engines/playbook_step_executor.py` imports `approval_store`, `dead_letter_store`, `notification_delivery_store`, `playbook_store`, `soar_response_outcomes`, and the integration adapters (lines 17–31) — it does not import `core.soar_protected_targets` anywhere. The `block_ip` step dispatches straight to `integrations.integration_registry.execute_playbook_simulated_adapter("firewall", "block_ip", ...)` (line 1042) with no call to `require_unprotected_target`. The sibling response-action-queue path (`engines/soar_action_worker.py`) does import and call this guard before its own `block_ip` execution. The two paths currently disagree on whether a protected IP can be targeted.

2. **Registry/executor action-vocabulary mismatch.** `engines/playbook_registry.py:11-21` defines `SUPPORTED_ACTIONS` — the frozenset used by `validate_playbook_steps` to accept or reject a step at definition-save time — and it does not include `notify_teams`. `engines/playbook_step_executor.py:41-47` defines a second, independent mapping, `ADAPTER_ACTIONS`, which *does* include `"notify_teams": ("teams", "send_message")`, and the executor's dispatch checks `action in ADAPTER_ACTIONS` (line 955) *before* it ever checks `action in SUPPORTED_ACTIONS` (line 958, imported from the registry at line 23). Net effect: a step with `action: "notify_teams"` is rejected by `validate_playbook_steps` at save time, but would be executed without complaint if it ever reached the executor by any path that bypasses registry validation. Two independent lists for the same concept is the root cause, not just the missing entry.

3. **Dead `attempt_count`.** `migrations/0007_soar_approval_playbook_wiring.sql` added `attempt_count INTEGER NOT NULL DEFAULT 0` and `max_attempts INTEGER NOT NULL DEFAULT 3` to `playbook_executions`. `core/playbook_store.py:551-560` (`mark_stale_execution_for_recovery`) reads both to decide whether a stale-leased execution should be requeued to `pending` (`attempt_count < max_attempts`) or given up on and marked `failed` (`else` branch). The only function that can change `attempt_count` — `update_playbook_execution_reliability_metadata` (`core/playbook_store.py:1313-1376`) — has no callers anywhere in the codebase outside its own definition (confirmed by repo-wide search). `recovery_count` *is* incremented on every stale recovery (line 568, `recovery_count = recovery_count + 1`), but `attempt_count` stays at its default `0` forever, so `attempt_count < max_attempts` (`0 < 3`) is always true and the `failed` give-up branch can never execute through this path. A step that reliably goes stale immediately after every claim (e.g. a poison-pill step) would cycle `running → pending → running` indefinitely, with only `recovery_count` climbing, and never reach a terminal state on its own.

## Goals / Non-Goals

**Goals:**
- Make playbook `block_ip` enforce the same protected-target policy the response-action queue path already enforces.
- Establish one canonical action-name vocabulary that both the registry (definition-time) and the executor (dispatch-time) read from, eliminating the class of bug that let `notify_teams` drift out of sync, not just this one instance of it.
- Make the `max_attempts` give-up path in `mark_stale_execution_for_recovery` reachable by incrementing `attempt_count` at the point an execution is stale-recovered.

**Non-Goals:**
- No new step/action types (that's `Ad Hoc Trigger & Enrichment Step` and `Conditional Branching Primitive`).
- No new playbooks or playbook content (`Core Playbook Pack v1`).
- No schema changes — `attempt_count`/`max_attempts` columns and their constraints already exist from migration 0007; this change only wires existing columns, it does not add new ones.
- No change to the response-action queue path itself (`engines/soar_action_worker.py`, `core/response_action_queue_store.py`) — this change only brings the playbook path up to the same standard, it does not touch the queue path's implementation.
- No decision revisit — `soar-automation-path-consolidation-decision` already decided the playbook engine is authoritative; this change executes on that decision's Acceptance Criterion 1, it does not re-litigate it.

## Decisions

### Protected-target enforcement placement
Call `core.soar_protected_targets.require_unprotected_target` directly inside the playbook `block_ip` step handler in `engines/playbook_step_executor.py`, immediately before dispatching to `execute_playbook_simulated_adapter`. **Alternative considered:** wait for a future shared-guard abstraction spanning both SOAR paths. **Rejected for now:** the guard function is already path-agnostic (it takes a target, not a caller-specific object), so importing and calling it directly is a same-day, low-risk fix; a shared-abstraction refactor can happen later without this fix needing to be redone, only relocated.

### Canonical action vocabulary
Introduce one shared constant (e.g., `KNOWN_PLAYBOOK_ACTIONS` or equivalent) that is the single source of truth for every action name the engine recognizes, built by combining the current `SUPPORTED_ACTIONS` (non-adapter actions: `block_ip`, `monitor`, `flag_high_priority`, `require_approval`) and `ADAPTER_ACTIONS` keys (`notify_slack`, `notify_teams`, `notify_email`, `notify_webhook`) in one place — most naturally in `engines/playbook_registry.py`, with `engines/playbook_step_executor.py` importing from it rather than maintaining its own parallel `ADAPTER_ACTIONS` action-name set independently. **Alternative considered:** simply add `"notify_teams"` to `SUPPORTED_ACTIONS` and stop there. **Rejected as insufficient:** that fixes this one instance but leaves two independently-maintained lists in place, which is the actual root cause and will recur the next time an adapter action is added.

### `attempt_count` wiring point
Increment `attempt_count` inside `mark_stale_execution_for_recovery`, alongside the existing `recovery_count = recovery_count + 1` increment, at the moment a stale execution is requeued to `pending`. **Alternative considered:** increment on every lease claim (i.e., every time `playbook_step_executor` picks up an execution to process a batch). **Rejected:** that would conflate ordinary multi-batch processing of a healthy, slow-but-progressing execution with genuine failure/retry attempts, and would make `max_attempts` trip far too early for long-running executions with many steps. Counting only stale-recovery events matches the column's evident intent (a retry-after-failure budget, not a processing-iteration counter).

## Risks / Trade-offs

- **[Risk]** Adding the protected-target check could newly block a `block_ip` step in an existing test fixture or demo scenario that currently assumes unconditional success.
  **[Mitigation]** This is exactly the intended behavior change; existing playbook tests using synthetic non-protected IPs are unaffected, and any test asserting unconditional `block_ip` success against a protected-range IP should be corrected as part of implementation, not worked around.
- **[Risk]** Consolidating the action vocabulary touches a shared import path used by both the registry and the executor; a mistake here could reject or silently misdispatch every playbook action, not just `notify_teams`.
  **[Mitigation]** The full existing playbook test suite (`tests/test_playbook_registry.py`, `tests/test_playbook_step_executor.py`, `tests/test_playbook_store.py`) already exercises every current action name and must pass unchanged except for the new `notify_teams` acceptance case.
- **[Risk]** Incrementing `attempt_count` changes real operational behavior (executions can now actually reach `permanently failed`-via-give-up sooner than before, where before they never would).
  **[Mitigation]** This is the intended fix — the give-up branch already exists and is already the documented design; making it reachable is closing a gap, not adding new risk surface. `max_attempts` already defaults to a deliberately-chosen `3`, not something newly invented by this change.

## Migration Plan

No database migration required — all three fixes operate on existing schema and existing modules. Implementation should land as three independently revertible commits/PRs (one per finding) even though they ship under one child spec, so any single fix can be rolled back without affecting the other two. Rollback of any one fix is a straightforward revert; none of the three changes depends on the others being present.

## Open Questions

- Should the canonical action vocabulary constant also be consumed by the frontend (`frontend/src/components/PlaybooksPanel.js`) create-form validation, or is server-side validation sufficient? Left to implementation — out of scope for this design decision.
- Should `max_attempts` become configurable per-playbook-definition (currently it's a per-execution column with a fixed default of 3), or is the fixed default acceptable indefinitely? Not decided here — wiring the existing column is in scope; changing its default/configurability model is not.
