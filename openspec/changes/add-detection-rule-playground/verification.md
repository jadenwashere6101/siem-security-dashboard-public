# Detection Rule Playground Verification

Status: Phases 1–5 are implemented on Mac. No commit, no push, no deployment, no VM access, no migration, and no production mutation have occurred.

## Mac AI Evidence — Phases 1–3

- Implemented a second backend simulator mode, `temporary_playground_rule`, inside the existing rollback-only Detection Simulator engine/route boundary. Version 1 `rule_id`-based production-rule simulation remains intact and is still exercised by the existing test suite.
- Temporary-rule contract is backend-owned and fail-closed: canonical `source`/`source_type`, source-compatible `input_format`, optional source-compatible `event_type`, exactly one `condition`, exactly one `aggregation` (`count`), bounded `threshold`, bounded `window_minutes`, bounded string/list sizes, bounded grouped results, optional allowlisted `mitre_technique_id`, and explicit rejection of persisted/history-aware request shapes.
- Temporary-rule evaluation is pasted-event-only. It does not read production `events` or `alerts` for threshold/window/dedup semantics, and route-level validation rejects history/draft-style fields.
- Parser/normalizer reuse is preserved by routing temporary-rule input through the same source-specific parse/normalize handlers the simulator already uses.
- Temporary alert preview is built by inserting a simulator-only alert row inside the rollback transaction only when threshold is met; MITRE preview and SOAR/playbook preview then reuse the existing preview contracts against that uncommitted row.
- No queueing, playbook execution, approval creation, incident creation, audit logging, reputation/geolocation API usage, or integration adapter execution occurs in the temporary-rule path.

## Commands and Results

- Python compilation:
  - `python3 -m py_compile engines/detection_simulator.py routes/detection_simulator_routes.py tests/test_detection_simulator.py`
  - Passed
- Focused Phase 1–3 backend suite:
  - `python3 -m pytest tests/test_detection_simulator.py -q`
  - Passed: `62 passed`
- Directly affected regressions:
  - `python3 -m pytest tests/test_ingest_normalized_event.py tests/test_detection_applicability.py tests/test_playbook_engine.py tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_port_scan_detection.py tests/test_high_request_rate_detection.py tests/test_http_error_detection.py tests/test_application_exception_detection.py tests/test_honeypot_event_detections.py tests/test_pfsense_firewall_detections_soar.py tests/test_source_aware_detection.py -q`
  - Passed: `163 passed`

## Safety Evidence

- Zero durable writes for temporary-rule mode:
  - Covered by `test_temporary_rule_no_external_calls_and_zero_writes`
- Worker-safety / separate-connection visibility:
  - Covered by `test_temporary_rule_no_pending_row_visible_to_separate_connection`
- No external quota or integration execution:
  - Covered by `test_temporary_rule_no_external_calls_and_zero_writes`
- Pasted-event-only behavior:
  - Covered by `test_temporary_rule_is_pasted_event_only_even_when_real_history_exists`
- Version 1 unchanged:
  - Existing simulator tests still pass inside `tests/test_detection_simulator.py`
  - Detector/playbook/applicability regressions passed unchanged

## Mac AI Evidence — Phases 4–5 (Frontend)

New files:
- `frontend/src/utils/detectionSimulatorPlaygroundContract.js` — presentation-only mirror of the backend's temporary-rule allowed-value maps (condition fields, group-by fields, input formats, event types, operators by field type, severities, MITRE id pattern) plus a pure `buildPlainLanguageSummary()` derived-from-form-state description. Mirrors the existing `SIMULATOR_SOURCE_INPUT_FORMATS` pattern already used for Version 1 guidance; the backend independently validates everything regardless of what this file allows.
- `frontend/src/utils/detectionSimulatorPlaygroundSamples.js` — canned "load sample events" text per source/input-format combination. Every payload was verified directly against the real `PARSE_DISPATCH` parser/normalizer functions in `engines/detection_simulator.py` before being embedded (including discovering and fixing that Azure Insights identity payloads require `baseType: "SignInLog"` to route to the identity normalizer).
- `frontend/src/components/DetectionSimulatorPlaygroundBuilder.js` — the guided builder: source/input-format/event-type-filter selectors, pasted-or-sample event textarea with a "Load sample events" action, a condition builder (field/operator/value, with `in_list` and numeric-field handling), group-by/threshold/window/severity controls, an optional MITRE technique id field (format-validated client-side against `Txxxx`/`Txxxx.xxx` before submission), a live plain-language summary, and `Run Simulation` / `Reset Rule` actions. It only assembles a `temporary_rule` request object and hands it to a parent-supplied `onRun` callback — it never parses pasted events or computes a match/threshold outcome itself.

Modified files:
- `frontend/src/components/DetectionSimulatorPanel.js` — added a `role="radiogroup"` two-mode selector (`Existing Production Rule` default-selected, `Temporary Playground Rule`). The Version 1 form, its handlers, and its exact request-payload shape are unchanged and still gated behind `mode === "existing_production_rule"`; the panel's `runError`/`result`/pipeline/explainability rendering block is shared by both modes unmodified. Switching modes clears any prior result/error.
- `frontend/src/components/DetectionSimulatorExplainability.js` — extended (not rewritten) with shape-detected branches for temporary-rule stages: playground-specific applicability wording (detected via `allowed_condition_fields` presence), grouped-evidence + pasted-event-only + nothing-persisted disclosure sentences appended to the threshold explanation (detected via `grouped_results` presence), temporary-mode alert-preview and MITRE wording (detected via `temporary_rule_semantics`/`reason` fields the backend already returns). Every Version 1 branch and wording string is untouched.
- `frontend/src/utils/detectionSimulatorStages.js` — purely additive: three new `SIMULATOR_STAGE_REASON_TEXT` entries for the temporary-rule reason codes the backend already returns (`temporary_rule_threshold_not_reached`, `no_alert_created_for_temporary_rule`, `no_temporary_rule_mitre_selected`).
- `DetectionSimulatorPipeline.js` required no changes — it is a pure stage-status renderer already generic across both modes.

No backend files were modified in this round; Phases 1–3 (already implemented and evidence-backed above) are reused unchanged.

## Commands and Results — Phases 4–5

- Focused new-file frontend tests:
  - `CI=true npx react-scripts test src/utils/detectionSimulatorPlaygroundContract.test.js src/components/DetectionSimulatorPlaygroundBuilder.test.js --watchAll=false`
  - Passed: 2 suites, 18 tests
- Updated existing-file frontend tests (Panel mode-selector/submission/reset/keyboard tests added; Explainability temporary-rule-evidence tests added):
  - `CI=true npx react-scripts test src/components/DetectionSimulatorPanel.test.js src/components/DetectionSimulatorPipeline.test.js src/components/DetectionSimulatorExplainability.test.js src/services/detectionSimulatorService.test.js --watchAll=false`
  - Passed: 4 suites, 77 tests (39 pre-existing Version 1 tests pass byte-for-byte unchanged; 38 new)
- Full frontend regression suite (App/sidebar/navigation and all other components/services/utils):
  - `CI=true npx react-scripts test --watchAll=false`
  - Passed: 66 suites, 843 tests. Remaining console warnings in the run (`MapViewReputation.test.js`, `SourceIpContext` act() warnings) are pre-existing and in files untouched by this change (confirmed via `git status --short`).
- Frontend production build:
  - `npm run build`
  - Compiled successfully. Pre-existing ESLint warnings in `App.js`, `IncidentsPanel.js`, `LiveLogsPanel.js` (none touched by this change) are unrelated to the playground feature; the three new/modified simulator files compiled with zero warnings. Build was run without `CI=true` to match `docs/mac-vm-source-of-truth-policy.md`'s documented `npm run build` command exactly (that policy's own frontend-deployment section does not set `CI=true`, and this repo already carries unrelated warnings that predate this change).
- Backend regression re-check (Phase 1–3 files untouched this round, re-run for confidence):
  - `python3 -m pytest tests/test_detection_simulator.py -q`
  - Passed: `62 passed`
- `git diff --check`: passed
- `openspec validate add-detection-rule-playground --strict`: passed

## Local Browser Verification — Limitation

- Started the CRA dev server (`npm start`, port 3000) against the local Postgres instance (already running, used by the pytest `postgres_db` fixture) and reached the real `/siem/` login screen in Chrome via browser automation.
- The Flask backend (`python3 siem_backend.py`) was not started: the repository's `.env` is empty and no Python `venv` exists in this environment, so bringing up an authenticated session would require populating real DB/session secrets, running schema migrations, and seeding an admin user — meaningful environment setup outside the scope of a frontend-only UI change. Login was attempted (user-authorized, using Chrome's own saved-credential autofill) and failed with a JSON-parse error, confirming no backend was listening (CRA served its own `index.html` for the API call).
- **Result: no authenticated live-backend click-through of either simulator mode was completed.** In its place, verification relies on: the 843-test full frontend suite (real jsdom DOM rendering, real fireEvent/user-event interactions, `toHaveFocus()`-based keyboard-order assertions, and a `console.error` spy asserting no new console errors — see `DetectionSimulatorPanel.test.js`'s "mode selector and builder controls are keyboard-focusable..." test), the clean production build, and the fact that every new component reuses the exact dark-theme style constants and responsive grid pattern (`repeat(auto-fit, minmax(200px, 1fr))`) already visually verified for Version 1's workspace.
- This is a disclosed environment-setup gap, not a code defect. If full authenticated browser click-through is required before archiving this change, it needs either (a) the user providing/approving local `.env` DB+secret setup and an admin seed, or (b) deferring that check to VM AI's Phase 7 read-only production verification (which does exercise a real authenticated session).

## Migration / Deployment Scope

- No schema migration was added or required for Phases 1–5.
- No VM work was performed.
- Frontend production build succeeded and is ready for the (not-yet-authorized) build/deploy step described below.

## Planned VM Handoff

Owner: VM AI, only after explicit user authorization.

- Approved commit placeholder: `<APPROVED_COMMIT_SHA>`
- Expected migration state: none — Phases 1–5 added no schema migration and none was discovered to be required
- Expected changed files: `engines/detection_simulator.py`, `routes/detection_simulator_routes.py`, `tests/test_detection_simulator.py` (backend, Phases 1–3), plus the frontend files listed above (Phases 4–5) and their compiled `frontend/build/` artifact
- Deployment order: this is a combined frontend+backend change — deploy backend first, verify `/health` and authenticated read-only simulator checks, then deploy the Mac-built frontend artifact per `docs/mac-vm-source-of-truth-policy.md`'s "Combined frontend and backend change" path
- Read-only production verification only:
  - `/health`
  - authenticated simulator mode checks for both `Existing Production Rule` and `Temporary Playground Rule`
  - role-boundary checks (analyst/super_admin only, matching the single `analyst_or_super_admin_required` backend decorator both modes share)
  - zero durable row-count delta across `events`, `alerts`, `playbook_executions`, `soar_response_decisions`, `response_actions_queue`, `incidents`, `incident_alerts`, `audit_log`
  - no worker-visible pending rows
- Rollback expectation: code/artifact rollback only, with no schema rollback expected

## Current Results

- `openspec validate add-detection-rule-playground --strict`: passed
- `git diff --check`: passed

## Scope Confirmation

- Phases 1–5 implementation is complete on Mac and evidence-backed, except for the disclosed live-browser-login gap noted above.
- No client-side rule evaluation exists anywhere in the new frontend code: `DetectionSimulatorPlaygroundBuilder.js` only assembles and submits a request object; all match/threshold/grouped-evidence computation is read verbatim from the backend response by the shared `DetectionSimulatorPipeline`/`DetectionSimulatorExplainability` components (see the Panel test "...without recomputing the match client-side").
- No persisted-draft or saved-rule behavior exists in the frontend: there is no `Save Rule` or promotion control anywhere (asserted directly in tests), `Reset Rule` only clears in-memory component state, and every request is sent fresh with no client-side storage.
- No VM work was performed.
- `VM Sync Required`: No for this implementation round; source changes are local only and were neither committed nor deployed.
