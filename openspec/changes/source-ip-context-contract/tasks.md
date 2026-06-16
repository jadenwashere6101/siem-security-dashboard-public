## 1. Backend Contract Setup

- [x] 1.1 Add a read-only source-IP context route at `GET /source-ip-context?source_ip=<ip>` behind analyst-or-super-admin access.
- [x] 1.2 Validate missing and invalid `source_ip` input with explicit HTTP 400 responses.
- [x] 1.3 Define response serialization helpers for `source_ip`, `generated_at`, `limits`, `alerts`, `incidents`, `queue`, `blocklist`, `reputation`, and `playbook_executions`.
- [x] 1.4 Ensure the response has no top-level unified `status` field.

## 2. Backend Aggregation

- [x] 2.1 Query bounded recent alerts for the requested source IP with alert lifecycle status, response fields, location, source metadata, and stored external reputation fields.
- [x] 2.2 Query bounded recent incidents directly matching the source IP and incidents linked to matching alerts.
- [x] 2.3 Query bounded recent response queue rows matching the source IP without changing queue execution semantics.
- [x] 2.4 Query blocklist entries for the source IP and expose expiry-aware effective status without mutating stored rows.
- [x] 2.5 Populate current behavioral reputation through existing behavioral reputation logic.
- [x] 2.6 Populate historical external reputation snapshots from matching alert records and identify the latest available snapshot.
- [x] 2.7 Query bounded recent playbook executions linked through matching alert IDs or incident IDs.

## 3. API Contract Tests

- [x] 3.1 Test unauthenticated, viewer, analyst, and super-admin permission behavior.
- [x] 3.2 Test missing and invalid `source_ip` error handling.
- [x] 3.3 Test successful response shape includes all required top-level sections and no fake unified top-level status.
- [x] 3.4 Test alert, incident, queue, blocklist, behavioral reputation, external reputation, and playbook execution context are populated from existing records.
- [x] 3.5 Test recent collections are bounded and response limits are exposed.
- [x] 3.6 Test the endpoint is read-only and does not mutate alerts, incidents, queue rows, playbook executions, approvals, blocklist rows, or SOAR state.

## 4. Frontend Integration Preparation

- [ ] 4.1 Add a frontend source-IP context service that calls the normalized backend contract.
- [ ] 4.2 Add a shared source-IP context display component with explicit labels for alert status, incident status, queue execution status, blocklist status, behavioral reputation, and external reputation snapshots.
- [ ] 4.3 Integrate the shared context display into Alert Details without duplicating frontend joins.
- [ ] 4.4 Integrate the shared context display into the Map popup without relying only on the clicked alert object.
- [ ] 4.5 Defer SOC Command Center source-IP enhancements unless implementation evidence justifies a later scoped change.

## 5. Validation Checklist

- [x] 5.1 Run backend syntax checks for any changed backend modules.
- [x] 5.2 Run source-IP context API contract tests.
- [ ] 5.3 Run focused frontend tests for Alert Details and Map popup integrations when frontend work begins.
- [x] 5.4 Confirm no alert, incident, queue, approval, playbook, SOAR orchestration, or schema lifecycle behavior changed.
- [x] 5.5 Confirm no mutation endpoint was introduced for source-IP context.
- [ ] 5.6 Confirm frontend source-IP context rendering consumes the backend contract rather than recomputing cross-tab joins.
