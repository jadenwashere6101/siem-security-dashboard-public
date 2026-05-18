## Context

The app now has mature SOAR execution, operations, metrics, integration safety, and SOC Command Center surfaces. Playbook execution data exists, but operators still need a clearer visual explanation of what happened in a run: which step is current, which step failed, whether an approval pause occurred, whether retry/recovery metadata matters, and whether the run was simulation or guarded real mode.

The current frontend uses React functional components, section-based navigation in `App.js`, and SOAR detail views under `PlaybooksPanel`. This change should fit those patterns. `PlaybooksPanel` remains the primary full-detail execution view; SOC Command Center may reuse a compact summary only if it can do so without extra backend scope.

## Goals / Non-Goals

**Goals:**
- Add a polished read-only execution visualization for playbook runs.
- Render step-by-step timeline data from `steps_log` and adjacent execution metadata.
- Show status states: pending, running, success, failed, skipped, awaiting approval, and unknown/malformed.
- Surface retries, timestamps, durations, safe failure messages, approval pauses, recovery/lease markers, and simulation/real labels when present.
- Integrate into `PlaybooksPanel` execution detail without removing existing fields or behavior.
- Support malformed, empty, stringified, or partial `steps_log` values with safe empty/error states.
- Keep the component compact, dark-theme consistent, accessible, and readable on narrow screens.

**Non-Goals:**
- No backend execution changes.
- No schema/migration changes.
- No new playbook execution, retry, dismiss, approval, or integration mutation controls.
- No real integration triggering.
- No global `App.js` rewrite.
- No replacement of SOAR Operations, SOAR Metrics, SOC Command Center, or existing PlaybooksPanel workflows.

## Decisions

### Decision 1: Build a reusable read-only timeline component

Create `frontend/src/components/PlaybookExecutionTimeline.js` as the main visualization component. It should accept an execution object and optional compact/full display mode.

Rationale: `PlaybooksPanel` needs a full view, and SOC Command Center may need a compact summary. A reusable component avoids duplicating step parsing and status rendering.

Alternatives considered:
- Embed all visualization directly in `PlaybooksPanel`. This is faster initially but makes SOC reuse and isolated tests harder.
- Add a third-party graph/flow library. The desired view is compact and bounded; a lightweight custom node/timeline layout should be enough and avoids dependency risk.

### Decision 2: Normalize `steps_log` defensively in the frontend

The component should normalize `steps_log` from existing execution data. Supported inputs should include arrays, JSON strings, missing values, partial step records, and unexpected objects. Malformed data should render a safe unavailable state rather than crash.

Rationale: Execution history can evolve across backend slices, and the visualization should tolerate older or sparse rows.

### Decision 3: Visual flow plus chronological timeline

The full view should contain two coordinated regions:
- Flow strip: node-style representation of ordered steps with status, current/terminal highlighting, approval pause markers, and recovery/lease markers.
- Timeline list: chronological step details with timestamps, durations, retries, failure class/message, and safe metadata.

Rationale: The flow strip gives quick shape; the timeline gives audit-friendly detail.

### Decision 4: Read-only clarity over controls

This spec adds no new execution controls. Existing retry/resume/abandon behavior in `PlaybooksPanel`, if already present, must remain unchanged and outside the new visualization component.

Rationale: The goal is explainability, not changing the execution state machine or safety posture.

### Decision 5: Use safe metadata only

The timeline should render step names, action names, adapter names, status, failure class/code, short sanitized error message, timestamps, durations, retry count, approval id/status, delivery attempt status, and recovery/lease flags when present. It must not render raw payloads, provider responses, auth headers, tokens, SMTP secrets, webhook URLs, or full request bodies.

Rationale: Execution logs may contain sensitive integration context. Visualization should be operationally useful without leaking secrets.

## Data Sources and Expected Reuse

Primary data:
- `getPlaybookExecution(executionId)` from `frontend/src/services/playbookService.js`.
- Existing execution objects from `listPlaybookExecutions()` where details are already available.
- Execution fields expected to be useful: `id`, `playbook_id`, `status`, `mode`, `created_at`, `started_at`, `completed_at`, `current_step`, `steps_log`, `error`, `failure_class`, `retry_count`, `lease_owner`, `lease_expires_at`, `recovery_count`, `last_recovered_at`, `dead_letter_id`, `approval_request_id`, and related step metadata if present.

Secondary data, only if already available in detail responses or existing read services:
- Approval status/id/action for approval-gated steps.
- Notification delivery attempt status/provider/mode for notification steps.
- Dead-letter failure class/status/retryability for failed steps.

No new backend endpoint should be added unless a tiny read-only field gap blocks the UI from safely identifying existing execution steps.

## UI Shape

Full view in `PlaybooksPanel` execution detail:
- Header: execution id, playbook id/name, overall status badge, simulation/real badge, started/completed or last-updated timestamp.
- Flow visualization: horizontally wrapping step nodes with connecting lines, accessible labels, status icons/badges, current step highlight, terminal highlight, approval pause marker, and recovery/lease marker.
- Timeline list: ordered step rows with step label, action/adapter, status, timestamps/duration, retry count, failure class/code, safe message, and linked context labels.
- Footer/side strip: summary counts for succeeded, failed, skipped, pending/running, approval-gated, and retry attempts.

Compact view for SOC Command Center, if implemented:
- Small status strip or mini timeline for the selected/recent execution.
- Limit to key status, current/failed step, and simulation/real label.
- No new fetch fan-out unless existing Command Center data already includes enough execution detail or a bounded detail fetch is justified.

Visual style:
- Consistent dark theme, compact cards, badges, and timeline rows.
- Stable node dimensions with wrapping for narrow widths.
- No decorative landing-page elements.
- Accessible labels for status and step order.

## Risks / Trade-offs

- `steps_log` shape may vary across execution versions -> normalize defensively and test arrays, JSON strings, malformed values, and missing fields.
- Flow diagrams can become too wide -> use wrapping node layout and compact mode rather than a large canvas.
- Raw errors may contain secrets -> sanitize and truncate displayed messages.
- SOC Command Center reuse may require extra data -> keep it optional and skip if it would cause backend or fan-out risk.
- Existing PlaybooksPanel tests may be brittle -> integrate behind execution detail rendering and add focused tests.

## Migration Plan

1. Audit `PlaybooksPanel` execution detail and current playbook execution service shapes.
2. Create `PlaybookExecutionTimeline.js` with pure normalization/status helpers and full/compact rendering modes.
3. Integrate the full timeline into `PlaybooksPanel` execution detail.
4. Optionally reuse compact timeline in SOC Command Center only if existing data supports it safely.
5. Add focused tests for status rendering, malformed data, failure messages, approval pause, recovery/lease markers, simulation/real labels, and panel integration.
6. Run frontend focused tests and build.
7. Rollback is removing the new component and panel wiring; no backend or schema rollback is expected.
