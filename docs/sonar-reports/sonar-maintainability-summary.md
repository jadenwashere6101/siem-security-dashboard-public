# SonarCloud Maintainability Issues

Organization: `jadenwashere6101`
Project key: `jadenwashere6101_siem-security-dashboard-public`
Open maintainability-impact issues: `1341`

## By Severity

- MAJOR: 976
- MINOR: 246
- CRITICAL: 119

## By Rule

- `javascript:S6774`: 795 (MAJOR:795) - 'compact' is missing in props validation
- `javascript:S7764`: 190 (MINOR:190) - Prefer `globalThis.window` over `window`.
- `python:S8572`: 67 (MAJOR:67) - Use "logging.exception()" instead.
- `javascript:S3358`: 59 (MAJOR:59) - Extract this nested ternary operation into an independent statement.
- `python:S3776`: 38 (CRITICAL:38) - Refactor this function to reduce its Cognitive Complexity from 20 to the 15 allowed.
- `python:S1192`: 37 (CRITICAL:37) - Define a constant instead of duplicating this literal "Internal server error" 5 times.
- `python:S1481`: 27 (MINOR:27) - Replace the unused local variable "alert_id" with "_".
- `javascript:S3776`: 16 (CRITICAL:16) - Refactor this function to reduce its Cognitive Complexity from 18 to the 15 allowed.
- `python:S6903`: 15 (CRITICAL:15) - Don't use `datetime.datetime.utcnow` to create this datetime object.
- `javascript:S7735`: 12 (MINOR:12) - Unexpected negated condition.
- `plsql:S1192`: 12 (CRITICAL:12) - Define a constant instead of duplicating this literal 6 times.
- `javascript:S4624`: 11 (MAJOR:11) - Refactor this code to not use nested template literals.
- `python:S1172`: 10 (MAJOR:10) - Remove the unused function parameter "now".
- `python:S112`: 8 (MAJOR:8) - Replace this generic exception class with a more specific one.
- `javascript:S2486`: 7 (MINOR:7) - Handle this exception or don't catch it at all.
- `javascript:S6582`: 5 (MAJOR:5) - Prefer using an optional chain expression instead, as it's more concise and easier to read.
- `python:S8513`: 3 (MAJOR:3) - Replace chained "endswith" calls with a single call using a tuple argument.
- `python:S3358`: 3 (MAJOR:3) - Extract this nested conditional expression into an independent statement.
- `python:S7500`: 3 (MINOR:3) - Replace this comprehension with passing the iterable to the dict constructor call
- `javascript:S6479`: 3 (MAJOR:3) - Do not use Array index in keys
- `python:S107`: 2 (MAJOR:2) - Function "create_dead_letter" has 15 parameters, which is greater than the 13 authorized.
- `shelldre:S7679`: 2 (MAJOR:2) - Assign this positional parameter to a local variable.
- `python:S125`: 2 (MAJOR:2) - Remove this commented out code.
- `javascript:S1128`: 2 (MINOR:2) - Remove this unused import of 'enableHalfOpenIntegrationCircuitBreaker'.
- `python:S1854`: 2 (MAJOR:2) - Remove this assignment to local variable 'row'; the value is never used.
- `python:S3457`: 2 (MAJOR:2) - Add replacement fields or use a normal string instead of an f-string.
- `javascript:S6819`: 1 (MAJOR:1) - Use <output> instead of the "status" role to ensure accessibility across all devices.
- `javascript:S1481`: 1 (MINOR:1) - Remove the declaration of the unused '_omit' variable.
- `javascript:S7744`: 1 (MINOR:1) - The empty object is useless.
- `javascript:S6653`: 1 (MINOR:1) - Use 'Object.hasOwn()' instead of 'Object.prototype.hasOwnProperty.call()'.
- `python:S5713`: 1 (MINOR:1) - Remove this redundant Exception class; it derives from another which is already caught.
- `javascript:S2004`: 1 (CRITICAL:1) - Refactor this code to not nest functions more than 4 levels deep.
- `javascript:S7762`: 1 (MAJOR:1) - Prefer `childNode.remove()` over `parentNode.removeChild(childNode)`.
- `javascript:S7786`: 1 (MINOR:1) - `new Error()` is too unspecific for a type check. Use `new TypeError()` instead.

## By Area

- `frontend`: 1107
- `routes`: 97
- `engines`: 34
- `core`: 34
- `tests`: 28
- `integrations`: 12
- `schema.sql`: 8
- `scripts`: 7
- `migrations`: 4
- `adapters`: 4
- `helpers`: 3
- `siem-azure-function`: 3

## Top Files

- `frontend/src/components/DeadLettersPanel.js`: 174
- `frontend/src/components/AlertTableRow.js`: 56
- `frontend/src/components/DashboardSection.js`: 48
- `frontend/src/components/IncidentsPanel.js`: 47
- `frontend/src/components/AlertsTable.js`: 45
- `frontend/src/components/AlertDetailsPanel.js`: 37
- `frontend/src/components/ApprovalsPanel.js`: 36
- `frontend/src/services/playbookService.test.js`: 36
- `frontend/src/components/SocCommandCenter.js`: 29
- `frontend/src/components/SoarMetricsDashboard.js`: 27
- `frontend/src/components/ThreatHuntEventDetails.js`: 27
- `frontend/src/services/metricsService.test.js`: 26
- `frontend/src/components/AlertExpandedRow.js`: 25
- `frontend/src/services/deadLetterService.test.js`: 24
- `frontend/src/components/IntegrationStatusPanel.js`: 24
- `frontend/src/components/PlaybooksPanel.js`: 23
- `routes/ingest_routes.py`: 22
- `frontend/src/components/AlertsToolbar.js`: 22
- `frontend/src/components/PlaybookExecutionTimeline.js`: 21
- `frontend/src/services/incidentService.test.js`: 21
- `frontend/src/services/approvalService.test.js`: 21
- `core/playbook_store.py`: 19
- `routes/playbook_routes.py`: 19
- `frontend/src/services/integrationService.test.js`: 19
- `frontend/src/components/SoarQueuePanel.js`: 17
- `frontend/src/components/AlertMitreDetails.js`: 16
- `frontend/src/components/TargetedAlertPanel.js`: 16
- `frontend/src/components/AlertSourceDetails.js`: 15
- `frontend/src/components/AlertGroupHeader.js`: 13
- `frontend/src/services/notificationDeliveryService.test.js`: 12
- `frontend/src/components/AlertNotesPanel.js`: 12
- `frontend/src/components/AlertReputationDetails.js`: 12
- `frontend/src/components/DashboardVisuals.js`: 12
- `frontend/src/components/ThreatHuntPanel.js`: 12
- `frontend/src/components/MapView.js`: 11
- `frontend/src/components/SeverityChart.js`: 11
- `engines/detection_engine.py`: 10
- `frontend/src/components/DashboardMetrics.js`: 10
- `routes/metrics_routes.py`: 9
- `frontend/src/services/soarQueueService.test.js`: 9
