# SOAR Metrics Source Mapping

Owner: Mac AI documentation for `clarify-soar-outcome-evidence-and-verification`.

UI component: `frontend/src/components/SoarMetricsDashboard.js`  
Each section sets `data-metrics-source` and keeps independent loading/error state. Errors render as **unknown/unavailable**, never as zero.

| UI section | Frontend service | Primary backend source | Notes |
| --- | --- | --- | --- |
| Playbook Metrics | `getPlaybookMetrics` | Playbook execution / outcome aggregates | Status + recent success/fail |
| Dead Letter Metrics | `getDeadLetterMetrics` | `soar_dead_letters` (and related) | Open/retrying distinct from zero |
| Notification Delivery Metrics | `getNotificationDeliveryMetrics` | Notification delivery attempt tables | Simulation vs real mode counts; not receipt proof |
| Incident Metrics | `getIncidentMetrics` | SOAR incidents | Status/severity breakdowns |
| Approval Metrics | `getApprovalMetrics` | SOAR approvals | Pending/approved/denied/expired |
| Worker Operations | `getPlaybookWorkerMetrics` (super_admin) | Worker runtime / lease / recovery views | Heartbeat unknown ≠ healthy |
| SOAR Queue Health | `loadSoarQueueStatus` (super_admin) | `response_action_queue` status counts | Pending/running/failed/skipped |

Refresh: client interval `REFRESH_INTERVAL_MS` (60s) plus manual refresh; last refresh time shown in UI.

## Bounded VM reconciliation procedure

1. Record snapshot timestamp T.
2. Call each metrics endpoint once; capture sanitized counts only.
3. Within ± tolerance window, run documented SQL/count queries per section.
4. Report matches or concurrent-ingest deltas; do not manufacture equality.
5. Stop on dirty tree, wrong SHA, secrets exposure risk, or any non-read-only tool.
