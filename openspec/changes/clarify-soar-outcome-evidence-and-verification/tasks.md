## 1. MAC AI — Canonical Contract Audit Pass

- [x] 1.1 Inventory every affected user-facing `Simulated`/`Simulation` occurrence and classify it as canonical, explanatory, test fixture, internal name, or misleading copy; do not globally replace text.
- [x] 1.2 Trace Recent Alerts, Queue, Playbooks, Operations, and Metrics from UI → service → API → serializer/backend → table/queue/worker/integration → resulting UI.
- [x] 1.3 Map canonical fields and related IDs available on each read model, including mode, state, `simulated`, `external_executed`, summary, reason code, and queue/execution/delivery/approval references.
- [x] 1.4 Document Metrics mappings for playbook executions/outcomes, dead letters, notification attempts, incidents, approvals, worker state, and queue actions.
- [x] 1.5 Confirm no schema/migration, Teams enablement, real firewall execution, or writer/backfill change is needed; stop and propose separately if false.

## 2. MAC AI — Outcome Evidence Implementation Pass

- [x] 2.1 Extend shared ResponseOutcome presentation with compact expandable evidence and canonical unknown/contradiction handling.
- [x] 2.2 Apply the shared evidence presentation to Recent Alerts/Alert Details, SOAR Queue, Playbooks, and SOAR Operations without duplicating vocabulary.
- [x] 2.3 Add accessible linked-record navigation for available queue, execution, delivery, approval, alert, and incident identifiers using existing contracts.
- [x] 2.4 Add only the smallest RBAC-preserving additive serializer field if stored canonical evidence is unavailable; do not add speculative browser joins.
  - Confirmed N/A: existing outcome serializers already expose required evidence fields.
- [x] 2.5 Ensure tracking-only, read-only, pending, blocked/rejected, failed, skipped, simulated, real-executed, and unknown states remain distinct.

## 3. MAC AI — Queue and Metrics Clarity Pass

- [x] 3.1 Add pre-action Queue copy explaining pending-row processing, internal lifecycle mutation, bounded batch size, SimulationExecutor, and prohibited external effects.
- [x] 3.2 Clarify simulation result copy without implying notification, provider, firewall, host, or other external execution.
- [x] 3.3 Verify SOAR Metrics per-section loading/error/zero behavior and make any misleading fallback explicit as unknown/error.
- [x] 3.4 Add developer/runtime documentation containing the endpoint-to-query/table mapping and bounded VM reconciliation procedure.

## 4. MAC AI — Automated and UI Verification Pass

- [x] 4.1 Add ResponseOutcome unit tests for every canonical state, evidence field, missing evidence, contradiction, and linked IDs.
- [x] 4.2 Add Recent Alerts, Queue, Playbooks, Operations, and linked-navigation component tests for truthful labels and evidence.
- [x] 4.3 Add backend/API regression tests for any additive serializer field and existing fail-closed/RBAC contracts.
  - No additive serializer; existing outcome contract regressions run.
- [x] 4.4 Add Metrics service/component/backend tests proving each source mapping, independent partial failure, zero-versus-error distinction, and refresh state.
- [x] 4.5 Run focused suites, canonical outcome end-to-end/regression tests, affected frontend suites, and `npm run build`.
- [x] 4.6 Perform dark-theme contrast, keyboard/focus, screen-reader naming, desktop/narrow viewport, and practical visual verification.
- [x] 4.7 Run `openspec validate clarify-soar-outcome-evidence-and-verification --strict` and `git diff --check`.

## 5. MAC AI — VM Read-Only Handoff Pass

- [x] 5.1 Define representative selection criteria without manufacturing absent states and list sanitized identifiers/statuses/counts only.
- [x] 5.2 Define alert → outcome → queue → execution → delivery → approval → integration-mode read-only trace queries/endpoints and redaction rules.
- [x] 5.3 Define per-Metrics-section bounded source queries, snapshot timestamp/tolerance, service/API checks, and contradiction reporting.
- [x] 5.4 State clean-tree, approved SHA, no-secrets, no-action-endpoint, no-remediation, rollback, and stop conditions in the handoff.

## 6. VM AI — Future Read-Only Outcome Verification Pass (Explicit Authorization Required)

- [ ] 6.1 Confirm explicit read-only authorization, clean VM worktree, and exact approved deployed SHA; stop on mismatch.
- [ ] 6.2 Select representative simulated, tracking-only, pending/blocked/failed/skipped, real-executed, and unknown records only where naturally present.
- [ ] 6.3 Trace each selected record across alert, canonical outcome, queue, playbook execution, delivery, approval, and integration mode with sanitized evidence.
- [ ] 6.4 Compare each affected user-facing label to canonical evidence and report matches, missing links, and contradictions without remediation.
- [ ] 6.5 Do not send notifications, run a simulation batch, approve/deny work, retry queues/dead letters, enable Teams/firewall, or mutate data.

## 7. VM AI — Future Read-Only Metrics Verification Pass (Explicit Authorization Required)

- [ ] 7.1 Record a verification boundary timestamp and capture sanitized SOAR Metrics API values.
- [ ] 7.2 Compare playbook, outcome, dead-letter, notification, incident, approval, worker, and queue values with their documented source tables/services.
- [ ] 7.3 Explain bounded concurrent-ingest differences; do not manufacture equality, freeze workers, or mutate records.
- [ ] 7.4 Capture sanitized service health/config mode presence without printing secrets and report unresolved source-contract drift to MAC AI.

## 8. MAC AI / VM AI — Global Stop Conditions

- [x] 8.1 Stop if canonical truth would be cosmetically renamed, ambiguous evidence promoted to real, or fail-closed behavior weakened.
- [x] 8.2 Stop if work would enable Teams or real firewall execution, expose secrets, invoke an action endpoint, mutate production, or require a migration not covered here.
- [x] 8.3 Do not commit, push, deploy, or access the VM without the corresponding explicit authorization.

Status: **Mac phase complete** (tasks 1–5 + stop-condition compliance). Parent remains open for VM phases 6–7. Do not archive. Handoffs: `docs/soar_outcome_evidence_vm_handoff.md`, `docs/soar_metrics_source_mapping.md`.
