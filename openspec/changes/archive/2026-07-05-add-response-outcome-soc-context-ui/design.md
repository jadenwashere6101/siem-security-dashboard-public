# Design: Response Outcome SOC Context UI

## Boundary

This child change is screen-level frontend work for SOC Command Center, Source-IP Context, Attack Map integration, Blocklist Manager, Approvals Panel, Playbooks Panel, and SOAR Metrics only. It depends on Phase 7 shared components and Phase 8 Alert/Queue UI being implemented first, but does not modify those surfaces.

This change does not modify Alert Details, response log display, SOAR Queue UI, backend routes, API contracts, canonical outcome writers, migrations, or real execution policy.

## Data Contract

All updated views consume `response_outcome` and canonical outcome count fields from existing API endpoints already updated by `add-response-outcome-backend-apis`:

- SOC Command Center: canonical count fields added to `/metrics/playbooks`, `/metrics/notifications`, `/metrics/incidents`, `/metrics/approvals`.
- Source-IP Context: `response_outcome` on Source-IP Context API response.
- Approvals Panel: `response_outcome` on approval list/detail from `GET /approvals`.
- Playbooks Panel: `response_outcome` on each execution from `GET /playbook-executions` and `GET /playbook-executions/<id>`.
- Blocklist Manager: tracking-only provenance fields from blocklist API.
- SOAR Metrics: canonical count fields from existing metrics endpoints.
- Attack Map popup: `response_outcome` on source-IP context if the popup shows response status; confirm whether source-IP context data flows into the popup.

## SOC Command Center

### Operational cards

- Update cards that display SOAR action counts to use canonical outcome mode/state counts from metrics endpoint response.
- Fields available: counts by `execution_mode` (observed/simulation/tracking_only/real), by `execution_state`, `external_executed` true/false, `tracking_recorded` true/false, `simulated` true/false.
- Do not remove existing card content; add canonical breakdowns alongside or replace ambiguous aggregate counts with canonical ones.
- Use `outcomeLabel` for card labels; do not use standalone `"Executed"`.

### Incident workspace

- For the selected incident, show related canonical outcomes using `ResponseOutcomeSummary`.
- Source the outcome from the incident API `response_outcome` field.
- Render no-history state when `response_outcome` is null.

## Source-IP Context Component

- Add `ResponseOutcomeBadge` and `ResponseOutcomeSummary` for recent canonical outcomes for the selected IP.
- Source from Source-IP Context API `response_outcome` or `response_outcomes` list fields.
- If the API returns multiple recent outcomes (a list), render them as a brief canonical outcome timeline using canonical labels and summaries.
- Render no-history state when no outcomes are present.

## Attack Map Popup

- During implementation, inspect whether the Attack Map popup currently shows any response status fields.
- If it shows response status: update label to use `outcomeLabel` and add `ResponseOutcomeBadge`.
- If it does not show response status: document as confirmed-no-status and make no change.
- Do not add a new backend route for the Attack Map popup regardless of what is found.

## Blocklist Manager

- For each blocklist entry, mark tracking-only entries clearly with `"Tracking only"` label via `ResponseOutcomeBadge` where tracking-only provenance is available.
- Update any wording that implies firewall, external, or local enforcement for tracking-only entries.
- If a blocklist entry has no canonical outcome, render without badge (no-history state is acceptable here since not all blocklist entries are SOAR-created).
- Preserve all existing blocklist display fields.

## Approvals Panel

- Add `ResponseOutcomeBadge` and `ResponseOutcomeSummary` to approval list rows and approval detail.
- Source from approval API `response_outcome` field.
- Use canonical language: `"Awaiting approval"` for `execution_state = awaiting_approval`; `"Blocked by approval"` for `execution_state = blocked`; `"Real executed"` for real-executed-after-approval outcomes.
- Preserve all existing approval fields (status, risk_level, decided_by, events).

## Playbooks Panel

- Add `ResponseOutcomeBadge` to each execution in the execution list.
- Add `ResponseOutcomeSummary` with `showRelated = true` to the execution detail timeline.
- Update step outcome labels in the execution timeline to use canonical execution state labels for each step event.
- Source from playbook execution API `response_outcome` and `response_outcomes` (timeline) fields.
- Preserve all existing execution fields (status, playbook id, step count, error, timestamps).

## SOAR Metrics Dashboard

- Add canonical outcome breakdown panels showing counts by:
  - `execution_mode`: observed / simulation / tracking_only / real
  - `execution_state`: observed / selected / queued / awaiting_approval / running / skipped / blocked / succeeded / failed
  - `external_executed`: true / false
  - `tracking_recorded`: true / false
  - `simulated`: true / false
- Source from canonical count fields in existing metrics endpoints.
- Preserve existing metrics display; add canonical breakdowns alongside.
- Use `outcomeLabel` for all canonical metric labels.

## Test Coverage Requirements

- SOC Command Center: canonical count displayed correctly for each mode/state; no standalone `"Executed"` in card labels.
- Source-IP Context: badge and summary rendered for non-null outcome; no-history state for null; multiple outcomes render correctly.
- Attack Map popup: confirmed behavior documented (either canonical label used, or no status display confirmed).
- Blocklist Manager: tracking-only badge rendered where provenance is available; no enforcement implication.
- Approvals Panel: awaiting/blocked/real-executed-after-approval labels correct; legacy fields preserved.
- Playbooks Panel: execution badge present; step timeline uses canonical labels; legacy fields preserved.
- SOAR Metrics: canonical breakdown counts rendered; existing metrics unchanged.
- All updated surfaces: no Phase 7 component re-implemented inline.

## Dependency on Phase 7

All components must be imported from Phase 7 shared files. Do not reimplement `outcomeLabel`, `outcomeColor`, `ResponseOutcomeBadge`, or `ResponseOutcomeSummary` inline.
