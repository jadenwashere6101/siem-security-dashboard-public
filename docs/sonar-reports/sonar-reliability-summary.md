# SonarCloud Reliability Issues

Organization: `jadenwashere6101`
Project key: `jadenwashere6101_siem-security-dashboard-public`
Open reliability-impact issues: `844`

## By Severity

- MAJOR: 817
- CRITICAL: 16
- MINOR: 11

## By Rule

- `javascript:S6774`: 795 - 'compact' is missing in props validation
- `python:S6903`: 15 - Don't use `datetime.datetime.utcnow` to create this datetime object.
- `javascript:S6853`: 13 - A form label must be associated with a control.
- `python:S1244`: 9 - Do not perform equality checks with floating point values.
- `javascript:S7781`: 6 - Prefer `String#replaceAll()` over `String#replace()`.
- `javascript:S7773`: 2 - Prefer `Number.isNaN` over `isNaN`.
- `python:S7519`: 2 - Replace with dict fromkeys method call
- `javascript:S2871`: 1 - Provide a compare function that depends on "String.localeCompare", to reliably sort elements alphabetically.
- `javascript:S7732`: 1 - Avoid using `instanceof` for type checking as it can lead to unreliable results.

## By Area

- `frontend`: 818
- `core`: 15
- `tests`: 9
- `routes`: 2

## Top Files

- `frontend/src/components/DeadLettersPanel.js`: 163
- `frontend/src/components/AlertTableRow.js`: 51
- `frontend/src/components/DashboardSection.js`: 48
- `frontend/src/components/IncidentsPanel.js`: 39
- `frontend/src/components/AlertDetailsPanel.js`: 37
- `frontend/src/components/AlertsTable.js`: 37
- `frontend/src/components/ApprovalsPanel.js`: 30
- `frontend/src/components/ThreatHuntEventDetails.js`: 27
- `frontend/src/components/AlertExpandedRow.js`: 25
- `frontend/src/components/SoarMetricsDashboard.js`: 24
- `frontend/src/components/IntegrationStatusPanel.js`: 23
- `frontend/src/components/AlertsToolbar.js`: 22
- `frontend/src/components/SocCommandCenter.js`: 21
- `frontend/src/components/PlaybookExecutionTimeline.js`: 16
- `frontend/src/components/AlertMitreDetails.js`: 16
- `frontend/src/components/TargetedAlertPanel.js`: 16
- `core/playbook_store.py`: 15
- `frontend/src/components/AlertSourceDetails.js`: 15
- `frontend/src/components/AlertGroupHeader.js`: 13
- `frontend/src/components/SoarQueuePanel.js`: 12
- `frontend/src/components/AlertReputationDetails.js`: 12
- `frontend/src/components/DashboardVisuals.js`: 12
- `frontend/src/components/ThreatHuntPanel.js`: 12
- `frontend/src/components/AlertNotesPanel.js`: 11
- `frontend/src/components/DashboardMetrics.js`: 10
- `frontend/src/components/SeverityChart.js`: 10
- `frontend/src/components/AlertCorrelationSignals.js`: 9
- `frontend/src/components/AlertExportLinks.js`: 9
- `frontend/src/components/ResolvedAlertsTable.js`: 9
- `frontend/src/components/BlocklistManagerPanel.js`: 9
