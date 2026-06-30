# Design: Response Outcome Alert and Queue UI

## Boundary

This child change is screen-level frontend work for Alert Details and SOAR Queue only. It depends on Phase 7 shared components (`ResponseOutcomeBadge`, `ResponseOutcomeSummary`, `outcomeLabel`, `outcomeColor`) from child change `add-response-outcome-frontend-components`. Do not start implementation before Phase 7 components are verified.

This change does not modify SOC Command Center, Source-IP Context, Attack Map, Blocklist Manager, Approvals Panel, Playbooks Panel, or SOAR Metrics (those are Phase 9). It does not modify backend routes, API contracts, canonical outcome writers, migrations, or real execution policy.

## Data Contract

All updated views consume `response_outcome` from existing API endpoints already updated by `add-response-outcome-backend-apis`:

- Alert list/detail: `response_outcome` on each alert object.
- SOAR Queue list: `response_outcome` on each queue item from `GET /admin/soar/queue/recent`.
- SOAR Queue detail: `response_outcome` on the queue item from `GET /admin/soar/queue/<id>`.

Views must handle `response_outcome: null` gracefully using the no-history state from `ResponseOutcomeSummary`.

## Alert Views

### Expanded alert row

- Add `ResponseOutcomeBadge` for the alert's `response_outcome`.
- Existing columns (severity, priority, status, source IP, timestamps) remain unchanged.
- Badge is added as a new column or inline element; do not replace the existing `response_status` display yet.

### Alert side/detail panel

- Add `ResponseOutcomeSummary` with `showRelated = true`.
- Render below or alongside the existing alert field display.
- Do not remove legacy `response_action` / `response_status` fields from the panel during Phase 8; they may be de-emphasized in a later phase.

### Response log display

- For each response log entry in the alert detail, update the status label to use `outcomeLabel` derived from the entry's canonical outcome fields.
- Replace any standalone `"Executed"` or `"Simulated"` status strings with canonical labels.
- If no `response_outcome` is present on a log entry, render using the existing legacy display (do not break existing log rendering).

### Manual action feedback

- For `block_ip` manual action responses, update the success feedback message to clearly state that a tracking-only SIEM blocklist entry was created with no firewall, provider, external, or local enforcement.
- Example: `"Recorded in SIEM blocklist (tracking only). No external enforcement occurred."` — or the equivalent canonical summary from the API response.
- If the API returns `response_outcome.execution_mode = "tracking_only"`, use `"Tracking only"` label in feedback, not `"Executed"`.

## SOAR Queue Views

### Queue list rows

- Add `ResponseOutcomeBadge` for each queue item's `response_outcome` alongside the existing status column.
- Existing columns (action, source IP, status, retry count, timestamps) remain unchanged.
- `response_outcome: null` renders badge in no-history state.

### Queue detail panel

- Add SOAR correlation id field: display `response_outcome.soar_correlation_id` when present.
- Add `ResponseOutcomeSummary` with `showRelated = true`.
- Existing fields (action, status, retry count, last error, related approval, response log, playbook execution) remain unchanged; canonical fields are added alongside.

### Batch simulation feedback

- Update the batch SOAR run simulation feedback to use `"Simulated"` not `"Executed"`.
- Example: `"N actions simulated"` not `"N actions executed"`.
- If the batch API returns a result count, use canonical labels for each outcome type in the summary.

## Test Coverage Requirements

- Alert expanded row: `ResponseOutcomeBadge` renders for non-null outcome; renders no-history state for null outcome.
- Alert detail panel: `ResponseOutcomeSummary` renders with expected fields for non-null outcome; no-history state for null.
- Response log display: canonical label used for log entries with outcome; legacy display preserved when no outcome.
- Manual action feedback: tracking-only block_ip feedback does not say `"Executed"` or imply enforcement.
- Queue list row: badge present for non-null outcome; null handled.
- Queue detail panel: SOAR correlation id rendered when present; `ResponseOutcomeSummary` rendered.
- Batch simulation feedback: output contains `"Simulated"` not `"Executed"`.
- No test may assert on legacy standalone `"Executed"` in any updated surface.

## Dependency on Phase 7

All components must be imported from the Phase 7 shared component files. Do not reimplement `outcomeLabel`, `outcomeColor`, `ResponseOutcomeBadge`, or `ResponseOutcomeSummary` inline. If Phase 7 components are not yet available, block and wait rather than duplicating logic.
