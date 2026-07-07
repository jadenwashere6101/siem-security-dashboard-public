## Context

### Current schedule-related code inventory

Re-verified directly against the code as part of writing this spec:

| Layer | File | What exists |
|---|---|---|
| Schema | `migrations/0006_soar_playbooks.sql` | `playbook_schedules` table: `playbook_id` FK, `schedule_expression`, `timezone`, `enabled`, `paused`, `next_run_at`, `last_run_at`, `last_success_at`, `last_failure_at`, `last_scheduled_execution_id`, `missed_run_policy` (CHECK `skip|record_only|run_once`), `max_catchup_runs`, `max_concurrent_runs`, plus three indexes. |
| Store | `core/playbook_store.py:764-940` (approx.) | `create_playbook_schedule`, `get_playbook_schedule`, `list_playbook_schedules`. No update/pause/delete function exists at all. |
| Routes | `routes/playbook_routes.py:341-406` | `GET /playbook-schedules` (list) and `GET /playbook-schedules/<id>` (detail) only. **No `POST`, `PATCH`, or `DELETE` route exists for schedules anywhere in the codebase.** |
| Frontend service | `frontend/src/services/playbookService.js:168-205` | Read-only fetch wrappers for the two `GET` routes only. |
| Frontend UI | `frontend/src/components/PlaybooksPanel.js` | A "Schedules" tab (list view, line ~720) and a detail view (line ~1091), both explicitly labeled: *"Schedules are metadata-only. No scheduler or daemon exists, and these records do not execute playbooks."* (line 1000) and *"Metadata-only schedule visibility. This record does not execute a playbook."* (line 1094). |
| Tests | `tests/test_playbook_store.py`, `tests/test_playbook_routes.py` | Exercise `create_playbook_schedule`/`get_playbook_schedule`/`list_playbook_schedules` directly (store-level) and the two `GET` routes (RBAC, filters, shape). Tests are the *only* callers of `create_playbook_schedule` in the entire repository. |
| Execution consumers | *(none found)* | Repo-wide search for `next_run_at`/`schedule_expression` outside `core/playbook_store.py` and `routes/playbook_routes.py` returns zero matches. `engines/soar_playbook_worker.py`, `scripts/soar_playbook_worker_daemon.py`, and `scripts/run_playbook_executor_once.py` contain no reference to `playbook_schedules` at all. |

### What `playbook_schedules` currently does

Stores schedule metadata rows — a cron-like expression, timezone, enable/pause flags, missed-run policy, catch-up/concurrency limits, and run-history timestamps — and exposes them for **read-only** display via two API routes and one frontend tab, which the UI itself labels as non-executing.

### What it does not do

- Cannot be created through the product: no route calls `create_playbook_schedule`; it is reachable only via direct test invocation or manual database access.
- Cannot be updated, paused, or deleted through any route or store function — none exist.
- Never triggers a playbook execution: no process anywhere reads `next_run_at` or `schedule_expression` to decide when to run something. There is no scheduler daemon, cron process, or polling loop for this table anywhere in the codebase.

### Whether any UI/API depends on it

Yes, but only for read-only display: the two `GET` routes and the frontend "Schedules" tab/detail view read from it. Nothing in the SOAR execution pipeline — `engines/soar_playbook_orchestrator.py`, `engines/soar_playbook_worker.py`, `engines/playbook_step_executor.py` — depends on or reads this table. Removing it would affect only the display surface, not any executing behavior, since none currently reads from it to execute anything.

### Whether scheduled playbooks are valuable for this project right now

Not right now. Two things would need to be true for a scheduler to add real value, and neither is: (1) a real playbook library to schedule — per the original audit, `playbook_definitions` has zero persisted rows today, and `Core Playbook Pack v1` (the roadmap item that adds real content) has not yet been implemented; (2) a demonstrated need for *time-based* automation distinct from the playbook engine's existing *alert-triggered* automation (`trigger_config` matching on ingest) — none of the missing-playbook scenarios identified in the audit require a schedule rather than an alert trigger. Building a scheduler now would be the same class of premature engineering the original audit criticized in the opposite direction (an engine with no content) — here it would be a capability with no content and no proven need.

## Goals / Non-Goals

**Goals:**
- Decide, once, whether `playbook_schedules` should be finished or retired, using SOC-architect judgment (realistic value vs. interview-quality cost of dead surface), not sunk-cost preservation.
- Define what "retired" or "finished" concretely means for this codebase's routes, store functions, frontend, and tests, so a later implementation pass has an unambiguous target.
- Leave the door open to real scheduled playbooks later, against actual requirements, without pretending this attempt was that design.

**Non-Goals:**
- Not building a scheduler, not deleting any file, not modifying schema, not modifying the frontend, and not running a migration — all deferred to a later, explicitly-requested implementation pass under this same child spec.
- Not deciding the fate of any other roadmap item (new playbooks, chaining, branching, ad hoc triggers, evidence collection, queue retirement, deployment work) — out of scope, per the parent roadmap.
- Not re-litigating the `soar-automation-path-consolidation-decision` or `playbook-engine-correctness-hardening` decisions — this item has no dependency on either.

## Decisions

### Recommendation: retire the surface (Option B), not finish the scheduler (Option A)

**Selected: Option B — retire the unused schedule surface.**

Rationale:
1. The write path is already unreachable in production (no route calls `create_playbook_schedule`), so this isn't a "paused mid-build" feature with real users depending on it — it is schema, a store function, and a display view with no way to populate real data through the app itself.
2. There is no content to schedule yet (`Core Playbook Pack v1` hasn't shipped) and no demonstrated need for time-based (vs. alert-triggered) automation among any of the missing-playbook scenarios the audit identified.
3. A disclosed-but-permanently-inert UI panel is a worse interview answer ("we knew it didn't work and left it") than a clean surface with no such panel — dead surface is a cost even when honestly labeled, because "why does this exist" is still the first follow-up question it invites.
4. Retiring is low-risk: nothing in the execution pipeline reads this table, so removing the read-only display and the unreachable write path has zero blast radius on working functionality.
5. This does not foreclose scheduled playbooks permanently — it is explicitly a "not now" call. If a genuine time-based automation need emerges after `Core Playbook Pack v1` ships, it should be designed fresh against real requirements, not retrofitted onto this orphaned attempt.

### Alternatives considered

- **A. Finish the scheduler properly.** Rejected for now: would require a real scheduler daemon (cron parsing, catch-up-policy execution, concurrency-limit enforcement, a create/update/pause/delete API, and frontend authoring UI) built speculatively, ahead of any real playbook content to schedule and any demonstrated need beyond alert-triggered automation. This is a legitimate future capability, not a bad idea — just premature relative to the rest of this roadmap.
- **B. Retire the unused surface.** Selected — see rationale above.
- **C. Leave as-is (status quo).** Rejected: the frontend already discloses non-functionality, which is the least-bad version of "do nothing," but leaving it in place doesn't resolve the audit finding and keeps inviting "why does this exist" scrutiny indefinitely, with an unreachable write path and dead store code left unaddressed.
- **D. Hide the frontend tab but leave schema/store/routes in place.** Rejected: only hides the symptom. The unreachable `create_playbook_schedule` function and the two read-only routes would remain as orphaned surface, and a future engineer reading the routes/store file (not just the UI) would still find dead code with no consumer.

## Implementation Boundaries (for the later implementation phase)

**In scope for that later phase:**
- Remove `GET /playbook-schedules` and `GET /playbook-schedules/<id>` from `routes/playbook_routes.py`.
- Remove or clearly mark deprecated the `create_playbook_schedule`, `get_playbook_schedule`, `list_playbook_schedules` functions in `core/playbook_store.py` once their only callers (routes and tests) are removed/updated.
- Remove the "Schedules" tab and detail view from `frontend/src/components/PlaybooksPanel.js` and the corresponding fetch wrappers from `frontend/src/services/playbookService.js`.
- Update or remove the schedule-specific tests in `tests/test_playbook_routes.py` and `tests/test_playbook_store.py` so the suite reflects the retired surface rather than testing removed behavior.
- Decide, as a lower-priority, optional follow-up, whether to drop the `playbook_schedules` table via a forward-only migration, or leave the (now fully orphaned, zero-consumer) table in schema as inert debt. This is not required to resolve the audit finding, since the interview-facing risk lives in the reachable API/UI layer, not in raw schema nobody reviews directly — but it is not excluded either.

**Out of scope (per this spec and the parent roadmap):**
- New playbooks or playbook content.
- Playbook chaining, conditional branching, ad hoc triggers, evidence collection.
- Queue retirement or any response-action-queue work.
- Backend migrations beyond the optional table-drop noted above.
- UI redesign beyond removing the Schedules-specific views.
- Deployment work.

## Risks / Trade-offs

- **[Risk]** A future roadmap item silently assumed `playbook_schedules` would exist and be finished.
  **[Mitigation]** Repo-wide search confirms no other code path or child spec in this roadmap depends on it being present or functional; the parent roadmap's dependency notes list this item as independent.
- **[Risk]** Removing the UI/API surprises an operator who bookmarked or relied on the Schedules view.
  **[Mitigation]** Since no real schedule rows can exist in production today (no reachable create path), the practical impact of removal is limited to losing a display of test/manually-inserted data, not any working feature.
- **[Risk]** A genuine future need for scheduled playbooks requires rebuilding from scratch instead of finishing this attempt.
  **[Mitigation]** Accepted trade-off: a fresh design against real requirements (post `Core Playbook Pack v1`) will produce a better scheduler than retrofitting an already-orphaned write path, and the schema can optionally remain as a reusable starting point if not dropped.
- **[Risk]** Removing store functions that tests currently call breaks the test suite if not updated in the same pass.
  **[Mitigation]** Implementation boundaries explicitly include updating/removing the corresponding tests in the same implementation pass, not as a follow-up.

## Migration Plan

Not applicable to this spec-creation step — no code or schema changes are made here. When the later implementation phase executes: no destructive migration is required to remove routes/store functions/UI (pure code removal, revertible via version control); the optional schema-table drop, if pursued, should be a separate forward-only migration, landed independently from the code-removal changes so the two can be reviewed and reverted separately.

## Open Questions

- Should the `playbook_schedules` table be dropped in the same implementation pass as the code/UI removal, or left as inert schema until a real scheduling need justifies either finishing or formally dropping it? Left open — recommendation leans toward leaving it (lower risk, optional), but not mandated here.
- If scheduled playbooks are revisited later, should they reuse this table's shape (`missed_run_policy`, `max_catchup_runs`, `max_concurrent_runs` are reasonable primitives) or be redesigned from scratch alongside whatever real use case drives them? Left to that future spec.
