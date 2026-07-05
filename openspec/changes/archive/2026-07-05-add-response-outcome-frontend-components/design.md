# Design: Response Outcome Frontend Components

## Boundary

This child change is shared frontend utility and component work only. It does not modify any screens, backend routes, API contracts, canonical outcome writers, migrations, runtime behavior, or real execution policy.

Phase 8 screen-level changes (Alert Details, response log, manual action wording, SOAR Queue) depend on these components and must not be started until the components from this phase pass tests. Phase 9 screen-level changes (SOC Command Center, Source-IP Context, Blocklist Manager, Approvals Panel, Playbooks Panel, SOAR Metrics) also depend on these components.

## Parent Decision 7 UI Language Contract

All label text must match exactly:

| Condition | Label |
|---|---|
| `execution_state = observed`, no response selected | `Observed only` |
| `execution_mode = simulation` or `simulated = true` | `Simulated` |
| `execution_mode = tracking_only` or `tracking_recorded = true` | `Tracking only` |
| `execution_mode = real` and `external_executed = true` | `Real executed` |
| `execution_state = awaiting_approval` | `Awaiting approval` |
| `execution_state = blocked`, approval denied/expired | `Blocked by approval` |
| `execution_state = skipped` | `Skipped` |
| `execution_state = failed` | `Failed` |

Do not use standalone `executed`. Use phrases like `Simulated succeeded`, `Tracking-only recorded`, or `Real executed` for composite labels.

## Component Contracts

### `outcomeLabel(outcome)` utility function

Input: the `response_outcome` object from the API (or `null`).
Output: a string label from the table above.

- When `outcome` is `null` or has no `execution_mode`: return `"Observed only"`.
- Derive label from `execution_mode`, `execution_state`, `external_executed`, `tracking_recorded`, and `simulated` in the priority order shown in the parent design Decision 7.
- Must not derive labels from legacy fields (`response_action`, `response_status`, `executed`).

### `outcomeColor(outcome)` utility function

Input: the `response_outcome` object (or `null`).
Output: a semantic color token (not a hex code; use project color system).

Suggested mapping:
- `Observed only` → neutral/gray
- `Simulated` → blue
- `Tracking only` → yellow/amber
- `Real executed` → green
- `Awaiting approval` → orange
- `Blocked by approval` → red
- `Skipped` → gray
- `Failed` → red

### `ResponseOutcomeBadge` component

Props:
- `outcome`: the `response_outcome` object from the API (or `null`)

Renders a badge with:
- Label text from `outcomeLabel(outcome)`.
- Color from `outcomeColor(outcome)`.
- An accessible `aria-label` that includes both the label text and, when non-null, the `execution_mode` and `execution_state` values.
- Must not crash on any combination of valid canonical enum values.
- Must not crash when `outcome` is `null`.

### `ResponseOutcomeSummary` component

Props:
- `outcome`: the `response_outcome` object from the API (or `null`)
- `showRelated`: boolean (default false); when true, renders related ids section

Renders when `outcome` is non-null:
- Selected action (formatted, not raw enum key)
- Decision source
- Execution actor (when present)
- Execution booleans: `external_executed`, `tracking_recorded`, `simulated` as human-readable clauses, not raw booleans
- Outcome summary text
- Reason code explanation (when present)
- Related ids section (when `showRelated = true`): alert id, queue id, playbook execution id, approval request id, notification delivery id

Renders when `outcome` is `null`:
- A clear no-history state message, e.g. `"No response outcome recorded."`
- Must not render empty or blank.

### Inferred legacy outcome handling

When a screen receives a `response_outcome: null` but has a legacy `response_action` or `response_status` field, it MUST NOT infer canonical state from those fields in the component layer. The component renders the null state. If inferred compatibility is needed, it must be provided by the backend helper `resolve_*_outcome` and passed through the API as a proper `response_outcome` object.

## File Placement

Target the existing frontend utility and component directory structure. Likely candidates:

- `static/js/outcome_utils.js` or equivalent — label and color utilities
- `static/js/components/ResponseOutcomeBadge.js` or equivalent — badge component
- `static/js/components/ResponseOutcomeSummary.js` or equivalent — summary component
- Test files alongside or in a `__tests__` / `tests/` directory matching project conventions

During implementation, confirm the actual frontend file conventions from existing component files before creating new ones.

## Test Coverage Requirements

- `outcomeLabel` — all four `execution_mode` values, all nine `execution_state` values, all three boolean flags, null input, and every `reason_code`.
- `outcomeColor` — all canonical conditions and null input.
- `ResponseOutcomeBadge` — renders correct label, renders correct aria-label, handles null gracefully.
- `ResponseOutcomeSummary` — renders all fields when present, renders no-history state for null, renders related ids when `showRelated = true`, avoids standalone `executed` copy.
- Accessibility — badge aria-label is non-empty for every canonical mode/state, summary text is non-empty for null.
