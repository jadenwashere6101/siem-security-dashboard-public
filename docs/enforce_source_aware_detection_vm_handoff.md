# Source-Aware Detection Evaluation VM Handoff (Phases 1–8 complete)

Owner: **VM AI** for Phase 8 deployment; this document is now closeout evidence for the OpenSpec archive.

Mac source of truth: `/Users/jadengomez/Projects/siem-security-dashboard-public`
VM runtime only: per existing deployment runbook / `scripts/deploy_backend_vm.sh` target.

Do **not** edit feature source on the VM. Do **not** merge on a dirty VM.

## Status

- OpenSpec change: `enforce-source-aware-detection-evaluation`
- Phases 1–5 (registry, execution gate, source-isolated queries, config/API, UI): implemented, tests passing.
- Phases 6–7 (correlation/end-to-end regression, schema confirmation, final review, quality gates, browser verification): complete, evidence below.
- Deployed commit: **`6b2ca84`** ("add source-aware detection rule evaluation"), committed and pushed to `origin/main`.
- Phase 8 (VM deployment/production verification): backend, workers, and frontend artifact deployed on `6b2ca84`; see "Phase 8 production verification" below for the evidence actually recorded and which task items remain open.

## Prerequisites

1. Explicit authorization to commit and push this change from Mac.
2. VM worktree clean (`git status` empty of local edits).
3. No new migration required — confirmed below (schema unchanged).

## Files changed

Backend:
- `engines/detection_applicability.py` (new) — canonical source-pair registry, immutable applicability metadata.
- `engines/detection_config.py` — merges applicability metadata into effective/default rule responses.
- `engines/detection_engine.py` — all 15 base detectors now receive the evaluated source pair, constrain every historical aggregation/evidence/location query to `source_ip` + exact `(source, source_type)`, and gate on effective `active` before any SQL.
- `engines/ingest_engine.py` — builds explicit per-event-type detector candidates and applies a shared applicability + active gate (`_run_detector`) before invoking any detector.
- `routes/admin_routes.py` — `PATCH /admin/detection-rules/<rule_id>` now accepts `parameters`, `active`, or both; validates strict booleans; persists active state; audits old/new active + parameter changes.

Frontend:
- `frontend/src/components/DetectionRulesPanel.js` — accessible active toggle/status control, read-only "Applicable Sources" badges sourced from the API (no duplicate matrix).
- `frontend/src/services/detectionRulesService.js` — sends `active` alongside `parameters` on update.

Tests (new/updated):
- `tests/test_detection_applicability.py` (new), `tests/test_source_aware_detection.py` (new)
- `tests/test_admin_api_contracts.py`, `tests/test_auth_rbac.py`, `tests/test_high_request_rate_detection.py`, `tests/test_ingest_normalized_event.py`, `tests/test_port_scan_detection.py`
- `frontend/src/components/DetectionRulesPanel.test.js` (new), `frontend/src/services/detectionRulesService.test.js` (new)

No migration files added. `openspec/changes/enforce-source-aware-detection-evaluation/` holds the proposal/design/tasks/specs.

## Phase 6–7 verification evidence (Mac)

**Backend tests:** `python3 -m pytest tests/` → 1726 passed, 3 pre-existing failures unrelated to this change (`test_alert_mutation_api_contracts.py::test_post_alert_execute_duplicate_block_ip_does_not_write_tracking_success`, `test_post_alert_execute_canonical_write_failure_rolls_back_legacy_success`, `test_soar_adapter_interface.py::test_adapter_backed_executor_invalid_result_fails` — confirmed to fail identically on `main` before this change via `git stash`).

**Frontend tests:** `CI=true npx react-scripts test --watchAll=false` → 56 suites / 743 tests passed.

**Production build:** `npx react-scripts build` → succeeds (pre-existing ESLint warnings only, in files untouched by this change: `App.js`, `IncidentsPanel.js`, `LiveLogsPanel.js`).

**Python compilation:** `python3 -m py_compile` on all changed/new files → clean.

**`git diff --check`:** clean, no whitespace errors.

**`openspec validate enforce-source-aware-detection-evaluation --strict`:** `Change 'enforce-source-aware-detection-evaluation' is valid`.

**Schema/migration:** Confirmed no migration needed. `events`, `alerts`, and `detection_config` already carry `source`/`source_type`/`active`/`parameters` columns (present since migrations 0002/0011). `tests/test_migrations.py` and `tests/test_schema_migrations.py` pass (35 tests).

**Correlation regression:** `tests/test_correlated_activity.py` and `tests/test_targeted_correlation.py` pass. Confirmed by code review that `correlated_activity`, `web_to_app_attack_pattern`, `spray_then_success_pattern`, and `cloud_app_error_pattern` read already-attributed open `alerts` rows (not raw `events`) and are not registered in `RULE_APPLICABILITY` — correlation remains a separate, unchanged domain per design decision 6.

**Final source-predicate review:** Read all 15 base detector functions in `engines/detection_engine.py` end-to-end. Every historical aggregation, temporal join (`successful_login_after_spray`), evidence lookup, and location lookup constrains on `source_ip` + exact `source`/`source_type`. Two enforcement layers confirmed: `ingest_engine._run_detector` (dispatch-time) and `detection_engine._prepare_rule_evaluation` (direct-call/defense-in-depth). No detector bypasses the shared gate. Only one applicability matrix exists (`engines/detection_applicability.py`); `routes/alerts_events_routes.py` has an unrelated, pre-existing `VALID_EVENT_SOURCES` set used for event search filtering, not rule applicability. Unknown/malformed/case-variant/blank source pairs fail closed (`test_unknown_case_variant_and_mismatched_pairs_fail_closed`) with no SQL executed (proven via `cur.execute.assert_not_called()` in direct-detector tests). No `UPDATE`/`DELETE`/`ALTER TABLE` statements were introduced against `events` or `alerts` — historical rows are never mutated.

**RBAC/audit:** `test_viewer_cannot_change_detection_rule_active_state` added; `super_admin_required` unchanged; audit event `detection_rule_updated` now includes `old_active`/`new_active` alongside existing parameter change tracking.

## Real-browser verification (Mac, local-only DB, not deployed)

Verified against a locally-built production frontend bundle served by the Flask backend (matching the real single-origin production topology) against an isolated, freshly migrated local Postgres database (no shared state with any deployed environment):

- Logged in as super_admin; Detection Rules panel renders 15 rules with correct read-only "Applicable Sources" badges per rule (multi-source `failed_login_threshold`: Azure/Bank App/NGINX/OpenTelemetry; single-source `port_scan_threshold`: Bank App only; four Honeypot-only rules; four pfSense-only rules) and the "One global configuration applies to all listed sources" note.
- Disabled `failed_login_threshold` through the admin UI (real `PATCH /admin/detection-rules/failed_login_threshold` call) → status flipped to `INACTIVE`; confirmed via direct ingest that 3 qualifying `failed_login` events from a fresh IP were stored in `events` but created zero alerts.
- Re-enabled the same rule via UI → status returned to `ACTIVE`, parameters (`threshold=3`, `window_minutes=15`) preserved; ingesting one more qualifying event immediately produced an alert with truthful `source=bank_app`/`source_type=custom` evidence.
- Disabled and re-enabled `pfsense_firewall_repeated_deny` (pfSense-only rule) via UI — same behavior.
- Audit log (`audit_log` table) shows `detection_rule_updated` events with `old_active`/`new_active` for both toggles.
- Triggered a failed parameter update (`threshold=0`, below the validated minimum) → inline validation error shown ("Parameter threshold must be between 1 and 100"), row remained in edit mode with no partial save; after Cancel, the row correctly reverted to `DEFAULT / Code defaults` with unmodified values — no rollback artifact left behind.
- No console errors/exceptions during any of the above (checked via browser console after each action).
- Visual/contrast spot-check of status badges, source badges, and buttons against the existing dark theme showed no regression; toggle buttons carry accessible labels (`aria-label="Disable Failed Login Threshold"` etc., `aria-pressed`) confirmed via accessibility tree read.

Note: one interaction hazard observed and worth carrying into VM smoke testing — `DetectionRulesPanel`'s disable action uses a native `window.confirm()` dialog. This is pre-existing, intentional UX (confirms before disabling detection), not a regression, but it will block any browser-automation tooling used during VM verification unless pre-empted (e.g. `window.confirm = () => true` before clicking Disable, or manual confirmation).

## Deployment sequence (exact order, once authorized)

1. **Commit and push from Mac.**
2. **Wait for GitHub Actions** (`migration-validation.yml`) to pass on the pushed commit.
3. **Sync VM safely** — clean-tree preflight on VM (`git status --short` empty), fetch/merge only the authorized pushed revision through the existing source-of-truth workflow. Never force-push; never rewrite migration files.
4. **Deploy/restart backend** — run the deployment helper's migration dry-run (expected: `Nothing to apply`, since no migration is included in this change), then restart only the affected backend service(s) per the existing runbook.
5. **Deploy Mac-built frontend artifact** — build `frontend/build/` on Mac (already verified to build cleanly) and deploy/rsync it per `deploy.sh`; reload Nginx so new SPA assets are served.
6. **Perform production verification** (see below).

## Phase 8 production verification (recorded evidence)

Reported and recorded as of this closeout:

- **Deployed commit:** `6b2ca84`.
- **Migration:** none required; consistent with the Phase 7 schema conclusion (no migration files in this change).
- **Backend and workers:** reported healthy on the deployed commit.
- **Source isolation in production:** confirmed using existing production rows (not a fresh synthetic-data-per-rule-family pass with dedicated test IPs).
- **Correlation:** all four existing correlation families (`correlated_activity`, `web_to_app_attack_pattern`, `spray_then_success_pattern`, `cloud_app_error_pattern`) confirmed.
- **Frontend:** Mac-built artifact deployed; Detection Rules UI verified live in production.

**Not separately evidenced at this closeout** (left for a future authorized pass, not blocking archive since no defect is indicated):
- A synthetic-data, fresh-IP verification per individual rule family (as originally scoped in task 8.3) beyond the existing-rows confirmation above.
- An explicit production test that toggling `active=false` prevents detection without blocking ingestion.
- Restoration/audit evidence for any `active`-state changes made specifically for smoke testing, and an explicit rollback-readiness confirmation (task 8.5).

Task list below is updated to reflect exactly this: 8.1, 8.2, and 8.4 are marked complete on the strength of the evidence above; 8.3 and 8.5 remain open pending the additional evidence described.

## Production verification — safe read-only vs. mutating

**Safe, read-only checks (no runtime data change):**
- `GET /health` returns ok.
- `GET /admin/detection-rules` (as super_admin) shows all 15 rules with correct `active` state and `applicable_sources` metadata matching the registry.
- Visual check of the Detection Rules panel in production (active/inactive rendering, source badges, dark theme).
- Review `audit_log` for any historical `detection_rule_updated` entries (read-only).

**Mutating checks (require restoration after, per task 8.5):**
- Toggling any rule's `active` state via the admin UI/API to confirm the PATCH contract and audit logging work in production — **must be restored to its prior state immediately after** and the restoration itself audited.
- Ingesting authorized synthetic events (fresh, clearly-marked test IPs, e.g. `TEST-NET` ranges) per rule family/source pair to confirm one supported source per rule still detects, and that unsupported/mixed sources do not contribute or create alerts. This writes real `events`/`alerts` rows in production and should use IPs and a naming convention that make cleanup/identification straightforward.
- Verifying cross-source correlation (`web_to_app_attack_pattern`, `spray_then_success_pattern`, `cloud_app_error_pattern`, generic `correlated_activity`) still fires from accurately attributed alerts — also alert-writing, same cleanup caveat.

## Rollback posture

- No schema/data migration is included, so rollback is a pure application-version rollback to the prior approved commit (backend + frontend artifact only).
- No `DROP`/`ALTER` destructive statements were introduced; existing historical `events`/`alerts` rows are never rewritten by this change, so no data rollback is needed.
- Any `active` state changes made during VM smoke testing must be restored to their pre-test values and the restoration audited before closing out deployment.

## Unresolved risks / open items

- Task 8.3's originally-scoped synthetic-data-per-rule-family verification and explicit `active=false`-prevents-detection production test are not separately evidenced (production isolation was confirmed via existing rows instead). No defect is indicated by this gap; it is a coverage gap in the verification record, not a known issue.
- Task 8.5's restore/audit/rollback-readiness confirmation for smoke-testing changes is not recorded. If any `active`-state toggling was done in production during verification, confirm it was restored before treating the deployment as fully closed out.
- Local real-browser verification (Mac-side, pre-deployment) used an isolated local database and a temporary WSGI mount to emulate the `/siem`-prefixed production topology. This was superseded by the live production Detection Rules UI verification recorded above.
- No production data was touched by Mac-side verification (fully isolated local DB, dropped after verification).
