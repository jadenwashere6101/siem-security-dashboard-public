# Verification

## Scope

This closeout reviewed the complete Phase A-E diff as one feature, re-confirmed that the Phase A-B files are part of this OpenSpec change, and completed the final Mac-owned validation/build/handoff work without accessing the VM.

## Feature-level diff review

- Phase A-B files are part of this change, not unrelated work:
  - `engines/detection_engine.py`
  - `engines/detection_config.py`
  - `core/core_playbook_pack_v1.py`
- Phase C-E files align to the approved read-only analyst-investigation and Detection Health scope:
  - `routes/alerts_events_routes.py`
  - `routes/admin_routes.py`
  - `frontend/src/components/AlertDetailsPanel.js`
  - `frontend/src/components/AlertTableRow.js`
  - `frontend/src/components/DetectionRulesPanel.js`
  - `frontend/src/services/detectionRulesService.js`
  - `frontend/src/services/pfsenseAlertInvestigationService.js`
  - related focused tests

## Command evidence

### Focused/backend contract checks

- `python3 -m pytest tests/test_alerts_api_contracts.py tests/test_admin_api_contracts.py`
  - Passed.
- `python3 -m pytest tests/test_detection_applicability.py tests/test_schema_migrations.py tests/test_migrations.py`
  - Passed.

### Full frontend regression

- `CI=true npm test -- --watch=false` (run from `frontend/`)
  - Passed: `68/68` suites, `858/858` tests.
  - Pre-existing warnings only:
    - React `act(...)` warnings in untouched components/tests.
    - DOM nesting warning surfaced in existing alert-table test output.

### Full backend regression

- `python3 -m pytest`
  - Completed in `187.47s`.
  - Result: `1880 passed`, `3 failed`, `3 warnings`.
  - Failing tests:
    - `tests/test_alert_mutation_api_contracts.py::test_post_alert_execute_duplicate_block_ip_does_not_write_tracking_success`
    - `tests/test_alert_mutation_api_contracts.py::test_post_alert_execute_canonical_write_failure_rolls_back_legacy_success`
    - `tests/test_soar_adapter_interface.py::test_adapter_backed_executor_invalid_result_fails`
  - No failure occurred in the pfSense detection, admin contract, alerts contract, migration, or playbook areas touched by this change; `tests/test_pfsense_firewall_detections_soar.py` passed in the same full-suite run.
  - Treat the three failures above as unrelated until the VM owner confirms otherwise against the branch baseline.

### Build / schema / compile / spec / diff

- `npm run build` (run from `frontend/`)
  - Succeeded.
  - Pre-existing warnings only in untouched files:
    - `frontend/src/App.js`
    - `frontend/src/components/IncidentsPanel.js`
    - `frontend/src/components/LiveLogsPanel.js`
- `python3 scripts/validate_schema_snapshot.py`
  - Passed: snapshot matches migration `0018`.
- `python3 -m py_compile routes/alerts_events_routes.py routes/admin_routes.py tests/test_alerts_api_contracts.py tests/test_admin_api_contracts.py tests/test_pfsense_firewall_detections_soar.py`
  - Passed.
- `openspec validate pfsense-detection-quality-and-analyst-experience --strict`
  - Passed.
- `git diff --check`
  - Passed.

## Browser verification

### Completed in local Mac browser verification environment

- Authenticated app shell loaded in headless Chrome against an isolated local temp database.
- Dark theme shell rendered correctly.
- Narrow layout shell rendered correctly at `390px` width.
- Detection Rules navigation was present in the authenticated super-admin shell.
- No feature-specific frontend crash prevented app boot.

### Limitation

- The temporary headless harness could not reliably drive the dashboard alert-table interactions inside the iframe in this environment, even after switching to exact seeded data values and the native controlled-input setter.
- Because of that harness limitation, the following UI items remain backed by focused Jest coverage plus API verification rather than a completed end-to-end headless click path:
  - pfSense "Why this fired" detail interaction
  - cooldown/suppression list indicators
  - Detection Health click/focus navigation
  - final no-console-errors assertion for the full interaction path

### Browser-backed local data set used

- Local temp DB: `codex_pfsense_closeout_20260713`
- Seeded browser-verification rows:
  - `failed_login_threshold` non-pfSense control row
  - `pfsense_firewall_repeated_deny` resolved row with why-fired context
  - `pfsense_firewall_noisy_source` suppressed row
  - `21` `pfsense_firewall_port_scan` rows
  - `5` `pfsense_firewall_suspicious_allow` rows

## Non-pfSense unchanged confirmation

- Non-pfSense behavior remained outside the scope of code changes.
- The local browser seed included a non-pfSense `failed_login_threshold` alert specifically to confirm the new pfSense-only investigation affordance does not broaden automatically.
- Focused API/UI tests for pfSense additions passed without requiring non-pfSense contract changes.

## No-migration confirmation

- No migration files were added.
- Schema snapshot validation still matches migration `0018`.
- The backend change relies on existing `alerts`, `audit_log`, and `detection_config` structures only.

## Slack mute / deployment caveat

- The source-controlled notification policy in `core/core_playbook_pack_v1.py` is not the same thing as the current production database state.
- `scripts/seed_core_playbook_pack_v1.py` only seeds definitions; persisted `playbook_definitions.steps` rows can already differ in the production DB.
- Local verification confirmed the source-seeded investigation playbooks omit `notify_slack`, while containment playbooks still keep `notify_slack`.
- VM owner must verify the production DB separately before deployment by inspecting persisted `playbook_definitions` rows; do not assume the production DB mute state from source code alone.

## Exact VM deployment / verification steps

1. Sync this branch to the VM without rebasing away the validated diff.
2. Re-run `openspec validate pfsense-detection-quality-and-analyst-experience --strict`.
3. Re-run `git diff --check`.
4. Confirm there are no new migrations to apply for this change.
5. Rebuild/redeploy the frontend artifact from this exact source state.
6. Run the relevant backend tests on-VM for the deployed Python/runtime environment.
7. Run the relevant frontend tests/build checks on-VM if that environment is part of the release gate.
8. Inspect persisted `playbook_definitions.steps` in the production DB and verify:
   - pfSense investigation playbooks do not notify Slack unless explicitly intended.
   - pfSense containment playbooks still preserve the approved Slack behavior.
9. Browser-verify on the VM/deployed app:
   - pfSense "Why this fired" panel
   - cooldown/suppression indicators
   - Detection Health 24-hour counts, severity, last-fired values, and badges
   - click/focus navigation from Detection Health to the matching Detection Rule
   - non-pfSense alerts/rules unchanged
   - dark theme
   - narrow layout
   - keyboard accessibility
   - no new console errors
10. Only after the VM owner confirms the persisted playbook state and deployed browser behavior should this change be considered deployment-ready.
