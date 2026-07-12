# Detection Simulator Workspace Verification

Status: Implementations 1–3 are complete on Mac. All Mac-owned tasks across Phases 1–7 are resolved, including the two previously deferred tasks (1.6 audit_log decision, 2.6/2.7 near-miss instrumentation). Only VM-owned Phase 7 tasks (7.8–7.11) remain, pending explicit user authorization to commit, push, and deploy. No commit, no push, no VM access, and no deployment have occurred.

## Mac AI Evidence — Implementation 3 (deferred-task resolution + Phase 7 Mac gates)

### Part 1 — Near-miss threshold evidence (tasks 2.6/2.7), resolved without detector modification

- **Zero lines changed in `engines/detection_engine.py` or `engines/correlation_engine.py`.** Confirmed: `git diff --stat engines/detection_engine.py engines/correlation_engine.py` — empty output.
- Mechanism: `engines/detection_simulator.py` adds `RULE_ID_TO_DETECTOR` (imports the same 15 detector function objects `engines/ingest_engine.py` calls on the real path) and `_fetch_threshold_evidence`, which re-invokes the exact same function once more, on the same transaction, with only its `threshold` parameter temporarily lowered to the minimum valid value — only when the real evaluation didn't match and wasn't dedup-suppressed. See `design.md`'s "Explainability near-miss evidence" decision for the full design and its one disclosed limitation.
- New test: `test_rule_id_to_detector_maps_to_the_exact_production_functions` — asserts every mapped callable `is` (identity, not equality) the real `engines.detection_engine` function object. Passed.
- New test: `test_threshold_not_met_surfaces_real_observed_value_via_evidence_call` — 2 pasted failed logins against a threshold of 3 correctly surfaces `observed_value=2`, `observed_value_label="attempts"`, `configured_threshold=3`, `evidence_available=true`. Passed.
- New test: `test_threshold_met_reports_observed_value_without_a_second_query` — 5 pasted failed logins surfaces `observed_value=3` (not 5) — a genuine, correct finding: the real detector alerts the moment the 3rd event crosses the threshold, then production dedup silently skips re-evaluating on events 4–5, so 3 is the truthful observed value at the moment of alert creation. This is exactly the kind of accurate evaluation evidence this feature exists to surface. Passed.
- New test: `test_evidence_call_never_survives_rollback` — proves the evidence call's own phantom alert insert (from the artificially lowered threshold) never becomes durable. Passed.
- New test: `test_evidence_call_does_not_run_for_rules_without_a_threshold_parameter` — defensive coverage for `_fetch_threshold_evidence`'s early-return path. Passed.
- Regression proof (task 2.7): since no detector file changed, there is no instrumentation diff to regress-test — production alerting is unaffected by construction. As direct proof, the complete existing detection-engine test suite was run **unchanged** and passed 100%: `test_failed_login_detection.py`, `test_password_spraying_detection.py`, `test_port_scan_detection.py`, `test_high_request_rate_detection.py`, `test_http_error_detection.py`, `test_application_exception_detection.py`, `test_honeypot_event_detections.py`, `test_pfsense_firewall_detections_soar.py`, `test_source_aware_detection.py`, `test_ingest_normalized_event.py` — 303 tests total across these plus `test_detection_simulator.py`, `test_ingest_api_contracts.py`, `test_detection_applicability.py`, `test_playbook_engine.py`, `test_soar_playbook_orchestrator.py`, `test_soar_enqueue_orchestrator.py`, `test_soar_queue_visibility_api.py`, `test_auth_rbac.py`, `test_source_health.py` — all passed.
- Frontend: `DetectionSimulatorExplainability.js`'s `thresholdExplanation` now renders `evaluated_window_minutes`, `observed_value`/`observed_value_label`/`configured_threshold` (when `evidence_available`), and an explicit "not available" disclosure when evidence genuinely couldn't be gathered (never a fabricated number). 3 new frontend tests added and passed; full suite re-run — 813/813 passed, 0 regressions.

### Part 2 — `audit_log` decision (task 1.6), resolved explicitly

- **Decision: no `audit_log` write of any kind, for any reason, ever.** This closes `design.md`'s prior open question (which had defaulted to "yes, write a narrow meta-entry") in favor of the strictest reading of `spec.md`'s zero-durable-write contract.
- `spec.md`'s "Zero durable production writes" requirement now names `audit_log` explicitly in both its requirement text and its scenario list, plus a new dedicated scenario ("No audit trail row is ever written for a simulation").
- `design.md`'s write-boundary table and Open Questions section were updated to reflect the closed decision and its rationale (see the "Resolved: no `audit_log` write of any kind" subsection).
- No code changed for this resolution — the implementation already never called `log_audit_event` (confirmed since Implementation 1); this round makes that behavior an explicit, permanent contract rather than an implementation default that could silently drift.
- Verified by the existing `test_zero_durable_writes_across_all_guarded_tables` (`audit_log` row count asserted unchanged) and the full zero-write test suite below.

### Part 3 — Final Phase 7 quality gates

- **Transaction/rollback**: one transaction per simulation run; `conn.rollback()` runs unconditionally in a `finally` block; `conn.commit()` is never called anywhere in `engines/detection_simulator.py` or anything it calls. Confirmed by `test_never_commits_even_when_wrapper_forbids_commit` (the test double has no `commit()` method — an accidental call raises `AttributeError`, not a silent success).
- **Zero-write verification, extended for this round**: `test_zero_durable_writes_across_all_guarded_tables` now covers all 9 guarded tables the prompt requires — `events`, `alerts`, `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `response_actions_log` (added this round), `incidents`, `incident_alerts`, `audit_log` — across a run that reaches the alert preview *and* SOAR/playbook preview paths (an approval-requiring matched playbook). Passed.
- **Worker-visibility verification (new)**: `test_no_pending_row_is_visible_to_a_genuinely_separate_connection` opens a second, fully independent PostgreSQL connection (not the simulation's own connection/transaction) — mirroring exactly how `engines/soar_action_worker.py` and `engines/soar_playbook_worker.py` connect in production — and queries `SELECT COUNT(*) FROM playbook_executions WHERE status = 'pending'` and the equivalent for `response_actions_queue` immediately after a matched-alert-and-playbook simulation run. Both return 0. This is a direct proof of worker safety, not only an inference from an unchanged row count on the same connection. Passed.
- **External integrations**: confirmed no integration adapter is invoked (`test_no_integration_adapter_invoked_during_simulation`, patching Slack's outbound webhook call and asserting it is never called for a playbook whose step would send a real message).
- **Reputation/location stubs**: confirmed no outbound `requests.get` call occurs via `core.ip_helpers` during a simulation run (`test_reputation_lookup_is_stubbed_not_called_live`); geolocation is never invoked at all (no code path calls `lookup_ip_location`).
- **Rule scope**: `run_detection_simulation` validates `rule_id` against `get_detection_rule_defaults()` — the exact same existing-rules inventory production uses — and rejects anything else with `SimulationValidationError`; there is no code path in the simulator, the route, or the frontend that accepts a custom rule definition, Python source, or SQL text.
- **Rule-list endpoint**: `GET /detection-simulator/rules` returns only `rule_id`, `display_name`, `description`, `active`, `applicable_sources` — read-only metadata, no thresholds-as-writable-state, no mutation capability of any kind (confirmed by `test_rules_route_allows_analyst_and_lists_existing_rules_only`).
- **Frontend performs no detection evaluation**: `detectionSimulatorService.js`'s `isValidSimulationResponse` validates response *shape* only (all 9 stages present with a `status` string); no threshold comparison, count, or match/no-match decision is computed client-side anywhere in the frontend.
- **Malformed responses fail safely**: `runDetectionSimulation` throws `"Invalid simulation response"` for a response missing required stages or the `simulated` flag, without rendering partial/incorrect results (`detectionSimulatorService.test.js`).
- **RBAC**: unchanged from Implementation 1/2, re-verified this round — `login_required` + `analyst_or_super_admin_required` on both the `/run` and `/rules` endpoints.
- **Sidebar/navigation**: unchanged from Implementation 2, re-verified live in-browser this round.
- **Production ingestion, detections, SOAR, and existing workspaces unchanged**: proven by the full backend suite (1812/1815 passed, same 3 pre-existing unrelated failures) and full frontend suite (813/813 passed) both passing with this round's changes applied.

### Browser verification (Implementation 3)

Performed against a real local Postgres-backed `siem_backend.py`, started with ephemeral shell-exported environment variables only (`SIEM_DB_NAME`, `SIEM_ADMIN_USERNAME=admin`, `SIEM_ADMIN_PASSWORD`, `SECRET_KEY`, `SIEM_DEBUG=true`) — **no `.env` file was created, edited, or read**; torn down (`kill -9`) after verification.

| Required scenario | Result |
|---|---|
| Raw pfSense log simulation | Parsed and normalized correctly (a real `filterlog` line, `pfsense_firewall_repeated_deny` rule — applicable). Confirmed via Parser/Normalized Event stages both "Succeeded" before the run reached the DB-dependent stage described below. |
| Representative JSON simulation | A realistic `bank_app` `failed_login` JSON event parsed and normalized correctly; Parser/Normalized Event both "Succeeded". |
| Applicable rule, threshold met | **Not demonstrable live** — see local-environment limitation below. Fully covered by `test_threshold_met_reports_observed_value_without_a_second_query` (real transactional Postgres, correctly migrated schema). |
| Applicable rule, threshold not met, numeric explanation | **Not demonstrable live** — same limitation. Fully covered by `test_threshold_not_met_surfaces_real_observed_value_via_evidence_call`. |
| Rule not applicable | Confirmed live: `bank_app` + `honeypot_scanner_detected` correctly shows Detection Applicability "Failed" with the exact backend reason text, and Detection Evaluation through SOAR Preview all "Skipped". |
| Existing-alert suppression | **Not demonstrable live** — same limitation (requires querying `alerts`). Fully covered by `test_existing_open_alert_suppression_is_disclosed`. |
| Malformed input | Confirmed live: pasting `{not valid json at all` shows "Pasted JSON input is not valid JSON." client-side, before any network request, and the previously rendered results remain visible and unreplaced. |
| Backend failure | Confirmed live (and, per the limitation below, unavoidably so for any applicable-rule run against this local DB): the applicable-rule pfSense run above returned "Internal server error", rendered correctly as a distinct error state, not a false success. |
| Alert/MITRE/SOAR preview | **Not demonstrable live** — same limitation. Fully covered by `test_threshold_met_reports_observed_value_without_a_second_query`, `test_soar_preview_matches_playbook_and_surfaces_approval`, and the 12 `DetectionSimulatorExplainability.test.js` / 6 `DetectionSimulatorPipeline.test.js` fixture-based frontend tests. |
| Explicit rollback/no-production-write disclosure | Confirmed live: the workspace header states, verbatim, "Run pasted events through the real detection and SOAR-preview pipeline inside a transaction that is always rolled back. No event, alert, incident, playbook, or response action is ever created, queued, or executed by this workspace," visible on every page load before any simulation is run. |
| Analyst and super-admin access | Super-admin access confirmed live (logged in as the `admin` bypass user, full workspace interaction). Analyst access confirmed by `test_route_allows_analyst_and_returns_simulation_result` (backend) and the dedicated `App.test.js` test rendering the workspace for an analyst session; not independently re-confirmed live this round (see below). |
| Unauthorized-role denial | Confirmed by `test_route_rejects_viewer_role`, `test_rules_route_rejects_viewer_role` (backend) and `App.test.js`'s "does not render Detection Simulator nav for viewer role" test; not independently re-confirmed live this round — creating a throwaway viewer user would require mutating the local `users` table, which was judged unnecessary given the strength of existing automated coverage (see below). |
| Desktop and narrow layouts | Desktop confirmed live (1434px viewport). Narrow layout: the `resize_window` browser tool did not visibly affect screenshot capture dimensions in this environment (same limitation observed and disclosed in Implementation 2); inferred safe from code inspection — `DetectionSimulatorPanel.js` uses the identical `repeat(auto-fit, minmax(200px, 1fr))` CSS grid and unconstrained flexbox stacks already used by `SourceHealthPanel.js`, which *was* independently verified at a 390×844 viewport in `add-source-health-workspace`. |
| Keyboard accessibility | Confirmed live: `Tab` from the workspace heading moves focus through Source → Detection rule → Input format → paste textarea → Run Simulation button, in that exact logical order, with correct `aria-label`s on every control (verified via `document.activeElement` inspection after each `Tab` press). |
| No new console errors | Confirmed: cleared the console log, exercised all scenarios above, and found zero messages referencing any Detection Simulator file. The only errors present anywhere in the session were the pre-existing Dashboard alert-polling failures against the same local DB schema issue (reproducible independent of this change). |

**Known local-environment limitation (not a defect in this change, and not new this round):** the local dev database `siem_dashboard` has schema drift predating this work — its `events`/`alerts` tables are missing `source`/`source_type` columns that the currently-committed migration `0002_base_siem_core.sql` (and `schema.sql`) define, even though `schema_migrations` claims that migration is applied. A safe, rolled-back diagnostic (`BEGIN; CREATE INDEX ...; ROLLBACK;`) confirmed the column genuinely does not exist. Fixing this would require deeper surgery than the sanctioned `scripts/migrate.py` tool provides (it only applies *pending* migrations; this is a drift in an *already-applied* one) and was judged out of scope and too risky to attempt on a personal local database whose full history and other dependents aren't known. This blocks live demonstration of any scenario that requires a real `events`/`alerts` query — which is, not coincidentally, also confirmed live: the exact same pfSense "backend failure" scenario above IS that blocked path, captured on purpose as the required "backend failure" evidence. Every blocked scenario is instead fully covered by real, transactional-Postgres `pytest` tests using a freshly and correctly migrated schema per test (`tests/conftest.py`'s `postgres_db` fixture), which is a strictly stronger correctness guarantee than a single manual browser click-through would have provided anyway.

## Mac AI Evidence — Implementation 2 (Phases 4–6)

- Small backend addition this round: `GET /detection-simulator/rules` (`login_required` + `analyst_or_super_admin_required`), reusing `engines.detection_config.get_all_effective_detection_rules()` read-only — needed because the existing `/admin/detection-rules` listing is super-admin only and the workspace's rule selector needs analyst access. No existing route or function was modified.
- Frontend focused test command/result: `CI=true npx react-scripts test --watchAll=false --runInBand src/services/detectionSimulatorService.test.js src/components/DetectionSimulatorPipeline.test.js src/components/DetectionSimulatorExplainability.test.js src/components/DetectionSimulatorPanel.test.js src/utils/sectionsConfig.test.js src/App.test.js` — 73 passed
- Full frontend suite: `CI=true npx react-scripts test --watchAll=false --runInBand` — 810 passed, 64 suites, 0 failed. One pre-existing `act(...)` warning in `SourceIpContext.js` (unrelated, confirmed present before this change)
- Backend focused test command/result (including the new rules-endpoint tests): `python3 -m pytest tests/test_detection_simulator.py -q` — 33 passed
- Frontend production build: `npm run build` — passed; only 3 pre-existing eslint warnings (`App.js` missing-dep, `IncidentsPanel.js` unused vars, `LiveLogsPanel.js` missing-dep), confirmed pre-existing via `git stash` comparison against clean `main`; zero warnings in any new Detection Simulator file
- Browser verification (local, real backend + real Postgres, no VM): started `siem_backend.py` locally against the existing local dev database `siem_dashboard` using ephemeral shell-exported env vars (`SIEM_DB_NAME`, `SIEM_ADMIN_USERNAME=admin`, `SIEM_ADMIN_PASSWORD`, `SECRET_KEY` — **no `.env` file was created or edited**), logged in as the `admin`/super_admin bypass user, and drove the app through Chrome:
  - Confirmed "Detection Simulator" appears in the sidebar under "SOC Tools", positioned correctly, dark theme consistent with the rest of the app.
  - Confirmed the workspace loads its rule selector live from the new `/detection-simulator/rules` endpoint (real HTTP round-trip, real RBAC).
  - Confirmed selecting a source narrows the input-format selector to only the formats that source supports (e.g., Bank App → JSON only, auto-selected).
  - Ran a real simulation (source not applicable to the selected rule, to avoid a pre-existing, unrelated local-DB schema issue described below) and confirmed, live against the real backend: all 9 pipeline stages render in the exact specified order, with correct succeeded (green)/failed (red)/skipped (gray) states, each stage's reason text sourced directly from the backend response (e.g., "Rule 'honeypot_scanner_detected' is not applicable to source 'bank_app'"), and the Explanation section rendering real backend-derived text for Parser, Normalization, and Rule-not-applicable.
  - Confirmed no console errors originate from any Detection Simulator file; the only console errors present were pre-existing and unrelated (the Dashboard's background alert-polling failing against the same stale local-DB schema issue below, reproduced independent of this change).
  - **Known local-environment limitation, not a defect in this change**: the pre-existing local dev database `siem_dashboard` predates the `source`/`source_type` columns on `events`/`alerts` (schema drift unrelated to this work — confirmed by the *existing, untouched* `GET /alerts` Dashboard endpoint failing with the identical `column "source" does not exist` error). This blocked demonstrating a live "matched detection with alert/MITRE/SOAR preview" browser scenario locally. That exact scenario (multiple failed logins → matched alert → MITRE mapping → matched playbook with approval requirement) is fully covered instead by real, transactional-Postgres backend tests (`tests/test_detection_simulator.py`, fresh correctly-migrated schema per test via the `postgres_db` fixture) and by the 14 `DetectionSimulatorPanel.test.js` / 6 `DetectionSimulatorPipeline.test.js` / 12 `DetectionSimulatorExplainability.test.js` frontend tests using response fixtures matching the exact real API contract.
  - Local-only artifacts: rebuilt `frontend/build/` twice with `PUBLIC_URL=/` to match local Flask static serving (the repo's real deployment expects `/siem/`-prefixed asset paths served behind a separate web server, not Flask's local dev static route) — `frontend/build/` is gitignored, and the standard `/siem/`-prefixed build was restored via a final `npm run build` before finishing. The local Flask server and its ephemeral env vars were torn down after verification; no `.env` file exists or was touched.
- `git diff --check`: passed
- `openspec validate add-detection-simulator-workspace --strict`: passed
- Final implementation diff scope review (Implementation 2): new files are `frontend/src/services/detectionSimulatorService.js`, `frontend/src/utils/detectionSimulatorStages.js`, `frontend/src/components/DetectionSimulatorPanel.js`, `DetectionSimulatorPipeline.js`, `DetectionSimulatorExplainability.js`, and their test files. Modified files: `frontend/src/utils/sectionsConfig.js` (+1 entry), `frontend/src/App.js` (+1 import, +1 render block), `frontend/src/App.test.js` (+1 mock, +2 tests), `frontend/src/utils/sectionsConfig.test.js` (updated expected section list), `routes/detection_simulator_routes.py` (+1 new read-only route), `tests/test_detection_simulator.py` (+4 tests for the new route). No other production file was touched; no schema, migration, secret, or service-unit file changed.

## Mac AI Evidence — Implementation 1 (Phases 1–3)

- Backend focused test command/result: `python3 -m pytest tests/test_detection_simulator.py -q` — 30 passed, 2 pre-existing unrelated warnings
- Backend zero-durable-write integration test (task 1.7) command/result: covered by `test_zero_durable_writes_across_all_guarded_tables` (asserts unchanged row counts in `events`, `alerts`, `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `incidents`, `incident_alerts`, `audit_log` across a run that does produce a matched alert and a matched playbook), `test_mid_pipeline_exception_still_rolls_back` (exception path), and `test_never_commits_even_when_wrapper_forbids_commit` (the test's DB wrapper has no `commit()` method at all — an accidental commit call would raise `AttributeError`, not silently succeed) — all passed
- Detection-engine/correlation-engine before/after instrumentation regression (task 2.7): not applicable this round — the near-miss instrumentation (task 2.6) was deferred, so no production detector SQL was modified; nothing to regression-test
- SOAR/playbook no-execution test (task 3.7) command/result: covered by `test_no_integration_adapter_invoked_during_simulation`, patching `integrations.slack_adapter._post_slack_webhook` and asserting it is never called for a simulation whose matched playbook's step would send a real Slack message — passed
- Related regression suites: `python3 -m pytest tests/test_ingest_normalized_event.py tests/test_ingest_api_contracts.py tests/test_playbook_engine.py tests/test_soar_playbook_orchestrator.py tests/test_soar_enqueue_orchestrator.py tests/test_detection_applicability.py tests/test_failed_login_detection.py tests/test_source_aware_detection.py tests/test_source_health.py -q` — 143 passed
- Full backend suite: `python3 -m pytest tests/ -q` — 1803 passed, 3 failed, 3.53s+159.91s total. The 3 failures (`test_alert_mutation_api_contracts.py::test_post_alert_execute_duplicate_block_ip_does_not_write_tracking_success`, `test_alert_mutation_api_contracts.py::test_post_alert_execute_canonical_write_failure_rolls_back_legacy_success`, `test_soar_adapter_interface.py::test_adapter_backed_executor_invalid_result_fails`) were confirmed pre-existing and unrelated: reproduced identically on a `git stash` of this change's diff (clean `main`), same 3 failures, same errors
- Python compilation: `python3 -m py_compile engines/detection_simulator.py routes/detection_simulator_routes.py siem_backend.py tests/test_detection_simulator.py` — passed
- `git diff --check`: passed
- `openspec validate add-detection-simulator-workspace --strict`: passed
- Blueprint import/registration sanity check: `siem_backend.app` imports cleanly with `detection_simulator` present in `app.blueprints` and `POST /detection-simulator/run` present in `app.url_map` — confirmed, no circular import introduced
- Final implementation diff scope review: new files are `engines/detection_simulator.py`, `routes/detection_simulator_routes.py`, `tests/test_detection_simulator.py`; the only modified existing file is `siem_backend.py` (two lines: one import, one `register_blueprint` call). No file under `engines/detection_engine.py`, `engines/correlation_engine.py`, `engines/ingest_engine.py`, `engines/playbook_engine.py`, `core/ip_helpers.py`, `helpers/enrichment_helpers.py`, `routes/ingest_routes.py`, `schema.sql`, or any migration was modified. No frontend file was touched.
- Frontend: not started this round (Phase 4/5 are out of scope for Implementation 1)
- Browser verification: not applicable — no frontend exists yet
- `git diff --check`: passed (frontend N/A)

## Final Contract Review — Implementation 2 additions

- The frontend never performs client-side parsing, threshold evaluation, or detection logic of any kind — `runDetectionSimulation()` and `loadSimulatorRules()` only send the analyst's exact selections and render whatever the backend returns; `isValidSimulationResponse` only checks response *shape* (all 9 stages present with a `status` string), never recomputes a result.
- Sidebar visibility: `detection-simulator` uses `visibleWhen: canTakeAlertActions` (analyst or super-admin), matching the backend's `analyst_or_super_admin_required` boundary exactly; confirmed by `sectionsConfig.test.js`'s exhaustive role-matrix test and live in-browser as super_admin.
- Pipeline visualization renders all 9 stages in the exact spec order with non-color-only status indicators (symbol + text + `aria-label`); confirmed by `DetectionSimulatorPipeline.test.js` and live in-browser.
- Explainability renders parser failure, normalization failure, rule-not-applicable, matched/not-matched with configured parameters, existing-open-alert suppression, real-history blending, alert preview (with the "stubbed for simulation" reputation caveat), MITRE mapping (including the "no specific mapping" case), and SOAR preview (matched playbooks, approval requirements, selected response, and the "no execution occurred" statement) — all derived from backend response fields, never recomputed.
- Near-miss/failed-condition numeric detail (observed count vs. threshold) remains unimplemented, consistent with task 2.6/2.7 still being deferred; this is a known, explicitly documented gap, not an oversight.

## Final Contract Review — Implementation 1 scope

- The simulation endpoint (`engines/detection_simulator.py`) never calls `conn.commit()` anywhere; `conn.rollback()` runs unconditionally in a `finally` block around all pipeline DB work, confirmed by the AttributeError-on-commit test technique above.
- The simulation endpoint never calls the production `/ingest`, `/ingest/honeypot`, or other ingest route handlers — it calls `engines.ingest_engine.ingest_normalized_event` and `engines.playbook_engine.match_playbooks` directly.
- Row counts in `events`, `alerts`, `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `incidents`, `incident_alerts`, and `audit_log` are unchanged by simulation runs, including runs that produce a matched alert and a matched playbook with an approval-requiring step.
- `audit_log`: no row of any kind is written by the simulator in this implementation (task 1.6 was deferred — see `tasks.md` for the reasoning: this round's safety requirements listed `audit_log` among tables that must never receive durable rows, stricter than design.md's narrow carve-out, so nothing is written pending explicit reconciliation of that ambiguity).
- Reputation lookups are stubbed (patched at the `engines.detection_engine`/`engines.correlation_engine` call sites for the duration of the simulation call only); confirmed no outbound `requests.get` call occurs via `core.ip_helpers` during a simulation run. Geolocation lookups are never invoked by the simulator at all (no code path calls `lookup_ip_location`).
- Near-miss/failed-condition detector instrumentation (task 2.6) was **not implemented** this round — deferred to the Explainability phase; production alerting behavior is therefore unaffected by construction (no detector file was touched), not merely regression-tested.
- RBAC: `login_required` plus `analyst_or_super_admin_required` allows analysts and super administrators (`test_route_allows_analyst_and_returns_simulation_result`, `test_route_allows_super_admin`), returns 401 for unauthenticated requests (`test_route_requires_authentication`), and returns 403 for insufficient roles (`test_route_rejects_viewer_role`).
- Pipeline stage reporting covers all 9 stages (`raw_input`, `parser`, `normalized_event`, `detection_applicability`, `detection_evaluation`, `threshold_window_evaluation`, `alert_preview`, `mitre_mapping`, `soar_preview`) with succeeded/skipped/failed status per stage; visualization rendering itself is Phase 5 (not this round).

## Phase 7 VM Deployment Handoff

Owner: **VM AI**, only after the user explicitly authorizes the Mac commit/push and the VM deployment. This document does not authorize production access or mutation, and none has occurred. Per `docs/mac-vm-source-of-truth-policy.md`, this handoff follows the "Backend/runtime source without migrations" row of the Deployment Decision Matrix (no migration is included in this change).

### 1. Approved commit

Pending. **`<APPROVED_COMMIT_SHA>`** — must be replaced with the exact, explicitly authorized, pushed commit SHA before any VM step below is executed. Do not deploy any other commit, including a later or earlier one, without a fresh authorization.

### 2. Clean-tree and divergence checks (Mac, pre-push, and VM, pre-sync)

- Mac: `git status --short` at the time of any future commit must be reviewed so only the intended Detection Simulator files are included (this document's diff-scope review above is the current, pre-commit baseline for comparison).
- VM, before every sync: `cd /home/jaden/siem-security-dashboard && git status --short`. If any output appears, **stop** and report the exact files — do not stash, discard, merge, pull, or work around a dirty VM tree without explicit user direction.
- VM: `git fetch origin`, then confirm `git rev-parse origin/main` equals the approved commit, and confirm the VM branch is not behind or diverged from `origin/main` before proceeding.

### 3. GitHub Actions success requirement

Do not deploy a commit whose CI status is not green. Confirm the approved commit's checks have passed (e.g., `gh pr checks` or the equivalent for the merged commit) before recording it as "approved" in section 1. No CI run has been triggered by this Mac-only implementation round, since nothing has been pushed.

### 4. VM sync

After the clean-tree and CI checks above pass, and only with explicit deployment authorization:

```bash
cd /home/jaden/siem-security-dashboard
git fetch origin
git reset --hard origin/main
git rev-parse HEAD   # must equal the approved commit SHA from section 1
```

Never use `git merge origin/main` or a bare `git pull` to sync the VM, per policy.

### 5. Migration expectation

**None.** This change adds no new tables, no schema changes, and no migration file. `scripts/validate_schema_snapshot.py` confirms `schema.sql` still matches migration `0018` (unchanged by this work). Do not run `bash scripts/deploy_backend_vm.sh --dry-run-migrations` expecting a pending migration — there is none; if one is unexpectedly reported, stop and report it rather than applying it.

### 6. Backend deployment and restart order

1. Confirm the VM is on the approved commit (section 4).
2. No migration step is needed (section 5).
3. Restart only `siem-backend.service`:
   ```bash
   sudo systemctl restart siem-backend.service
   systemctl status siem-backend.service --no-pager
   ```
4. Verify health: `curl -fsS http://127.0.0.1:5051/health` returns HTTP 200.
5. No other service (SOAR worker units, playbook worker units) needs restarting — this change adds no worker-facing code paths and does not modify `engines/soar_action_worker.py` or `engines/soar_playbook_worker.py`.

### 7. Mac-built frontend artifact deployment

The Mac-built, `/siem/`-hosted production build (the standard `npm run build` output, **not** the `PUBLIC_URL=/` build used only for this round's local verification) must be deployed:

```bash
rsync -avz --delete \
  -e "ssh -i ~/.ssh/jadeng15.pem" \
  /Users/jadengomez/Projects/siem-security-dashboard-public/frontend/build/ \
  jaden@4.204.25.149:/home/jaden/siem-security-dashboard/frontend/build/
```

Deploy backend first (sections 4–6), verify health, then deploy the frontend artifact — combined frontend+backend change, per the policy's deployment matrix.

### 8. Authenticated production API checks (read-only)

Using an existing authorized analyst or super-admin session, without printing credentials or cookies:

1. `GET /health` → 200.
2. `GET /detection-simulator/rules` (authenticated) → 200, returns only `rule_id`/`display_name`/`description`/`active`/`applicable_sources` fields, matching the exact set `get_detection_rule_defaults()` defines.
3. `POST /detection-simulator/run` with a benign, inapplicable-rule example (e.g., `honeypot` source + `port_scan_threshold` rule, which fails at the Detection Applicability stage before any `events`/`alerts` query) → 200, per-stage response with `detection_applicability.status == "failed"`.
4. Unauthenticated `GET /detection-simulator/rules` and `POST /detection-simulator/run` → 401.
5. An existing insufficient-role (viewer) session on both endpoints → 403.

### 9. Browser checks for the Detection Simulator workspace

1. Confirm "Detection Simulator" appears in the sidebar, under SOC Tools, for an analyst or super-admin session, and is absent/inaccessible for a viewer session.
2. Run one benign, inapplicable-rule simulation (same input as section 8.3) through the UI; confirm all 9 pipeline stages render in the exact spec order with correct status indicators, and the Explanation section renders text matching the API response.
3. Confirm the workspace header's rollback/no-production-write disclosure text is present.
4. Confirm no new browser console errors appear that reference any Detection Simulator file.

### 10. Read-only verification steps (zero-durable-write proof in production)

Before and after step 9.2's simulation run, using read-only queries only (no inserted or deleted test rows):

```sql
SELECT (SELECT COUNT(*) FROM events) AS events,
       (SELECT COUNT(*) FROM alerts) AS alerts,
       (SELECT COUNT(*) FROM playbook_executions) AS playbook_executions,
       (SELECT COUNT(*) FROM soar_response_decisions) AS soar_response_decisions,
       (SELECT COUNT(*) FROM response_actions_queue) AS response_actions_queue,
       (SELECT COUNT(*) FROM response_actions_log) AS response_actions_log,
       (SELECT COUNT(*) FROM incidents) AS incidents,
       (SELECT COUNT(*) FROM incident_alerts) AS incident_alerts,
       (SELECT COUNT(*) FROM audit_log) AS audit_log;
```

All nine counts must be identical before and after. This mirrors exactly what `tests/test_detection_simulator.py::test_zero_durable_writes_across_all_guarded_tables` already proves against a real (test) Postgres instance — this step re-confirms it against the real production database, read-only.

### 11. Explicitly prohibited production-mutating checks

Without separate explicit authorization: do not send synthetic events to the real `/ingest` path, do not run a simulation against a real, currently-active attacker IP or a rule combination believed likely to match real production history in a way that could be confused with a real incident, do not modify detection rules, do not create or alter users/roles, do not trigger real SOAR/playbook/response actions, do not write or delete production events/alerts/incidents, and do not run schema DDL or migrations (none is expected — section 5). Per this Implementation 3 round's explicit instruction, **do not run any live production simulation during VM verification beyond the one minimal, inapplicable-rule benign example in sections 8.3/9.2, and do not run additional exploratory simulations, without separate explicit authorization** — even though the simulator is rollback-safe by design, production data should not be exercised beyond what is explicitly approved here.

### 12. Rollback procedure

- Keep the prior deployed commit SHA and the prior frontend artifact (or its source commit) available before deployment.
- If backend health, either API check (section 8), the browser checks (section 9), or the zero-write verification (section 10) fails: stop before proceeding further, do not deploy the frontend artifact if not already deployed, and restore the prior approved checkout via the same clean-tree/`git reset --hard` workflow, then restart `siem-backend.service` and re-verify `/health`.
- If only the frontend fails after a passing backend: restore the prior frontend build artifact via `rsync` from the prior known-good Mac build.
- No database rollback is expected or authorized — this change adds no migration and is designed to produce no durable data under any code path; if the zero-write verification in section 10 ever shows a count change, treat that as a critical defect, stop immediately, and do not attempt an ad hoc data fix on the VM — return it to Mac AI.

### 13. Final OpenSpec completion gates (must all hold before this handoff is considered actionable)

- [x] All Mac-owned tasks (Phases 1–7.7) show `[x]` in `tasks.md`, each with cited evidence.
- [x] `openspec validate add-detection-simulator-workspace --strict` passes.
- [x] `git diff --check` passes.
- [x] Full backend and frontend test suites pass (modulo the 3 pre-existing, confirmed-unrelated backend failures).
- [x] Production build passes with no new warnings.
- [ ] Explicit user authorization to commit.
- [ ] Explicit user authorization to push.
- [ ] Explicit user authorization to deploy.
- [ ] Sections 1–12 above executed in order, by VM AI, only after all three authorizations are granted.

## VM AI Evidence

- Explicit deployment authorization: not requested, not granted
- Approved commit: none
- Clean-tree preflight/post-check: not performed
- Migration decision and evidence: not applicable — none expected; not yet confirmed on the VM
- Backend health and authenticated simulation-endpoint smoke test: not performed
- Frontend artifact deployment: not performed
- Zero-durable-write production verification: not performed
- Rollback readiness: not applicable — no deployment has occurred

## Scope Confirmation

- Implementations 1–3 are complete on Mac: all Mac-owned tasks across Phases 1–7 are resolved, including both previously deferred tasks. Verified by 39 backend `test_detection_simulator.py` tests, 303 targeted backend regression tests, 1812/1815 full backend suite tests (3 pre-existing, confirmed-unrelated failures), 813/813 frontend tests, a passing production build, and two real local browser sessions (Implementation 2 and Implementation 3) against a live backend and Postgres database.
- No commit, push, archive, or deployment occurred in any implementation round. No VM was accessed. No `.env` file was ever created, edited, or read — every local browser verification session used ephemeral shell-exported environment variables against an already-existing local dev database, torn down after each session.
- Custom rule authoring, Python rule execution, SQL rule execution, a rule builder UI, persistent user-created rules, a rule editor, and rule versioning remain explicitly out of scope for this change and are documented as future roadmap only in `proposal.md` and `design.md`.
- **Both previously deferred tasks are now resolved, explicitly, not silently:**
  - Task 1.6 (`audit_log`): resolved as "never write to it, for any reason" — the strictest safe reading of the zero-durable-write contract, now stated explicitly in `spec.md` and `design.md`.
  - Tasks 2.6/2.7 (near-miss instrumentation): resolved via an evidence-call mechanism that re-invokes the real, unmodified production detector functions with a temporarily-lowered threshold — zero lines changed in `engines/detection_engine.py` or `engines/correlation_engine.py`.
- One known, disclosed, pre-existing local-environment limitation (unrelated to this change): the local dev database used for browser verification has schema drift that blocks live demonstration of matched/not-matched/suppression/alert-preview scenarios in a browser; these are instead fully covered by real transactional-Postgres backend tests. See "Browser verification (Implementation 3)" above for the complete scenario-by-scenario accounting.
- Remaining: VM-owned Phase 7 tasks only (7.8–7.11), pending explicit user authorization to commit, push, and deploy. See "Phase 7 VM Deployment Handoff" above for the complete, ready-to-execute procedure.
