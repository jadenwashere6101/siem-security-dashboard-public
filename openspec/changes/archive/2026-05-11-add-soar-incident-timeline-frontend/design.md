# Design: SOAR Incident Timeline Frontend

## Proposed architecture
Add read-only timeline loading to the existing incident detail flow. The frontend should fetch timeline data only after an incident is selected, using the existing frontend service patterns for authenticated API calls.

Recommended service helper:

```javascript
export const loadIncidentTimeline = async (incidentId) => {
  const res = await fetch(buildSiemPath(`/incidents/${incidentId}/timeline`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, { timeline: [] });

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load incident timeline", ["error"])
    );
  }
  return data;
};
```

The helper should live in `frontend/src/services/incidentService.js` alongside `loadIncidents`, `loadIncidentDetail`, and `updateIncidentStatus`.

## UI placement
Add a "SOAR Timeline" section to the existing incident detail panel in `IncidentsPanel.js`. The section should sit near linked alerts and incident status controls, preferably after linked alerts and before existing status mutation controls.

This should remain part of incident detail, not a new global navigation item. The incident is the natural context for this timeline.

## State model
Add timeline-specific state without changing existing incident detail state:

```javascript
const [timeline, setTimeline] = useState([]);
const [timelineLoading, setTimelineLoading] = useState(false);
const [timelineError, setTimelineError] = useState("");
```

When `selectedIncidentId` changes:
- Load incident detail as it does today.
- Load incident timeline separately.
- Timeline failure should not clear or break incident detail.
- Closing or changing the selected incident should clear stale timeline state.

Timeline refresh can happen when incident detail refreshes after a status update, but it must remain a read-only fetch.

## Timeline entry rendering
Render each entry with:
- Timestamp formatted with the existing timestamp utility.
- Human-readable event type label derived from `event_type`.
- Source label from `source`.
- Summary text from `summary`.
- Optional title if provided.
- Safe metadata as a compact key/value list.

Example:

```text
14:25:00 UTC  Playbook step completed
playbook_execution  notify_slack completed in simulation mode
playbook_id: pb_notify | execution_id: 123 | simulated: true | executed: false
```

Use restrained styling consistent with the current operational UI. This should be a dense, scannable timeline, not a marketing-style card layout.

## Safe metadata filtering
The frontend should render only safe metadata keys. Recommended allowlist:
- `incident_id`
- `alert_id`
- `playbook_id`
- `execution_id`
- `step_index`
- `action`
- `status`
- `simulated`
- `executed`
- `adapter`
- `circuit_state`
- `approval_request_id`
- `required_role`
- `source_ip`
- `severity`

Do not display:
- Secrets.
- Credentials.
- Webhook URLs.
- Email server settings.
- Raw request payloads.
- Raw adapter params.
- Full raw JSON fallback unless it is already sanitized by the backend and explicitly marked safe.

If the backend sends additional metadata keys, ignore them by default until they are reviewed.

## Event type labels
Convert machine event types into concise labels:
- `incident_created` -> "Incident created"
- `alert_linked` -> "Alert linked"
- `alert_created` -> "Alert created"
- `playbook_execution_created` -> "Playbook execution created"
- `playbook_execution_started` -> "Playbook execution started"
- `playbook_execution_status_changed` -> "Playbook status changed"
- `playbook_step_started` -> "Playbook step started"
- `playbook_step_completed` -> "Playbook step completed"
- `playbook_step_failed` -> "Playbook step failed"
- `playbook_step_skipped` -> "Playbook step skipped"
- `playbook_adapter_simulated` -> "Simulated adapter step"
- `approval_requested` -> "Approval requested"
- `approval_approved` -> "Approval approved"
- `approval_denied` -> "Approval denied"
- `approval_expired` -> "Approval expired"
- `approval_resumed` -> "Approval resumed"
- `audit_event` -> "Audit event"

Unknown event types should render as a title-cased fallback without failing the component.

## Loading, error, and empty states
Loading:

```text
Loading timeline...
```

Error:

```text
Error loading timeline: {timelineError}
```

Include a retry button that calls the timeline fetch for the selected incident only.

Empty:

```text
No SOAR timeline events found for this incident.
```

These states should be scoped to the timeline section and should not replace the incident detail view.

## Simulation language
The timeline section should include a persistent visibility note:

```text
Timeline is read-only. SOAR playbook and adapter events are simulation-only unless explicitly marked otherwise by the backend.
```

Because real execution does not exist, entries should avoid language like "blocked", "sent", "posted", or "remediated" unless the summary already makes clear that the action was simulated. Prefer "simulated block_ip", "simulated notification", or backend-provided summaries that include simulation context.

## Controls
Do not add any timeline controls that mutate state. Specifically, do not add:
- Approve or deny buttons.
- Retry, resume, abandon, cancel, or run buttons.
- Queue worker controls.
- Adapter execution or test-connection controls.
- Circuit breaker reset, force-open, or half-open controls.
- Incident status controls beyond the existing incident status section.

Timeline may have a refresh/retry fetch button because it only reads data.

## Auth and roles
Use the same incident detail visibility path already in the app. Do not add new role logic beyond what the incident panel already receives.

If analysts can view incidents, they can view timeline data. Super-admins can view timeline data. Viewers should follow existing incident panel access rules.

## Accessibility and layout
- Use semantic headings for the timeline section.
- Timeline rows should be keyboard-readable and not depend on color alone.
- Event type and timestamp should be visible text.
- Long summaries and metadata values should wrap without overflowing.
- The component should handle many timeline entries with a scrollable section or compact layout if needed.

## Safety boundaries
- Visibility only.
- Must not mutate incidents, alerts, approvals, playbooks, queues, executions, integrations, circuit breakers, or metrics.
- Must not imply real remediation occurred.
- Must not expose secrets or raw params.
- No backend changes.
- No schema changes.
- No executor changes.
- No queue changes.
- No integration behavior changes.
- No ingest, detection, or correlation changes.

## Test strategy
Add focused frontend tests that verify:
- `loadIncidentTimeline` calls `GET /incidents/<id>/timeline` with credentials included.
- Timeline section shows loading state.
- Timeline section shows error state and retry behavior.
- Timeline section shows empty state.
- Timeline entries render timestamp, event type label, source, summary, and safe metadata.
- Unsafe metadata keys are not rendered.
- Unknown event types render safely.
- Timeline fetch failure does not remove incident detail.
- No approve, deny, retry, resume, run, cancel, queue, adapter, or circuit breaker controls are rendered by the timeline.
- Text does not imply real remediation for simulated events.

## Risks and stop conditions
- Stop if frontend requires backend contract changes.
- Stop if the timeline needs mutation controls to be useful.
- Stop if raw metadata contains secrets or unsafe params that cannot be filtered safely.
- Stop if UI copy implies real remediation occurred.
- Stop if adding timeline state breaks existing incident status update behavior.
