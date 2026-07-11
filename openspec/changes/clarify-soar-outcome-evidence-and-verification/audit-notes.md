# SOAR Outcome Evidence — Mac Audit Notes

Change: `clarify-soar-outcome-evidence-and-verification`

## 1.1 Simulated / Simulation inventory (user-facing)

| Occurrence | Classification | Action |
| --- | --- | --- |
| `ResponseOutcome` label `Simulated` | Canonical | Retain; add expandable evidence |
| Queue “Run simulation batch” | Explanatory control | Clarify SimulationExecutor + no external effects |
| Queue last-batch summary | Explanatory | Rename success → simulated success; forbid real-execution language |
| Playbook timeline “Simulated” / “Simulation-Safe Execution” | Canonical / explanatory | Leave; evidence via ResponseOutcome |
| Integration Status “Simulation” / Simulate Failure|Recovery | Integration circuit controls (not outcome vocabulary) | Leave — not outcome labels |
| SOC “Simulation-Safe Execution” | Explanatory mode banner | Leave |
| Test fixtures / adapter messages | Test / internal | Leave |

No global text replacement performed.

## 1.2–1.3 Surface traces and read-model fields

| Surface | UI → service → API → tables |
| --- | --- |
| Recent Alerts / Alert Details | `AlertsTable`/`AlertDetailsPanel` → alerts API → `response_outcome` from soar outcome events |
| SOAR Queue | `SoarQueuePanel` → `/soar/queue*` → `response_action_queue` + outcome events |
| Playbooks | `PlaybooksPanel` → playbook APIs → executions + outcome events |
| Operations / Dead Letters | Dead-letter APIs (no ResponseOutcome badge required beyond existing) |
| Metrics | `SoarMetricsDashboard` → metrics/dead-letter/queue services → section sources below |

Canonical fields available on outcome payloads: `execution_mode`, `execution_state`, `simulated`, `external_executed`, `tracking_recorded`, `reason_code`, `outcome_summary`, `alert_id`, `incident_id`, `queue_id`, `playbook_execution_id`, `approval_request_id`, `notification_delivery_attempt_id`.

## 1.4 Metrics mappings

See `docs/soar_metrics_source_mapping.md`.

## 1.5 Stop confirmation

Original Mac pass: no schema/migration, Teams enablement, real firewall execution, or writer/backfill change required. Existing serializers already expose evidence fields — no additive serializer change (task 2.4 N/A).

## 9. Mac correction (VM-found defects)

### Defect 1 — stale `alerts.response_status`
- Legacy denormalized field can remain `pending` after terminal canonical outcomes.
- Corrected by removing authoritative “Response Status” presentation from Alert Expanded Row / Alerts side panel, preferring ResponseOutcome in ResponseStateSummary, and labeling Map/Source IP leftovers as legacy/non-authoritative.
- No historical `alerts` row rewrite.

### Defect 2 — approval expire mapped to `approval_denied`
- Queue/playbook/legacy producers previously collapsed expire → `reason_code=approval_denied`.
- Corrected with additive `approval_expired` in `REASON_CODES`, migration `0017_approval_expired_reason_code.sql` (CHECK expand only), producer/mapping updates, and frontend Expired vs Rejected labels.
- Historical `approval_denied` rows remain renderable; no outcome backfill.
