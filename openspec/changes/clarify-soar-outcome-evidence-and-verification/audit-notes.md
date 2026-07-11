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

## 11. Mac correction (stale simulation framing after task 10 mode-semantics fix)

Task 10 (`10.3`) changed queue lifecycle outcome modes to be derived from actual action/result instead of hard-coded simulation — `block_ip` → `tracking_only` (real durable SIEM Blocklist write), `monitor`/`flag_high_priority`/`escalate` → `internal` (real internal state change), only unrecognized/legacy actions still route to `SimulationExecutor`. Row 10/11 of the 1.1 table above ("Clarify SimulationExecutor + no external effects", "Rename success → simulated success") were written *before* task 10 and were never revisited — they described the pre-10.3 model. This pass corrects that drift:

| Occurrence (original) | Why stale | Correction |
| --- | --- | --- |
| Queue “Run simulation batch” subtitle/help/tooltip: “SimulationExecutor only” | `CANONICAL_QUEUE_ACTIONS` bypasses `SimulationExecutor` entirely via `execute_response_command` | Renamed control to “Process queue batch”; copy now states block_ip/monitor/flag_high_priority write real internal/tracking-only records, other actions use the simulation executor |
| Queue result “X queue actions simulated internally” / “Simulated success” | A `block_ip` or `monitor` success is a real durable write, not a simulation | “processed internally” / “Processed successfully”; added `summary.by_mode` breakdown so mixed batches report truthfully |
| `/admin/soar/worker/run-once` response `mode: "simulation"` (whole-batch label) | Applied uniformly regardless of per-row canonical mode | Renamed to `requested_executor_mode` (describes the request-side executor gate only); added `summary.by_mode` / `summary.success_by_mode` |
| `PlaybookMetricsPanel.js` “Simulation only… No real remediation… is active” | Contradicts task 10.4 (playbook non-adapter/lifecycle outcomes classified as internal/read_only/tracking-only/real, not hard-coded simulation) | Rewritten to match the live `SoarMetricsDashboard.js` notice; component currently unmounted (dead code) but corrected for consistency |
| `IncidentsPanel.js` SOAR Timeline notice “simulation-only unless explicitly marked otherwise” | Framed simulation as default/exception-driven; action type (not an exception flag) determines mode | “Each event’s mode (internal, tracking-only, simulated, or real) is determined by the backend and shown per event” |
| `IntegrationStatusPanel.js` Firewall adapter description “Plans containment actions in simulation only” | `block_ip` is `tracking_only` (real durable write), not simulation | “Records containment actions as tracking-only SIEM Blocklist entries; it does not change firewall rules” |
| `playbookService.js` / `PlaybooksPanel.js` error fallback text calling execution control actions “simulation” | Retry/abandon/resume act on playbook executions that may include real/internal/tracking-only steps | Generic “playbook execution” / “Playbook execution control action” wording |

Left unchanged (still accurate, not touched): `ResponseOutcome` canonical `Simulated` label; per-event `playbook_adapter_simulated` → “Simulated adapter step”; Integration Status circuit-breaker “Simulation” controls (unrelated in-memory test harness, not outcome vocabulary); SOC/ExecutionSafetyModelPanel “Simulation-Safe Execution” banner (already paired with “Real Workflow” capability matrix); Teams simulation-only behavior; `SoarMetricsDashboard.js` notice (already correct).

No global text replacement performed; no backend writer/outcome-event semantics changed.
