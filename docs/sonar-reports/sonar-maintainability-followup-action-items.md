# Sonar Maintainability Follow-Up Action Items

Source report: `sonar-maintainability.json` / `sonar-maintainability.csv`

## Overall Assessment

The maintainability count is high, but it is not a single signal. The largest bucket is the same React prop-validation policy issue seen in Reliability.

High-level breakdown:

- 1,341 maintainability-impact issues total
- 795 React prop-validation findings (`javascript:S6774`)
- 190 `globalThis.window` style findings (`javascript:S7764`)
- 67 Python logging cleanup findings (`python:S8572`)
- 59 frontend nested ternary readability findings (`javascript:S3358`)
- 38 Python cognitive complexity findings (`python:S3776`)
- 37 duplicated `Internal server error` literal findings (`python:S1192`)
- 27 unused local variable findings (`python:S1481`)

This should not be treated as a fix-all backlog. Several categories are style policy or would require risky refactors if handled mechanically.

## Recommended Batch 1: Low-Risk Frontend Style Cleanup

Safe only if you want to reduce Sonar count without changing behavior.

### `javascript:S7764` prefer `globalThis.window`

- Count: 190
- Classification: style/readability cleanup
- Risk: low, but repetitive
- Recommended handling: optional broad mechanical frontend pass if tests/build are clean. This is not urgent.

Top affected files:

| File | Count |
| --- | ---: |
| `frontend/src/services/playbookService.test.js` | 36 |
| `frontend/src/services/metricsService.test.js` | 26 |
| `frontend/src/services/deadLetterService.test.js` | 24 |
| `frontend/src/services/incidentService.test.js` | 21 |
| `frontend/src/services/approvalService.test.js` | 21 |
| `frontend/src/services/integrationService.test.js` | 19 |
| `frontend/src/services/notificationDeliveryService.test.js` | 12 |
| `frontend/src/services/soarQueueService.test.js` | 9 |
| `frontend/src/utils/sessionIdentity.js` | 5 |
| `frontend/src/components/SocCommandCenter.test.js` | 3 |
| `frontend/src/utils/siemPath.js` | 3 |
| `frontend/src/components/AlertsTable.js` | 3 |
| `frontend/src/components/SocCommandCenter.js` | 2 |
| `frontend/src/components/SoarMetricsDashboard.test.js` | 2 |
| `frontend/src/components/ThreatHuntPanel.js` | 2 |

### Minor frontend readability rules

Candidate rules:

- `javascript:S7735` unexpected negated condition: 12
- `javascript:S4624` nested template literals: 11
- `javascript:S6582` optional chaining: 5
- `javascript:S6479` array index keys: 3
- `javascript:S1128` unused imports: 2

Recommendation: fix selectively in UI files only when the local change is obvious. Do not refactor component structure just to satisfy these.

## Recommended Batch 2: Backend Logging Hygiene

### `python:S8572` use `logging.exception()`

- Count: 67
- Classification: real logging hygiene cleanup
- Risk: low to medium depending on call site
- Recommended handling: scoped backend pass replacing `logger.error(..., exc_info=True)` style patterns with `logger.exception(...)` only inside active exception handlers. Do not change control flow.

Top affected files:

| File | Count |
| --- | ---: |
| `routes/playbook_routes.py` | 13 |
| `routes/ingest_routes.py` | 13 |
| `routes/dead_letter_routes.py` | 6 |
| `routes/metrics_routes.py` | 5 |
| `routes/reporting_routes.py` | 5 |
| `routes/incident_routes.py` | 4 |
| `routes/alert_mutation_routes.py` | 4 |
| `routes/approval_routes.py` | 3 |
| `routes/alerts_events_routes.py` | 3 |
| `routes/blocklist_routes.py` | 3 |
| `routes/notification_delivery_routes.py` | 2 |
| `core/ip_helpers.py` | 2 |
| `engines/soar_playbook_worker.py` | 1 |
| `routes/integration_routes.py` | 1 |
| `routes/admin_routes.py` | 1 |
| `core/audit_helpers.py` | 1 |

## Recommended Batch 3: Tiny Python Cleanup

These can be safe if done one file at a time with focused tests:

- `python:S1481` unused local variables: 27
- `python:S8513` chained `endswith`: 3
- `python:S7500` dict constructor simplification: 3
- `python:S1854` dead assignment: 2
- `python:S125` commented-out code: 2

Recommendation: only fix obvious dead locals/imports/comments. Avoid touching orchestration paths unless the local diff is trivial and test-covered.

## Needs More Caution / Do Not Batch Blindly

### Cognitive complexity

- Python `python:S3776`: 38
- JavaScript `javascript:S3776`: 16
- Classification: potentially valid maintainability debt
- Risk: medium to high
- Recommendation: do not fix mechanically. Complexity refactors can change behavior, especially in SIEM/SOAR routes, stores, and UI state machines.

Top Python cognitive-complexity files:

| File | Count |
| --- | ---: |
| `engines/playbook_step_executor.py` | 4 |
| `routes/ingest_routes.py` | 4 |
| `integrations/webhook_adapter.py` | 3 |
| `routes/metrics_routes.py` | 2 |
| `routes/incident_routes.py` | 2 |
| `integrations/base_integration.py` | 2 |
| `routes/playbook_routes.py` | 2 |
| `engines/correlation_engine.py` | 2 |
| `engines/detection_config.py` | 2 |
| `integrations/email_adapter.py` | 1 |
| `engines/soar_playbook_worker.py` | 1 |
| `scripts/run_playbook_executor_once.py` | 1 |
| `core/notification_delivery_store.py` | 1 |
| `integrations/integration_registry.py` | 1 |
| `core/playbook_store.py` | 1 |

Top JavaScript cognitive-complexity files:

| File | Count |
| --- | ---: |
| `frontend/src/components/PlaybookExecutionTimeline.js` | 2 |
| `frontend/src/components/SocCommandCenter.js` | 2 |
| `frontend/src/components/DeadLettersPanel.js` | 2 |
| `frontend/src/components/SoarMetricsDashboard.js` | 1 |
| `frontend/src/components/PlaybookMetricsPanel.js` | 1 |
| `frontend/src/components/PlaybooksPanel.js` | 1 |
| `frontend/src/components/IncidentsPanel.js` | 1 |
| `frontend/src/App.js` | 1 |
| `frontend/src/components/ApprovalsPanel.js` | 1 |
| `frontend/src/components/SoarQueuePanel.js` | 1 |
| `frontend/src/components/AlertTableRow.js` | 1 |
| `frontend/src/components/DetectionRulesPanel.js` | 1 |
| `frontend/src/components/MapView.js` | 1 |

### Generic exceptions and too many parameters

- `python:S112` generic exceptions: 8
- `python:S107` too many parameters: 2
- Classification: possible design smell, not necessarily a bug
- Risk: medium
- Recommendation: audit before changing. Do not rewrite function signatures or exception hierarchy in stable SOAR paths just for Sonar.

## Likely Accept / Defer

### React PropTypes

- Rule: `javascript:S6774`
- Count: 795
- Recommendation: accept/defer unless you intentionally choose PropTypes or TypeScript as a frontend typing policy.

### Duplicated literals

- `python:S1192` duplicated `Internal server error`: 37
- `plsql:S1192` duplicated SQL/schema literals: 12
- Recommendation: generally defer. Extracting constants for simple repeated response text or schema SQL can reduce readability and create churn.

### Already handled in Reliability cleanup

- `python:S6903` datetime UTC usage should be cleared after Sonar reruns because `core/playbook_store.py` now uses `_utc_now()`.

## Exact Rule Summary

| Rule | Count | Sample message |
| --- | ---: | --- |
| `javascript:S6774` | 795 | 'compact' is missing in props validation |
| `javascript:S7764` | 190 | Prefer `globalThis.window` over `window`. |
| `python:S8572` | 67 | Use "logging.exception()" instead. |
| `javascript:S3358` | 59 | Extract this nested ternary operation into an independent statement. |
| `python:S3776` | 38 | Refactor this function to reduce its Cognitive Complexity from 20 to the 15 allowed. |
| `python:S1192` | 37 | Define a constant instead of duplicating this literal "Internal server error" 5 times. |
| `python:S1481` | 27 | Replace the unused local variable "alert_id" with "_". |
| `javascript:S3776` | 16 | Refactor this function to reduce its Cognitive Complexity from 18 to the 15 allowed. |
| `python:S6903` | 15 | Don't use `datetime.datetime.utcnow` to create this datetime object. |
| `javascript:S7735` | 12 | Unexpected negated condition. |
| `plsql:S1192` | 12 | Define a constant instead of duplicating this literal 6 times. |
| `javascript:S4624` | 11 | Refactor this code to not use nested template literals. |
| `python:S1172` | 10 | Remove the unused function parameter "now". |
| `python:S112` | 8 | Replace this generic exception class with a more specific one. |
| `javascript:S2486` | 7 | Handle this exception or don't catch it at all. |
| `javascript:S6582` | 5 | Prefer using an optional chain expression instead, as it's more concise and easier to read. |
| `python:S8513` | 3 | Replace chained "endswith" calls with a single call using a tuple argument. |
| `python:S3358` | 3 | Extract this nested conditional expression into an independent statement. |
| `python:S7500` | 3 | Replace this comprehension with passing the iterable to the dict constructor call |
| `javascript:S6479` | 3 | Do not use Array index in keys |
| `python:S107` | 2 | Function "create_dead_letter" has 15 parameters, which is greater than the 13 authorized. |
| `shelldre:S7679` | 2 | Assign this positional parameter to a local variable. |
| `python:S125` | 2 | Remove this commented out code. |
| `javascript:S1128` | 2 | Remove this unused import of 'enableHalfOpenIntegrationCircuitBreaker'. |
| `python:S1854` | 2 | Remove this assignment to local variable 'row'; the value is never used. |
| `python:S3457` | 2 | Add replacement fields or use a normal string instead of an f-string. |
| `javascript:S6819` | 1 | Use <output> instead of the "status" role to ensure accessibility across all devices. |
| `javascript:S1481` | 1 | Remove the declaration of the unused '_omit' variable. |
| `javascript:S7744` | 1 | The empty object is useless. |
| `javascript:S6653` | 1 | Use 'Object.hasOwn()' instead of 'Object.prototype.hasOwnProperty.call()'. |
| `python:S5713` | 1 | Remove this redundant Exception class; it derives from another which is already caught. |
| `javascript:S2004` | 1 | Refactor this code to not nest functions more than 4 levels deep. |
| `javascript:S7762` | 1 | Prefer `childNode.remove()` over `parentNode.removeChild(childNode)`. |
| `javascript:S7786` | 1 | `new Error()` is too unspecific for a type check. Use `new TypeError()` instead. |

## Recommended Next Step

Do not implement maintainability fixes until Sonar reruns after the recent Reliability fixes. Then audit the refreshed maintainability export because some overlap, especially `python:S6903`, should disappear.

Safest implementation order after rerun:

1. Backend logging hygiene (`python:S8572`) only inside exception handlers.
2. Optional frontend style cleanup (`globalThis.window`, negated conditions, optional chaining) if you want dashboard count reduction.
3. Tiny dead-code cleanup for unused variables/imports/comments.
4. Defer cognitive-complexity refactors unless a specific function is causing real maintenance pain.
