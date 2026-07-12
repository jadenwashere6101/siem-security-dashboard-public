## Context

The production detection pipeline is not a single atomic transaction. `routes/ingest_routes.py` calls `engines/ingest_engine.ingest_normalized_event` (which inserts into `events` and, per matching event type, calls detector functions in `engines/detection_engine.py`/`engines/correlation_engine.py` that each run a windowed SQL aggregate over `events` and `INSERT INTO alerts`), then explicitly commits, then separately calls playbook orchestration (`engines/soar_playbook_orchestrator.py`, which inserts `playbook_executions` and `soar_response_decisions` rows), then explicitly commits again, then separately calls SOAR enqueue (`engines/soar_enqueue_orchestrator.py`, which inserts `response_actions_queue` rows), then commits again, then creates incidents (`core/incident_store.py`), then commits again.

An architecture audit of this repository (prior conversation, not restated here in full) established two load-bearing facts this design depends on:

1. Every `conn.commit()` / `conn.rollback()` call in this pipeline lives in the **route** layer (`routes/ingest_routes.py`, `routes/alerts_events_routes.py`). Zero commit/rollback calls exist inside `engines/*.py` or `core/*.py`. This means the engine-layer functions are safe to call inside a caller-owned transaction without modifying them.
2. `playbook_executions` and `response_actions_queue` rows with `status='pending'` are polled by live background workers (`engines/soar_playbook_worker.py`, `engines/soar_action_worker.py`) that call real integrations (Slack, Teams, email, webhook, firewall adapters). Any commit of a simulation-produced row is a real production action, not a hypothetical risk.

Detection threshold/window logic is expressed as SQL (`SELECT ... FROM events WHERE ... GROUP BY ... HAVING COUNT(*) >= threshold`) embedded directly in each detector function, not as a portable pure function over an in-memory event list. There are 15 such detector functions in `engines/detection_engine.py` and 2 in `engines/correlation_engine.py`.

## Goals / Non-Goals

**Goals:**

- Let an analyst paste a raw log line or JSON event, select a source and an existing detection rule set, and see the event move through the real pipeline stages with zero durable writes.
- Reuse the production parser, normalizer, detection-applicability, detection-evaluation, threshold/window, alert-generation, MITRE-mapping, and playbook-matching/response-selection logic verbatim — no forked or re-implemented detection logic for existing rules.
- Guarantee, as a hard invariant with defense-in-depth, that no simulation run can leave a row in `events`, `alerts`, `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `incidents`, `incident_alerts`, or `audit_log`.
- Explain, in the response, why a detection did or did not fire, including near-miss detail that today's detectors do not expose.
- Add a new sidebar workspace with a pipeline-stage visualization matching the real pipeline order.

**Non-Goals:**

- Custom/temporary rule authoring, a rule builder UI, Python rule execution, SQL rule execution, persistent user-created rules, a rule editor, or rule versioning. These are documented in this design's Decisions and in the proposal as future roadmap only; no implementation task in this change builds them.
- Changing production `/ingest` behavior, production alerting behavior, or any existing spec's documented behavior.
- A fully isolated (non-database) simulation evaluator. Rejected — see Decisions.
- Guaranteeing the simulation result is unaffected by real, already-committed production history for the selected source/IP. The simulator reuses the real windowed queries, so real prior events and real open alerts for the same source/IP can influence the result; this is disclosed, not hidden (see Decisions).

## Decisions

### Reuse the production pipeline inside a rollback-only transaction, not a `dry_run` flag

The simulation endpoint opens its own database connection/transaction, calls the same engine-layer functions the production ingest route calls in the same order (`ingest_normalized_event` → `match_playbooks`/playbook-execution-creation logic → response-action selection), captures every function's return value, and then **unconditionally calls `conn.rollback()`** — in the success path and in every exception path — and never calls `conn.commit()` anywhere in the simulation code path.

This works specifically because of audit fact (1) above: since no engine-layer function calls commit/rollback itself, and Postgres transactions see their own uncommitted writes (`match_playbooks` re-selecting an alert row the same transaction just inserted will see it, uncommitted), the full call chain runs correctly without any commit ever occurring.

Alternative considered: thread a `dry_run: bool` parameter through every detector function, `ingest_normalized_event`, `match_playbooks`, `enqueue_committed_alerts`, `maybe_create_or_link_incident`, and every `INSERT` call site (~20+ call sites across 6+ files) and branch on it. Rejected:
- Every new call site is a place a future change could forget the flag and accidentally allow a real write from the simulator — the failure mode is silent and only discovered in production.
- It requires modifying shared production code paths that the audit found are currently commit-free by construction; adding the flag reintroduces commit-adjacent branches into files that currently have none.
- The transaction-boundary approach makes the safety property a property of the **caller** (one function, one rollback, one place to verify), not a property that must be independently correct at 20+ call sites.

Alternative considered: build an isolated, non-database simulation evaluator that re-implements threshold/window logic in Python over an in-memory event list. Rejected — see proposal and audit: detection logic is SQL-fused, not a pure function; a from-scratch reimplementation of 17 detector queries would need continuous manual re-sync with the real detectors and would silently drift, directly contradicting the "no duplicate detection logic" requirement.

### Never route simulation through the production `/ingest` route or any function that calls `commit()`

The simulation endpoint is new route code that calls the engine functions directly. It does not call the existing `/ingest`, `/ingest/honeypot`, or related route handlers, because those handlers call `conn.commit()` internally at multiple points (confirmed by the audit: 20+ `conn.commit()` sites in `routes/ingest_routes.py`) regardless of any flag passed to them. Calling into route-handler code for simulation would either commit real data or require modifying production route commit logic — both rejected.

### Production write-boundary inventory (every write the simulation touches and never lets land)

| Table | Written by | Guard |
|---|---|---|
| `events` | `engines/ingest_engine.ingest_normalized_event` | same rollback-only transaction |
| `alerts` | detector functions in `engines/detection_engine.py`, `engines/correlation_engine.py` | same rollback-only transaction |
| `playbook_executions` | `core/playbook_store.create_pending_playbook_execution_once` (via `engines/soar_playbook_orchestrator.py`) | same rollback-only transaction |
| `soar_response_decisions` / outcome events | `core/soar_response_outcomes.py` | same rollback-only transaction |
| `response_actions_queue` | `core/ip_helpers.enqueue_response_action` (via `engines/soar_enqueue_orchestrator.py`) | same rollback-only transaction; see Open Questions on the function's post-commit assumption |
| `incidents` / `incident_alerts` | `core/incident_store.py` | same rollback-only transaction |
| `audit_log` | `core/audit_helpers.log_audit_event` | **never called by the simulator, for any purpose.** See "Resolved: no `audit_log` write of any kind" below. |

The `audit_log` row is the one write path that does **not** share the rollback-only transaction (it owns its own connection and commits itself: `get_db_connection()` + `conn.commit()` inside `log_audit_event` itself), so a call to it would be durable immediately, not discarded at rollback like every other write in this table. That is exactly why this design treats it as categorically off-limits rather than another row the transaction boundary protects.

### Resolved: no `audit_log` write of any kind (closes the prior open question)

Earlier drafts of this design carried an open question — "should the simulation endpoint write one narrow `audit_log` entry recording that an analyst ran a simulation, separate from and never including simulated pipeline data?" — defaulting to yes. That question is now closed, with the opposite answer, for two reasons:

1. **`spec.md`'s "Zero durable production writes" requirement is the authoritative behavioral contract for this capability**, and the strictest safe reading of "zero durable writes" is zero, full stop — not "zero, except one specific table under specific conditions." A narrow carve-out is a judgment call this design is not in a position to make unilaterally when a stricter, unambiguous alternative (write nothing) fully satisfies every actual requirement.
2. The narrow carve-out's own justification — "so there's a durable record that a simulation ran" — is not a requirement of any scenario in `spec.md`. Nothing in the approved requirements needs a persistent audit trail of simulation usage to function correctly.

**Settled contract:** `core/audit_helpers.log_audit_event` (or any direct write to `audit_log`) is never called anywhere in the simulation code path, for any reason — not for pipeline activity, and not for a "simulation was run" meta-entry. If non-persistent request metadata (who ran it, when, with what source/rule selection) is useful for the response or for application-level logging, it may appear in the HTTP response body or in ordinary application logs (`logger.info`/`current_app.logger`), which are operational logging, not the durable `audit_log` table this design's zero-write guarantee covers. Diagnostic output of any kind must never include pasted raw analyst input or secrets.

### Worker safety is the load-bearing invariant, not a side note

Because `playbook_executions` and `response_actions_queue` rows with `status='pending'` are polled by live workers (audit fact 2), the rollback guarantee is not merely a data-cleanliness feature — its failure mode is "a real Slack message is sent / a real firewall block is issued because of a pasted training example." The implementation must include:
- A `try/finally` (or equivalent) that guarantees `rollback()` runs even when an unexpected exception occurs mid-pipeline.
- An integration test that asserts row counts in `events`, `alerts`, `playbook_executions`, `response_actions_queue`, `incidents`, and `audit_log` are unchanged before/after a simulation run that would, on the real `/ingest` path, produce an alert and a matched playbook.
- Consideration (recorded as an open question, not committed to in V1) of a dedicated, lower-privilege database role for the simulation connection as defense-in-depth beyond the rollback guarantee.

### External API calls are stubbed for simulation in V1

`core/ip_helpers.lookup_ip_reputation` (AbuseIPDB) and `lookup_ip_location` (ip-api.com) are live third-party HTTP calls with process-level shared caches (`REPUTATION_CACHE`, `geo_cache`) also used by production ingest. Calling them from simulation would burn real API quota on arbitrary pasted/attacker IPs and could pollute the shared cache with simulation-sourced entries that a subsequent real alert then reads. V1 injects a stub/short-circuit for these two functions in the simulation code path (e.g., a fixed neutral reputation/location result, clearly labeled as simulated in the response) rather than calling the real network APIs.

### Explainability near-miss evidence: an evidence-threshold re-invocation, not detector SQL instrumentation (implemented)

Today, a detector either returns a matching row (threshold met) or returns nothing (silent no-match) — there is no "3 of 5 attempts, threshold not met" signal anywhere in the codebase. An earlier draft of this design proposed closing that gap by modifying each detector's SQL to return the raw count regardless of whether `HAVING` would exclude it. That approach was **not implemented**, in favor of a strictly safer alternative that requires **zero changes to `engines/detection_engine.py` or `engines/correlation_engine.py`**:

`engines/detection_simulator.py` maps each Version-1 rule id to the exact, unmodified production detector function that evaluates it (`RULE_ID_TO_DETECTOR`, built from direct imports of the same function objects `engines/ingest_engine.py` calls on the real `/ingest` path). When the real, real-threshold evaluation does not produce a match — and is not already explained by an existing-open-alert dedup suppression — the simulator re-invokes that *same* function a second time, on the same cursor/transaction, with only its `threshold` parameter temporarily lowered to the minimum valid value (`DETECTION_THRESHOLD_MIN`). Because every detector already returns its observed count/condition value as a field on the alert-shaped dict it produces when a row clears the (now-lowered) threshold, this reveals the true observed value using the real query, the real window, and the real rule configuration — without forking, duplicating, or reimplementing any detection logic. Any alert this evidence call inserts is discarded by the caller's unconditional rollback exactly like every other write in the simulation transaction, and its `alert_id` is never merged into the simulation's real `alerts_created` result.

When the real call *does* match, no second invocation is needed at all: the observed value is already present in the real call's own return dict, and the simulator reads it directly.

This satisfies the "byte-for-byte unchanged production alerting" constraint by construction — the production `/ingest` path never calls this function with an overridden threshold, and the detector files themselves are unmodified (verified by `git diff` producing zero output against both files). See `tests/test_detection_simulator.py::test_rule_id_to_detector_maps_to_the_exact_production_functions` for a test asserting the mapped callables are the identical function objects, not copies.

**Known, disclosed limitation:** when a match is suppressed by dedup (an existing open alert already exists for that source/rule), the evidence call would hit the same dedup guard and also return nothing, so no numeric observed value is available in that specific case. The response discloses this explicitly (`evidence_available: false`) rather than fabricating a number — the "why no alert" narrative in that case is already fully explained by the dedup disclosure itself, which does not depend on a count.

**Not instrumented:** `engines/correlation_engine.py`'s two functions (`generate_correlated_activity_alerts`, `generate_targeted_correlation_alerts`). Neither is a selectable `rule_id` in `get_detection_rule_defaults()` — they run automatically after a primary detector alert, not by direct rule selection — so they are outside this feature's "pick an existing rule" interaction model entirely, not an oversight.

### Rule scope: existing SIEM rules only for V1

Python and SQL rule execution are rejected for V1 because this codebase has no sandboxing infrastructure for either (no subprocess isolation, no resource limits, no AST allow-listing for Python; no query-shape restriction for SQL), and building that is a distinct security-engineering project disproportionate to a V1 simulator. The long-term direction (not built in this change) is a separate, isolated evaluation worker/process with no network egress and no production database credentials, fed only already-parsed/normalized event data — never a live connection to the production database or the SOAR-adjacent tables described above.

### Frontend: reuse the established sidebar-workspace pattern

The frontend workspace follows the pattern already extracted for Source Health (`add-source-health-workspace`, `build-sidebar-shell-components`, `extract-section-nav-config`, `wire-sidebar-into-app-shell`): a new entry in the shared sidebar/section configuration, a focused service module calling the new simulation endpoint, and a workspace component. No new sidebar infrastructure is introduced by this change.

## Risks / Trade-offs

- [A future engine-layer change adds a `conn.commit()` call inside a function the simulator calls, silently breaking the rollback guarantee] → The integration test in the Worker-safety decision above must run in CI on every change to `engines/*.py` and `core/*.py`, not only when this feature is touched; document this test's importance in its own docstring/comment so it is not deleted as "just a simulator test."
- [Simulation result is influenced by real, already-committed production history for the selected source/IP, surprising an analyst who expects full isolation] → Surface this explicitly in the response payload and UI (e.g., "this result reflects real recent activity for this source" and "suppressed by existing open alert" reasoning) rather than presenting the result as fully isolated.
- [`enqueue_response_action`'s docstring assumes post-commit invocation] → **Resolved: moot.** The implementation never calls this function; SOAR preview reads the already-computed `response_action` field off the alert row instead.
- [An evidence-threshold re-invocation for near-miss reasoning accidentally changes which rows are inserted as real alerts] → **Resolved by construction, not just by testing.** The evidence call only ever runs from `engines/detection_simulator.py`, inside the simulator's own rollback-only transaction, and only for the one rule the analyst selected; the production `/ingest` path never invokes any detector with an overridden threshold. `engines/detection_engine.py` and `engines/correlation_engine.py` have zero lines changed (confirmed via `git diff`), so there is no modified `HAVING`-filtered result set to regress — the full existing detection-engine test suite passes unchanged as direct proof.
- [Performance: simulation queries still do full windowed scans of the real `events`/`alerts` tables] → No new indexes are anticipated since these are the same queries production already runs at the same or lower frequency; if evidence shows otherwise during implementation, treat as an explicit review gate rather than adding an index unreviewed.
- [Frontend/backend contract drift as pipeline stages are added in Phase 5] → Define the simulation response schema once in Phase 1 covering all stages up front (even before Phase 5's visualization consumes every field), so the frontend is not chasing an evolving backend shape stage-by-stage.
- [Production drift: future changes to shared detector/playbook logic silently change simulator behavior] → Accepted trade-off of "reuse, don't fork" (see proposal); mitigated by the same test suite covering both the production path and the simulation path calling the same functions.

## Migration Plan

1. Mac AI implements and verifies the backend simulation endpoint, rollback-transaction orchestration, external-API stubbing, and near-miss instrumentation, with focused tests including the zero-durable-write integration test.
2. Mac AI implements and verifies the frontend Detection Simulator workspace, pipeline visualization, and explainability presentation.
3. Mac AI runs focused and full regression suites, production build, browser verification, `git diff --check`, and strict OpenSpec validation.
4. After explicit authorization, commit and push the approved Mac revision.
5. VM AI performs clean-tree preflight, syncs only the approved commit, deploys backend then frontend, and verifies the simulation endpoint and workspace with read-only production-safe checks (no synthetic events sent to the real `/ingest` path, no real detection rules mutated).

Rollback is code-only: restore the prior backend/frontend revision and remove the new route/navigation entry by deploying the prior approved artifact. No schema or data rollback is expected, since this change adds no migration and no durable data.

## Open Questions

- Should the simulation database connection use a dedicated, lower-privilege role as defense-in-depth beyond the rollback guarantee, or is the rollback guarantee (plus the integration test) sufficient for V1? Default: rollback-only for V1; revisit if evidence reveals gaps. **Still open** — not revisited in Implementations 1–3; the zero-durable-write integration tests have not surfaced a gap the rollback boundary alone doesn't already close.

### Resolved (previously open)

- ~~Does `core/ip_helpers.enqueue_response_action` behave correctly against an uncommitted same-transaction alert row?~~ **Moot.** The implemented SOAR preview never calls `enqueue_response_action` at all — it reads the `response_action` field the real detector already computed and stored on the (uncommitted) alert row, so this function is never invoked from the simulation path and there was nothing to verify.
- ~~Should the simulation endpoint write one `audit_log` entry?~~ **Resolved: no.** See "Resolved: no `audit_log` write of any kind" above.
- ~~Which role boundary is correct?~~ **Resolved: `analyst_or_super_admin_required`**, implemented and verified (backend RBAC tests, frontend `sectionsConfig` role matrix, live browser session as super_admin).
