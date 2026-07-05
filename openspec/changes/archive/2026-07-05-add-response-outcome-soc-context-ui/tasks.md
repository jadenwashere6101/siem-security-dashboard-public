## 9. Phase 9 - SOC Command Center, Source-IP Context, Map, and Blocklist UI

> Parent roadmap task reference: tasks 9.1–9.9 in `openspec/changes/clarify-soar-response-outcomes/tasks.md`.
> The parent remains the master roadmap. Mark parent tasks complete after this child is verified.
> Depends on Phase 7 (`add-response-outcome-frontend-components`) and Phase 8 (`add-response-outcome-alert-queue-ui`).

### Pre-Implementation

- [x] 9.0.1 Confirm Phase 7 shared components are implemented and all Phase 7 tests pass.
- [x] 9.0.2 Confirm Phase 8 Alert Details and SOAR Queue UI are implemented and all Phase 8 tests pass.
- [x] 9.0.3 Confirm metrics endpoints return canonical count fields (`outcome_counts` by mode, state, booleans) — verify against live or test API response.
- [x] 9.0.4 Confirm Source-IP Context API returns `response_outcome` field(s) — verify against live or test API response.
- [x] 9.0.5 Confirm Approvals Panel API returns `response_outcome` on each approval — verify against live or test API response.
- [x] 9.0.6 Confirm Playbooks Panel API returns `response_outcome` on executions — verify against live or test API response.
- [x] 9.0.7 Inspect Attack Map popup to determine whether it currently displays any response status fields; document finding.

### SOC Command Center — Operational Cards

- [x] 9.1 Update SOC Command Center operational SOAR action count cards to display canonical outcome mode/state counts from metrics endpoint `outcome_counts` fields.
- [x] 9.2 Use `outcomeLabel` for all canonical outcome labels in cards; do not use standalone `"Executed"`.
- [x] 9.3 Verify existing card content is preserved; canonical breakdowns are added alongside, not replacing, existing counts.

### SOC Command Center — Incident Workspace

- [x] 9.4 Add `ResponseOutcomeSummary` to the incident workspace for the selected incident's `response_outcome`.
- [x] 9.5 Render no-history state when `response_outcome` is null.

### Source-IP Context Component

- [x] 9.6 Add `ResponseOutcomeBadge` for the most recent canonical outcome for the selected IP.
- [x] 9.7 Add `ResponseOutcomeSummary` for the most recent canonical outcome detail.
- [x] 9.8 If the API returns multiple recent outcomes, render a brief canonical outcome list with `outcomeLabel` and `outcome_summary` for each.
- [x] 9.9 Render no-history state when no canonical outcomes are returned.

### Attack Map Popup

- [x] 9.10 Inspect the Attack Map popup source to confirm whether response status fields are currently displayed.
- [x] 9.11 If response status is displayed: update the status label to use `outcomeLabel` and add `ResponseOutcomeBadge`.
- [x] 9.12 If no response status is displayed: document as confirmed-no-status and skip modification.
- [x] 9.13 Do not add a new backend route for the Attack Map popup in either case.

### Blocklist Manager

- [x] 9.14 Add `ResponseOutcomeBadge` with `"Tracking only"` label to blocklist entries where tracking-only canonical outcome provenance is available.
- [x] 9.15 Update any wording that implies firewall, external, or local enforcement for tracking-only entries.
- [x] 9.16 Verify blocklist entries without canonical outcome do not show a badge; preserve existing display.
- [x] 9.17 Verify all existing blocklist display fields are preserved.

### Approvals Panel

- [x] 9.18 Add `ResponseOutcomeBadge` to approval list rows using the approval's `response_outcome`.
- [x] 9.19 Add `ResponseOutcomeSummary` to the approval detail panel.
- [x] 9.20 Verify canonical labels used: `"Awaiting approval"` for awaiting, `"Blocked by approval"` for blocked, `"Real executed"` for real post-approval execution.
- [x] 9.21 Verify all existing approval fields (status, risk_level, decided_by, events) are preserved.

### Playbooks Panel

- [x] 9.22 Add `ResponseOutcomeBadge` to each execution in the playbook execution list.
- [x] 9.23 Add `ResponseOutcomeSummary` with `showRelated = true` to the execution detail timeline.
- [x] 9.24 Update step outcome labels in the execution timeline to use canonical execution state labels.
- [x] 9.25 Verify all existing execution fields (status, playbook id, step count, error, timestamps) are preserved.

### SOAR Metrics Dashboard

- [x] 9.26 Add canonical outcome breakdown panels for `execution_mode` counts (observed/simulation/tracking_only/real).
- [x] 9.27 Add canonical outcome breakdown for `execution_state` counts.
- [x] 9.28 Add `external_executed`, `tracking_recorded`, and `simulated` true/false count displays.
- [x] 9.29 Use `outcomeLabel` for all canonical metric labels.
- [x] 9.30 Verify existing metrics display is preserved; canonical breakdowns are additive.

### Tests

- [x] 9.31 Add frontend tests for SOC Command Center: canonical counts rendered; no standalone `"Executed"`.
- [x] 9.32 Add frontend tests for SOC Command Center incident workspace: `ResponseOutcomeSummary` renders; null renders no-history.
- [x] 9.33 Add frontend tests for Source-IP Context: badge and summary for non-null; no-history for null; multiple outcomes list.
- [x] 9.34 Add frontend test or documentation for Attack Map popup finding (canonical label or confirmed no-status).
- [x] 9.35 Add frontend tests for Blocklist Manager: tracking-only badge rendered; no enforcement implication; entries without outcome unaffected.
- [x] 9.36 Add frontend tests for Approvals Panel: awaiting/blocked/real-executed labels correct; legacy fields preserved.
- [x] 9.37 Add frontend tests for Playbooks Panel: execution badge; step timeline canonical labels; legacy fields preserved.
- [x] 9.38 Add frontend tests for SOAR Metrics dashboard: canonical breakdown counts rendered; existing metrics unchanged.

### Validation

- [x] 9.39 Run the frontend test suite; confirm all new tests pass with zero failures.
- [x] 9.40 Verify no Phase 7 component is re-implemented inline in any Phase 9 file.
- [x] 9.41 Run `openspec validate add-response-outcome-soc-context-ui --strict` and confirm valid.
- [x] 9.42 Run `git diff --check` and confirm no whitespace errors.
