# Tasks: SOAR Incident Timeline Frontend

## Implementation steps
- [ ] Inspect existing `incidentService.js` patterns.
- [ ] Add `loadIncidentTimeline(incidentId)` service helper for `GET /incidents/<id>/timeline`.
- [ ] Inspect current `IncidentsPanel.js` detail state and rendering.
- [ ] Add timeline state scoped to the selected incident.
- [ ] Fetch timeline data when an incident is selected.
- [ ] Clear stale timeline data when selected incident changes or closes.
- [ ] Render a read-only "SOAR Timeline" section in incident detail.
- [ ] Show timestamp, event type label, source, summary, and safe metadata.
- [ ] Add loading, error, retry, and empty states.
- [ ] Add safe metadata allowlist and ignore unknown unsafe keys by default.
- [ ] Add simulation/read-only notice.
- [ ] Ensure timeline errors do not break incident detail rendering.
- [ ] Ensure existing incident status update behavior is unchanged.
- [ ] Add focused frontend tests.
- [ ] Confirm no backend, schema, executor, queue, integration, ingest, detection, or correlation files changed.

## Exact frontend test requirements
- [ ] Test `loadIncidentTimeline` calls `/incidents/<id>/timeline` with `credentials: "include"`.
- [ ] Test service helper throws a useful error on non-OK response.
- [ ] Test selecting an incident loads timeline data.
- [ ] Test timeline loading state renders.
- [ ] Test timeline error state renders.
- [ ] Test timeline retry button refetches data.
- [ ] Test empty timeline state renders.
- [ ] Test timeline entries render formatted timestamp, event type label, source, summary, and title when present.
- [ ] Test safe metadata keys render.
- [ ] Test unsafe metadata keys such as secrets, webhook URLs, credentials, raw params, and raw payloads do not render.
- [ ] Test unknown event types render without crashing.
- [ ] Test timeline fetch failure does not clear selected incident detail.
- [ ] Test no approve/deny controls are added.
- [ ] Test no retry/resume/run/cancel controls are added.
- [ ] Test no queue worker controls are added.
- [ ] Test no adapter or circuit breaker controls are added.
- [ ] Test timeline copy does not imply real remediation occurred.

## Verification commands
Run:

```bash
npm test -- --watchAll=false IncidentsPanel.test.js
npm run build
git status --short
```

If service tests live in a separate file, include that focused test file as well.

Backend verification is not required for this frontend-only change, but run the existing incident route tests if any shared service contract is questioned:

```bash
python3 -m pytest tests/test_incident_routes.py -v
```

## Stop and rollback conditions
- Stop if implementation requires backend changes.
- Stop if implementation requires schema changes.
- Stop if implementation adds mutation controls.
- Stop if implementation adds approve, deny, resume, run, retry, cancel, queue, adapter, or circuit breaker controls.
- Stop if implementation changes executor behavior.
- Stop if implementation changes SOAR queue behavior.
- Stop if implementation changes integration behavior.
- Stop if implementation changes ingest, detection, or correlation internals.
- Stop if timeline rendering exposes secrets, credentials, webhook URLs, raw params, or unsafe raw payloads.
- Roll back if the timeline cannot remain visibility-only.
