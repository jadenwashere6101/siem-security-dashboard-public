# Verification — clarify-soar-outcome-evidence-and-verification (Mac)

## Dark theme / a11y / viewport

| Check | Result |
| --- | --- |
| Dark theme | Existing dark tokens retained; evidence text `#c9d1d9` / warning `#fcd34d` |
| Keyboard | Badge evidence uses native `<details>`/`<summary>`; related IDs are buttons |
| Screen reader | Badge aria-label retains mode/state; evidence list labeled |
| Narrow viewport | Evidence `maxWidth: 320px`; queue help wraps |

## Serializer

No additive backend serializer required — canonical evidence fields already present.

## Correction pass (Mac)

| Check | Result |
| --- | --- |
| Stale `alerts.response_status` | Removed as authoritative UI field; ResponseOutcome / ResponseStateSummary preferred |
| `approval_expired` | Distinct reason code + CHECK migration `0017`; Expired ≠ Rejected |
| Legacy `approval_denied` | Still renders as Rejected; no historical rewrite |
| External effect | Blocked/expired/denied paths keep effect booleans false |

### Commands (this pass)

| Command | Result |
| --- | --- |
| Focused frontend suites (`AlertExpandedRow`, `AlertsTable`, `ResponseOutcome`, `responseNavigation`, `MapViewSourceIpContext`, `SourceIpContext`) | **115 passed** |
| Broader frontend pattern (`Alert\|ResponseOutcome\|SoarQueue\|Playbook\|MapView\|SourceIp\|responseNavigation`) | **270 passed / 18 suites** |
| Correction-related backend (legacy + e2e + expired/denied queue/playbook) | **38 passed** |
| Full `test_response_action_queue.py` with sibling suites | **201 passed / 16 failed** — failures are **pre-existing** monitor/executor-mock expectations (confirmed failing without this diff); not fixed |
| `python3 -m py_compile` (touched modules) | **OK** |
| `npm run build` | **OK** (pre-existing eslint warnings only) |
| `openspec validate clarify-soar-outcome-evidence-and-verification --strict` | **valid** |
| `git diff --check` | **clean** |

## Stale simulation framing correction (task 11, this pass)

| Check | Result |
| --- | --- |
| `summary.by_mode` never labels a mixed batch as uniformly `simulation` | Confirmed via new `test_worker_run_once_admin_batch_summary_is_mode_aware_for_mixed_batch` (block_ip + monitor in one batch → `{"internal": 1, "tracking_only": 1}`, no `simulation` key) |
| Pre-existing stale assertion fixed | `test_worker_run_once_ignores_real_execution_env` asserted `"Monitoring only"` (legacy `SimulationExecutor` message); confirmed via `git stash` that this failed on `main` before this pass; updated to assert the actual canonical message `"Monitoring disposition recorded."` |
| No writer/outcome-event semantics changed | `classify_queue_action_mode` is additive and read-only (wraps existing `_queue_outcome_classification`); `_worker_result` gained one additive `action` field only |

### Commands (task 11, this pass)

| Command | Result |
| --- | --- |
| `tests/test_soar_worker_admin_run_control.py` | **26 passed** |
| `tests/test_response_action_queue.py` + `test_canonical_outcome_mode_semantics.py` + `test_soar_executor.py` + `test_soar_worker_runner.py` | **146 passed** |
| Frontend pattern (`Alert\|ResponseOutcome\|SoarQueue\|Playbook\|Incidents\|Integration\|responseNavigation\|MapView\|SourceIp`) | **361 passed / 22 suites** |
| Full frontend suite | **724 passed / 52 suites** |
| `npm run build` | **OK** (same pre-existing eslint warnings as before this pass, confirmed via `git stash` on unmodified `main`) |
| `git diff --check` | **clean** |
| `openspec validate clarify-soar-outcome-evidence-and-verification --strict` | **valid** |

### Visual verification (task 11, this pass)

Live local CRA dev server + a temporary local mock HTTP backend (via a temporary `frontend/src/setupProxy.js`, deleted after verification; no repo files retained) authenticated as `super_admin`, driven in a real browser:

| Representative state | Surface | Result |
| --- | --- | --- |
| Internal outcome | SOAR Queue → queue row 5001 (`monitor`) | Badge: **Internal** |
| Tracking-only outcome | SOAR Queue → queue row 5002 (`block_ip`) | Badge: **Tracking only** |
| Simulated outcome | SOAR Queue → queue row 5003 (`flag_high_priority`, `simulation` mode); Integration Status → Firewall adapter | Badge: **Simulated**; Firewall card: `SIMULATION` mode badge + corrected description |
| Real-capable/executed outcome | SOAR Queue → queue row 5004 (`notify_slack`); Integration Status → Slack adapter | Badge: **Real executed**; Slack card: `REAL` / `HEALTHY` |
| Mixed queue batch | SOAR Queue → “Process queue batch” click | Result panel: “2 queue actions processed internally”, “Modes: 1 internal · 1 tracking-only”, “Processed successfully: 2”, no blanket simulated label |

Also confirmed in-browser: SOAR Incidents timeline notice reads “Timeline is read-only. Each event's mode (internal, tracking-only, simulated, or real) is determined by the backend and shown per event,” with a genuinely-simulated per-event label (“Simulated adapter step”) still rendering correctly alongside it.
