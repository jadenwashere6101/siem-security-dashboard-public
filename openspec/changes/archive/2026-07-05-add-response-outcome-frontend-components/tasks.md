## 7. Phase 7 - Frontend Shared Outcome Components

> Parent roadmap task reference: tasks 7.1–7.7 in `openspec/changes/clarify-soar-response-outcomes/tasks.md`.
> The parent remains the master roadmap. Mark parent tasks complete after this child is verified.

### Pre-Implementation

- [x] 7.0.1 Confirm the frontend component directory convention from existing component files (e.g., `static/js/`, `templates/`, or equivalent).
- [x] 7.0.2 Confirm the frontend test runner and test file convention from existing test files.
- [x] 7.0.3 Confirm that no screen-level component already duplicates canonical label logic; if found, document it and plan consolidation.

### Shared Label and Color Utility

- [x] 7.1 Create `outcomeLabel(outcome)` utility that maps `execution_mode`, `execution_state`, `external_executed`, `tracking_recorded`, and `simulated` to the canonical UI labels from parent Decision 7; return `"Observed only"` for null input.
- [x] 7.2 Create `outcomeColor(outcome)` utility that maps canonical conditions to semantic color tokens; handle null input with neutral color.
- [x] 7.3 Ensure neither utility references legacy fields (`response_action`, `response_status`, `executed`) as input.
- [x] 7.4 Create shared formatter utility that avoids standalone `executed` copy in any produced string; use `"Simulated succeeded"`, `"Tracking-only recorded"`, `"Real executed"` for composite labels.

### ResponseOutcomeBadge Component

- [x] 7.5 Create `ResponseOutcomeBadge` component that accepts an `outcome` prop (or null).
- [x] 7.6 Render badge label from `outcomeLabel(outcome)`.
- [x] 7.7 Apply color from `outcomeColor(outcome)`.
- [x] 7.8 Include accessible `aria-label` containing label text, `execution_mode`, and `execution_state` when non-null.
- [x] 7.9 Verify component does not crash for any valid canonical mode/state combination or null input.

### ResponseOutcomeSummary Component

- [x] 7.10 Create `ResponseOutcomeSummary` component that accepts `outcome` and `showRelated` props.
- [x] 7.11 Render selected action, decision source, execution actor (when present), execution booleans as human-readable clauses, outcome summary text, and reason code explanation when `outcome` is non-null.
- [x] 7.12 Render a clear `"No response outcome recorded."` no-history state when `outcome` is null; do not render empty.
- [x] 7.13 Render related ids section (alert id, queue id, playbook execution id, approval request id, notification delivery id) when `showRelated = true` and outcome is non-null.
- [x] 7.14 Verify no component string contains standalone `executed` without a qualifying mode prefix.

### UI Handling for Inferred Legacy Outcomes

- [x] 7.15 Add null-outcome display state that does not attempt to infer canonical facts from legacy `response_action` or `response_status` fields in the component layer.
- [x] 7.16 Document in component comments that inferred compatibility (if needed) must be provided by the backend `resolve_*_outcome` helper and passed via the API, not derived in the component.

### Tests

- [x] 7.17 Add unit tests for `outcomeLabel` covering all four `execution_mode` values, all nine `execution_state` values, `external_executed=true`, `tracking_recorded=true`, `simulated=true`, null input, and every `reason_code` value.
- [x] 7.18 Add unit tests for `outcomeColor` covering all canonical conditions and null input.
- [x] 7.19 Add rendering tests for `ResponseOutcomeBadge`: correct label rendered, correct aria-label, null outcome handled without crash.
- [x] 7.20 Add rendering tests for `ResponseOutcomeSummary`: all fields present when non-null, no-history state for null, related ids section with `showRelated=true`, no standalone `executed` in any rendered string.
- [x] 7.21 Add accessibility assertions: badge aria-label is non-empty for every canonical mode/state, summary text is non-empty for null outcome.

### Validation

- [x] 7.22 Run the frontend test suite; confirm all new tests pass with zero failures.
- [x] 7.23 Confirm `ResponseOutcomeBadge` and `ResponseOutcomeSummary` are importable from shared paths that Phase 8 and Phase 9 changes can reference.
- [x] 7.24 Run `openspec validate add-response-outcome-frontend-components --strict` and confirm valid.
- [x] 7.25 Run `git diff --check` and confirm no whitespace errors.
