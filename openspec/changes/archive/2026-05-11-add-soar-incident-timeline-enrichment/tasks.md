# Tasks: SOAR Incident Timeline Enrichment

## Implementation steps
- [ ] Inspect current incident detail response and frontend incident detail rendering.
- [ ] Choose whether to extend `GET /incidents/<id>` or add `GET /incidents/<id>/timeline`.
- [ ] Add a read-only timeline aggregation helper using existing incident, alert, playbook execution, approval, and audit data.
- [ ] Include incident lifecycle events when reliable timestamps exist.
- [ ] Include linked alert events.
- [ ] Include playbook executions linked by `incident_id`.
- [ ] Include playbook executions linked through incident alert IDs when `incident_id` is absent.
- [ ] Parse `steps_log` defensively into timeline entries.
- [ ] Include approval requests and approval request events linked to playbook executions.
- [ ] Include audit events only when safely and structurally linked.
- [ ] Normalize event shape with timestamp, event type, source, source ID, summary, and metadata.
- [ ] Sort entries chronologically with deterministic tie-breaking.
- [ ] Add backend tests proving read-only behavior.
- [ ] Add frontend timeline visibility only if the backend contract is stable and the UI remains read-only.
- [ ] Confirm no schema, executor, queue, integration, ingest, detection, or correlation changes were made unless an additive schema change is absolutely necessary and explicitly justified.

## Exact backend test requirements
- [ ] Test unauthenticated timeline access is rejected.
- [ ] Test authorized analyst or super-admin can read the incident timeline.
- [ ] Test missing incident returns existing not-found behavior.
- [ ] Test linked alerts appear in the timeline.
- [ ] Test playbook executions linked by `incident_id` appear in the timeline.
- [ ] Test playbook executions linked by incident alert IDs appear when safe.
- [ ] Test `steps_log` entries produce timeline events with step index, action, status, and timestamp.
- [ ] Test adapter-backed simulated step output appears as visibility metadata only.
- [ ] Test approval requests linked to playbook executions appear.
- [ ] Test approval request events appear in chronological order.
- [ ] Test safely linked audit events appear.
- [ ] Test unsafe/unstructured audit events are omitted.
- [ ] Test timeline entries are sorted chronologically with deterministic tie-breaking.
- [ ] Test malformed or unexpected `steps_log` entries do not fail the whole response.
- [ ] Test GET timeline does not mutate incidents.
- [ ] Test GET timeline does not mutate alerts.
- [ ] Test GET timeline does not mutate approvals or approval events.
- [ ] Test GET timeline does not mutate playbook executions or steps logs.
- [ ] Test GET timeline does not enqueue SOAR queue rows or mutate queue state.
- [ ] Test GET timeline does not call playbook executor, queue worker, integration adapters, approval expiration, network, or subprocess paths.

## Optional frontend test requirements
- [ ] Test incident detail renders a read-only timeline section when timeline data is present.
- [ ] Test timeline entries render timestamp, event type, source, and summary.
- [ ] Test empty timeline state renders without error.
- [ ] Test loading and error states remain usable.
- [ ] Test no approve, deny, retry, resume, queue-run, adapter, or circuit breaker controls are added to the timeline.
- [ ] Test copy does not imply real remediation occurred.

## Verification commands
Run:

```bash
python3 -m py_compile siem_backend.py helpers/*.py core/*.py engines/*.py routes/*.py integrations/**/*.py scripts/*.py
python3 -m pytest tests/test_incident_routes.py -v
python3 -m pytest tests/test_playbook_routes.py tests/test_playbook_step_executor.py tests/test_approval_routes.py -v
python3 -m pytest tests/test_integration_adapters.py tests/test_integration_routes.py tests/test_metrics_routes.py -v
python3 -m pytest tests/test_failed_login_detection.py tests/test_password_spraying_detection.py tests/test_correlated_activity.py tests/test_targeted_correlation.py tests/test_ingest_api_contracts.py tests/test_alert_mutation_api_contracts.py -v
npm test -- --watchAll=false IncidentsPanel.test.js
npm run build
git status --short
```

Skip frontend commands if the implementation is backend-only, or adjust filenames to match the existing frontend test layout.

## Stop and rollback conditions
- Stop if implementation requires real execution.
- Stop if implementation adds mutation controls.
- Stop if implementation changes playbook executor behavior.
- Stop if implementation changes SOAR queue behavior.
- Stop if implementation changes integration behavior.
- Stop if implementation changes ingest, detection, or correlation internals.
- Stop if implementation needs non-additive schema changes.
- Stop if implementation adds daemon, systemd, Celery, APScheduler, or background worker behavior.
- Roll back if timeline reads cannot remain read-only and visibility-only.
