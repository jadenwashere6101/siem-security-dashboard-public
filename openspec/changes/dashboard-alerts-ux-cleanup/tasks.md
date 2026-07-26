## 1. Backend Alert Filtering

- [x] 1.1 Extend the shared alert filter parsing path to accept `rule_id` without changing existing search, severity, source, status, operational scope, exact IP, alert ID, sort, limit, or offset behavior.
- [x] 1.2 Add backend validation for malformed or unsupported `rule_id` values using non-sensitive detection-rule metadata or observed alert types.
- [x] 1.3 Reuse or extract shared alert SQL filter construction so `/alerts`, `/alerts/summary`, and export/report routes do not maintain divergent filter logic.
- [x] 1.4 Update CSV, PDF, and report export filtering to honor `rule_id` and the same eligible dashboard filters used by Recent Alerts.
- [x] 1.5 Add focused backend tests proving `rule_id` composes with existing filters and that alert pagination/export results match the requested filter set.

## 2. Backend Source-IP Cleanup

- [x] 2.1 Move synthetic/demo source-IP exclusion into the summary query path before source-IP grouping, counting, ranking, limiting, and map aggregation.
- [x] 2.2 Define the exclusion policy with explicit configured exclusions and known documentation/demo networks only, preserving legitimate private/internal production IPs.
- [x] 2.3 Apply the shared source-IP exclusion policy to Top Source IPs, Unique Source IPs, Attack Map markers, and source-IP map aggregation.
- [x] 2.4 Preserve Total Alerts, severity counts, and Alerts Over Time as alert-volume widgets unless product copy is intentionally changed in a future scope.
- [x] 2.5 Add focused backend tests proving synthetic/demo IPs are excluded before `LIMIT` and that source-IP-derived widgets remain mutually consistent.

## 3. Frontend Loading Cleanup

- [x] 3.1 Add one shared loading component or shared loading style helper for dashboard and Recent Alerts loading states.
- [x] 3.2 Move the spinner animation definition into `index.css` or another stylesheet imported by `frontend/src/index.js`.
- [x] 3.3 Replace duplicated spinner logic in workspace, timeline, and alert loading states with the shared implementation.
- [x] 3.4 Preserve reduced-motion behavior with a professional themed static loading state when animation is disabled.
- [x] 3.5 Add focused frontend tests or assertions covering shared loading usage and expected pending-state rendering.

## 4. Frontend Detection-Rule Filter

- [x] 4.1 Add `rule_id` to the Recent Alerts view state, default state, reset checks, summary query construction, and alerts query construction.
- [x] 4.2 Add a detection-rule filter control to the Recent Alerts toolbar that composes with existing search, severity, source, status, operational scope, exact pivots, sorting, and pagination.
- [x] 4.3 Populate rule filter options from non-sensitive detection-rule labels or observed alert types without weakening admin-only rule-management RBAC.
- [x] 4.4 Update alert export links so CSV, PDF, and report exports include the active `rule_id` and other eligible dashboard filters.
- [x] 4.5 Add focused frontend tests for query-string construction, toolbar behavior, reset behavior, pagination reset on rule changes, and export URLs.

## 5. Verification

- [x] 5.1 Run focused backend regression tests for alerts summary, alerts list filtering, and reporting exports.
- [x] 5.2 Run focused frontend tests for loading states, Recent Alerts filtering, and export URL construction.
- [x] 5.3 Run the frontend production build.
- [x] 5.4 Run `git diff --check`.
- [x] 5.5 Run `openspec validate dashboard-alerts-ux-cleanup --strict`.
- [x] 5.6 Perform local browser visual verification for the loading indicator and Top Source IPs chart.
- [ ] 5.7 After implementation is deployed through the documented VM workflow, perform runtime visual verification that loading behavior and Top Source IP filtering match the spec.

## 6. CSV Export Performance Hotfix

- [x] 6.1 Reshape `/alerts/export/csv` environment enrichment to avoid per-alert event-table latest-row lookups.
- [x] 6.2 Add the additive events index required to support latest environment lookup by source IP.
- [x] 6.3 Preserve CSV columns, filters including `rule_id`, export authorization, and latest environment semantics.
- [x] 6.4 Add focused reporting and schema tests for the bounded CSV query and migration snapshot.
- [x] 6.5 Capture local PostgreSQL before/after query-plan evidence without applying migrations to production or accessing the VM.

## 7. PDF and Confirmed Synthetic Data Follow-up

- [x] 7.1 Preserve the same-origin attachment download path for filtered PDF export while keeping CSV and TXT export links filter-backed.
- [x] 7.2 Centralize operational source-IP classification for source-IP dashboard widgets, including documentation networks and confirmed legacy synthetic sources.
- [x] 7.3 Preserve legitimate `1.1.1.1` production telemetry by avoiding broad public-IP or private/reserved range exclusions.
- [x] 7.4 Mark simulator-origin ingest payloads with canonical synthetic provenance and prevent them from being normalized as operational source metadata.
- [x] 7.5 Add a dry-run-first cleanup mechanism for confirmed synthetic alerts and associated synthetic event rows with dependency reporting, backup-before-delete, explicit confirmation, and transactional execution.
- [x] 7.6 Add focused tests for PDF/TXT/CSV filter preservation, centralized synthetic classification, and cleanup selectors that cannot capture unrelated records.
