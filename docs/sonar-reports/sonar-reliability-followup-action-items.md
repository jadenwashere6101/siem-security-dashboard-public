# Sonar Reliability Follow-Up Action Items

Source report: `sonar-reliability.json` / `sonar-reliability.csv`

## Overall Assessment

The 844 reliability-impact issues are not all false positives, but most are not production-risk bugs. The report is dominated by React prop validation findings rather than backend SOAR/orchestration failures.

High-signal breakdown:

- 795 React prop-validation findings (`javascript:S6774`) across frontend components
- 15 timezone/deprecated UTC datetime findings in `core/playbook_store.py` (`python:S6903`)
- 13 accessibility label association findings (`javascript:S6853`)
- 1 sort comparator reliability finding in `DeadLettersPanel.js` (`javascript:S2871`)
- 20 minor cleanup findings across tests/frontend/routes

## Recommended Fix First

These are the safest, highest-value reliability fixes to consider first.

### UTC datetime handling

- Rule: `python:S6903`
- Count: 15
- File: `core/playbook_store.py`
- Recommendation: fix in one scoped backend pass only after checking DB timestamp expectations. This is real technical debt, but it touches playbook persistence and should not be changed casually.

| File | Line | Finding |
| --- | ---: | --- |
| `core/playbook_store.py` | 600 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 229 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 320 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 157 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 402 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 490 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 523 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 89 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 631 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 1450 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 1382 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 1422 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 1510 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 1543 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `core/playbook_store.py` | 1608 | Don't use `datetime.datetime.utcnow` to create this datetime object. |

### Dead-letter sort comparator

- Rule: `javascript:S2871`
- Count: 1
- File: `frontend/src/components/DeadLettersPanel.js`
- Recommendation: safe small frontend fix. Use `String.localeCompare` in the affected sort comparator.

| File | Line | Finding |
| --- | ---: | --- |
| `frontend/src/components/DeadLettersPanel.js` | 177 | Provide a compare function that depends on "String.localeCompare", to reliably sort elements alphabetically. |

### Form label accessibility

- Rule: `javascript:S6853`
- Count: 13
- Recommendation: safe frontend polish. Associate labels with inputs/selects using `htmlFor`/`id` or `aria-label` where the visual label is not a real `<label>`.

| File | Line | Finding |
| --- | ---: | --- |
| `frontend/src/components/BlocklistManagerPanel.js` | 117 | A form label must be associated with a control. |
| `frontend/src/components/BlocklistManagerPanel.js` | 128 | A form label must be associated with a control. |
| `frontend/src/components/BlocklistManagerPanel.js` | 142 | A form label must be associated with a control. |
| `frontend/src/components/ThreatHuntPanel.js` | 131 | A form label must be associated with a control. |
| `frontend/src/components/ThreatHuntPanel.js` | 146 | A form label must be associated with a control. |
| `frontend/src/components/ThreatHuntPanel.js` | 161 | A form label must be associated with a control. |
| `frontend/src/components/ThreatHuntPanel.js` | 181 | A form label must be associated with a control. |
| `frontend/src/components/ThreatHuntPanel.js` | 192 | A form label must be associated with a control. |
| `frontend/src/App.js` | 344 | A form label must be associated with a control. |
| `frontend/src/App.js` | 363 | A form label must be associated with a control. |
| `frontend/src/components/AdminUsersPanel.js` | 194 | A form label must be associated with a control. |
| `frontend/src/components/AdminUsersPanel.js` | 213 | A form label must be associated with a control. |
| `frontend/src/components/AdminUsersPanel.js` | 232 | A form label must be associated with a control. |

## Mostly Noise / Low-Value Cleanup

### React prop validation

- Rule: `javascript:S6774`
- Count: 795
- Assessment: mostly low-value reliability noise caused by React components without PropTypes. This does not mean 795 runtime bugs exist.
- Recommendation: do not add PropTypes everywhere as a rushed cleanup. Either configure Sonar/ESLint policy intentionally, migrate selectively, or handle this in a separate frontend typing/PropTypes OpenSpec.

Top files by prop-validation volume:

| File | Count |
| --- | ---: |
| `frontend/src/components/DeadLettersPanel.js` | 161 |
| `frontend/src/components/AlertTableRow.js` | 51 |
| `frontend/src/components/DashboardSection.js` | 48 |
| `frontend/src/components/IncidentsPanel.js` | 38 |
| `frontend/src/components/AlertDetailsPanel.js` | 37 |
| `frontend/src/components/AlertsTable.js` | 37 |
| `frontend/src/components/ApprovalsPanel.js` | 29 |
| `frontend/src/components/ThreatHuntEventDetails.js` | 27 |
| `frontend/src/components/AlertExpandedRow.js` | 25 |
| `frontend/src/components/SoarMetricsDashboard.js` | 23 |
| `frontend/src/components/IntegrationStatusPanel.js` | 23 |
| `frontend/src/components/AlertsToolbar.js` | 22 |
| `frontend/src/components/SocCommandCenter.js` | 20 |
| `frontend/src/components/AlertMitreDetails.js` | 16 |
| `frontend/src/components/TargetedAlertPanel.js` | 16 |
| `frontend/src/components/PlaybookExecutionTimeline.js` | 15 |
| `frontend/src/components/AlertSourceDetails.js` | 15 |
| `frontend/src/components/AlertGroupHeader.js` | 13 |
| `frontend/src/components/AlertReputationDetails.js` | 12 |
| `frontend/src/components/DashboardVisuals.js` | 12 |

## Minor Cleanup Bucket

These are safe but low priority. They should not drive architecture changes.

| Rule | File | Line | Finding |
| --- | --- | ---: | --- |
| `python:S1244` | `tests/test_targeted_correlation.py` | 182 | Do not perform equality checks with floating point values. |
| `python:S1244` | `tests/test_correlated_activity.py` | 156 | Do not perform equality checks with floating point values. |
| `python:S1244` | `tests/test_high_request_rate_detection.py` | 143 | Do not perform equality checks with floating point values. |
| `python:S1244` | `tests/test_application_exception_detection.py` | 153 | Do not perform equality checks with floating point values. |
| `python:S1244` | `tests/test_http_error_detection.py` | 148 | Do not perform equality checks with floating point values. |
| `python:S1244` | `tests/test_successful_login_after_spray_detection.py` | 226 | Do not perform equality checks with floating point values. |
| `python:S1244` | `tests/test_password_spraying_detection.py` | 163 | Do not perform equality checks with floating point values. |
| `python:S1244` | `tests/test_port_scan_detection.py` | 138 | Do not perform equality checks with floating point values. |
| `python:S1244` | `tests/test_failed_login_detection.py` | 139 | Do not perform equality checks with floating point values. |
| `javascript:S7781` | `frontend/src/components/PlaybookExecutionTimeline.js` | 28 | Prefer `String#replaceAll()` over `String#replace()`. |
| `javascript:S7781` | `frontend/src/components/SocCommandCenter.js` | 96 | Prefer `String#replaceAll()` over `String#replace()`. |
| `javascript:S7781` | `frontend/src/components/DeadLettersPanel.js` | 33 | Prefer `String#replaceAll()` over `String#replace()`. |
| `javascript:S7781` | `frontend/src/components/ApprovalsPanel.js` | 550 | Prefer `String#replaceAll()` over `String#replace()`. |
| `javascript:S7781` | `frontend/src/components/IncidentsPanel.js` | 524 | Prefer `String#replaceAll()` over `String#replace()`. |
| `javascript:S7781` | `frontend/src/components/SoarQueuePanel.js` | 477 | Prefer `String#replaceAll()` over `String#replace()`. |
| `javascript:S7773` | `frontend/src/components/SoarMetricsDashboard.js` | 106 | Prefer `Number.isNaN` over `isNaN`. |
| `javascript:S7773` | `frontend/src/components/SoarQueuePanel.js` | 75 | Prefer `Number.parseInt` over `parseInt`. |
| `python:S7519` | `routes/metrics_routes.py` | 51 | Replace with dict fromkeys method call |
| `python:S7519` | `routes/metrics_routes.py` | 47 | Replace with dict fromkeys method call |
| `javascript:S7732` | `frontend/src/reportWebVitals.js` | 2 | Avoid using `instanceof` for type checking as it can lead to unreliable results. |

## What Not To Do

- Do not attempt to fix all 844 issues in one pass.
- Do not refactor SOAR orchestration, leases, approvals, dead letters, queues, or integrations just because the reliability count is high.
- Do not add broad runtime behavior changes for PropTypes noise.
- Do not change DB timestamp semantics without a focused test-backed pass.

## Recommended Next Implementation Batches

1. Frontend tiny reliability polish: fix `DeadLettersPanel.js` sort comparator and the 13 form-label accessibility findings.
2. Backend timestamp audit: inspect `core/playbook_store.py` UTC handling and decide whether to use timezone-aware datetimes consistently with the DB schema.
3. Sonar policy decision: mark `javascript:S6774` as accepted/low priority or create a separate frontend typing/PropTypes cleanup plan.
