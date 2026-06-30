## 8. Phase 8 - Alert Details and SOAR Queue UI

> Parent roadmap task reference: tasks 8.1–8.8 in `openspec/changes/clarify-soar-response-outcomes/tasks.md`.
> The parent remains the master roadmap. Mark parent tasks complete after this child is verified.
> Depends on Phase 7 child change `add-response-outcome-frontend-components`.

### Pre-Implementation

- [x] 8.0.1 Confirm Phase 7 shared components (`ResponseOutcomeBadge`, `ResponseOutcomeSummary`, `outcomeLabel`, `outcomeColor`) are implemented and all Phase 7 tests pass.
- [x] 8.0.2 Confirm the alert list and detail API returns `response_outcome` (verify against live or test API response).
- [x] 8.0.3 Confirm the SOAR Queue recent and detail API returns `response_outcome` (verify against live or test API response).
- [x] 8.0.4 Identify alert expanded row, alert detail panel, and response log display locations in the frontend source.
- [x] 8.0.5 Identify SOAR Queue list row, detail panel, and batch simulation feedback locations in the frontend source.

### Alert Details — Expanded Row

- [x] 8.1 Add `ResponseOutcomeBadge` to the expanded alert row using the alert's `response_outcome` field.
- [x] 8.2 Verify existing alert row columns (severity, priority, status, source IP, timestamps) remain unchanged.
- [x] 8.3 Verify badge renders the no-history state gracefully when `response_outcome` is null.

### Alert Details — Side/Detail Panel

- [x] 8.4 Add `ResponseOutcomeSummary` with `showRelated = true` to the alert detail panel.
- [x] 8.5 Render the summary below or alongside the existing alert fields; do not remove legacy `response_action`/`response_status` display.
- [x] 8.6 Verify summary renders all canonical fields (selected action, decision source, execution actor, booleans, outcome summary, reason code) when outcome is non-null.
- [x] 8.7 Verify summary renders no-history state when `response_outcome` is null.

### Alert Details — Response Log Display

- [x] 8.8 Update the response log display for each log entry to use `outcomeLabel` for canonical outcome status labels.
- [x] 8.9 Replace any standalone `"Executed"` or `"Simulated"` strings in log entry display with canonical labels.
- [x] 8.10 Verify legacy display is preserved when no `response_outcome` is present on a log entry.

### Manual Action Feedback

- [x] 8.11 Update manual `block_ip` action success feedback to clearly describe tracking-only blocklist behavior: SIEM-only, no firewall, provider, external, or local enforcement.
- [x] 8.12 Use `"Tracking only"` canonical label in feedback when `response_outcome.execution_mode = "tracking_only"`.
- [x] 8.13 Verify feedback does not use standalone `"Executed"` or imply external enforcement.

### SOAR Queue — List Rows

- [x] 8.14 Add `ResponseOutcomeBadge` to each queue list row using the item's `response_outcome`.
- [x] 8.15 Verify existing queue list columns (action, source IP, status, retry count, timestamps) remain unchanged.
- [x] 8.16 Verify badge renders no-history state when `response_outcome` is null.

### SOAR Queue — Detail Panel

- [x] 8.17 Add SOAR correlation id field to queue detail: display `response_outcome.soar_correlation_id` when present.
- [x] 8.18 Add `ResponseOutcomeSummary` with `showRelated = true` to queue detail panel.
- [x] 8.19 Verify existing queue detail fields (action, status, retry count, last error, related approval, response log, playbook execution) remain unchanged.

### SOAR Queue — Batch Simulation Feedback

- [x] 8.20 Update batch SOAR run simulation feedback to use `"Simulated"` not `"Executed"`.
- [x] 8.21 Verify batch feedback label reads `"N actions simulated"` or equivalent canonical phrasing.

### Tests

- [x] 8.22 Add frontend tests for alert expanded row: badge renders for non-null outcome; no-history state for null.
- [x] 8.23 Add frontend tests for alert detail panel: `ResponseOutcomeSummary` renders expected fields; no-history state for null.
- [x] 8.24 Add frontend tests for response log display: canonical label used with outcome; legacy display preserved without outcome.
- [x] 8.25 Add frontend tests for manual action feedback: tracking-only copy present; `"Executed"` not present in updated feedback.
- [x] 8.26 Add frontend tests for queue list row: badge present for non-null; null handled without crash.
- [x] 8.27 Add frontend tests for queue detail panel: SOAR correlation id rendered; `ResponseOutcomeSummary` rendered.
- [x] 8.28 Add frontend tests for batch simulation feedback: `"Simulated"` present; `"Executed"` not present.

### Validation

- [x] 8.29 Run the frontend test suite; confirm all new tests pass with zero failures.
- [x] 8.30 Verify no Phase 7 component is re-implemented inline in any Phase 8 file.
- [x] 8.31 Run `openspec validate add-response-outcome-alert-queue-ui --strict` and confirm valid.
- [x] 8.32 Run `git diff --check` and confirm no whitespace errors.
