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
