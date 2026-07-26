## 1. Backend Recon History API

- [x] 1.1 Extend recon list argument parsing for `limit`, `offset`, `status`, `severity`, `confidence`, `classification`, `search`, `time_range`, `start_time`, `end_time`, and `sort` with clear validation errors.
- [x] 1.2 Update `list_recon_activities` to apply filters before pagination and return `items`, `total`, `limit`, `offset`, `sort`, and filter metadata while preserving current default bounded behavior.
- [x] 1.3 Add a compact recon detail response that includes summary, confidence, classification, reasons, missing evidence, and investigation pivots without embedding an unbounded alert list.
- [x] 1.4 Add or extend a linked-alert endpoint for recon activity alerts with `limit`, `offset`, `total`, and deterministic sorting.
- [ ] 1.5 Review local query plans for new list/search paths and add only justified indexes/migration/schema updates if existing indexes are insufficient.

## 2. Recon Intelligence Model

- [x] 2.1 Add a recon intelligence scoring helper at the recon store boundary using linked alert count, source count, duration, target/service consistency, alert-type diversity, incident correlation, and progression evidence.
- [x] 2.2 Define classification tiers `recon_cluster`, `possible_campaign`, and `campaign_recon` with confidence levels and explainable reason codes.
- [x] 2.3 Suppress campaign wording for one-alert, one-source, short-duration activities with no incident or progression evidence.
- [x] 2.4 Preserve existing recon activity enrollment, alert context updates, notification eligibility behavior, and AI/read-model compatibility.
- [x] 2.5 Store the new projection in `summary` only if needed for list performance; otherwise compute it from existing summary fields at response time.

## 3. Frontend Recon Experience

- [x] 3.1 Add or wire a dedicated Recon workspace section reachable from the SOC Command Center.
- [x] 3.2 Update `reconActivityService` for paginated history, filters, search, detail loading, and linked-alert pagination.
- [x] 3.3 Keep the SOC Command Center recon card as a bounded operational summary with a clear "view all recon history" action.
- [x] 3.4 Build Recon workspace controls for time range, status, severity, confidence/classification, search, pagination, and reset.
- [x] 3.5 Build recon detail panels that show confidence reasons, missing evidence, target/service context, incident/source/alert pivots, and paginated linked alerts.

## 4. Tests

- [x] 4.1 Add backend tests for recon list pagination, totals, filtering, search, time ranges, and invalid query validation.
- [x] 4.2 Add backend tests for linked-alert pagination and compact detail payload bounds.
- [x] 4.3 Add backend tests proving weak one-alert recon is classified as low-confidence cluster and not campaign recon.
- [x] 4.4 Add backend tests proving multi-evidence recon reaches possible/campaign tiers with reason codes.
- [x] 4.5 Add frontend tests for Command Center summary behavior, Recon workspace filters, pagination, reset, detail loading, linked-alert pagination, and investigation pivots.

## 5. Documentation and Verification

- [x] 5.1 Add behavior documentation for recon confidence/classification terminology if implementation introduces analyst-visible labels.
- [x] 5.2 Run focused backend recon tests and Python compilation for modified Python modules.
- [x] 5.3 Run focused frontend tests for recon workspace and command-center changes.
- [x] 5.4 Run `cd frontend && npm run build`.
- [x] 5.5 Run `git diff --check`.
- [x] 5.6 Run `openspec validate recon-intelligence-cleanup --strict`.
- [ ] 5.7 Perform local browser verification for Command Center summary, Recon workspace pagination/filtering, detail layout, linked-alert paging, and responsive behavior.
- [x] 5.8 Document rollback notes and VM sync/runtime browser verification requirements in the implementation handoff.
