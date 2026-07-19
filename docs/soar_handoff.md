# SOAR Handoff: Current Architecture and Production/Demo State

Last updated: 2026-05-18

This is the current onboarding handoff for future contributors. It summarizes
the completed SIEM/SOAR platform state, the operational workflows that matter,
and the boundaries that should not be crossed without a new approved spec.

For demo scripts and interview framing, see [SOAR Docs Index](soar_docs_index.md).

## Current Platform Summary

The project is now a mature simulation-first SIEM/SOAR console:

- SIEM ingest, detection, correlation, alerts, incidents, reports, and RBAC.
- SOC Command Center for high-level operational pressure and safety state.
- SOAR Playbooks with read-only execution detail and visual execution timeline.
- SOAR Operations for dead letters, retryability, and safe recovery workflows.
- SOAR Metrics for worker, queue, execution, dead-letter, and notification health.
- Daemonized SOAR playbook worker with lease ownership and stale recovery.
- Approval gates for human-in-the-loop pauses.
- Guarded integration adapters for Slack, Teams, email, and generic webhooks.
- Firewall remains simulation/dry-run only.
- Integration audit logging, redaction, rate limiting, and notification dedup.
- Productization docs for demos, reset guidance, security boundaries, and final validation.

## Current Architecture

```text
Telemetry ingestion
  -> detection/correlation
  -> alerts/incidents
  -> SOAR playbook queue/executions
  -> daemonized worker with leases
  -> guarded adapter registry
  -> audit, metrics, notification delivery, approvals, dead letters
  -> SOC Command Center / Playbooks / SOAR Operations / SOAR Metrics
```

Important boundary: SOAR starts after alerts/incidents exist. Ingest,
detection, and correlation are not the place to add response execution behavior.

## Backend and SOAR Components

- `siem_backend.py` creates the Flask app and keeps compatibility for tests and deployment imports.
- `routes/*` expose alert, incident, playbook, approval, dead-letter, metrics,
  notification delivery, integration, and admin surfaces.
- `core/*` owns stores and shared safety helpers: approvals, dead letters,
  notification delivery, playbook storage, protected targets, audit helpers,
  DB access, and auth helpers.
- `engines/playbook_step_executor.py` executes playbook steps through safe
  simulation/default behavior and guarded adapter calls.
- `scripts/soar_playbook_worker_daemon.py` is the daemon entrypoint for
  lease-safe playbook execution.
- `integrations/*` contains adapter implementations, registry behavior,
  circuit breaker logic, real-mode guard helpers, rate limiting, and redacted
  integration audit behavior.

## Frontend Architecture and Deployment

The frontend is a Create React App application under `frontend/`.

- Development uses the CRA dev server only for local development.
- Production/demo deployment uses `npm run build`.
- CRA outputs static files into `frontend/build/`.
- Gunicorn serves the Flask WSGI app, including built frontend assets, in production.
- nginx sits in front of Gunicorn as the reverse proxy in the deployed VM workflow.
- Production is not a localhost dev-server workflow.
- The frontend artifact deployment model is build plus sync of `frontend/build/`
  to the configured remote static path.

Operational references:

- Frontend build:

  ```bash
  cd frontend
  npm run build
  ```

- Frontend artifact helper: `deploy.sh`. It builds CRA output and rsyncs build
  artifacts after operator review.
- Backend/VM deployment reference: `scripts/deploy_backend_vm.sh` plus
  [Schema Migration Workflow](schema_migration_workflow.md).
- Production backend runtime reference:
  [Production WSGI Runtime](production_wsgi_runtime.md).
- Worker operations reference:
  [SOAR Playbook Worker Daemon Runbook](soar_playbook_worker_daemon_runbook.md).

Do not run VM deployment or service restart commands as part of ordinary docs or
frontend polish work.

## Completed Roadmap Items

The following formerly planned items are complete:

- Daemonized SOAR playbook worker.
- Lease-safe execution ownership.
- Stale running execution recovery.
- Durable playbook execution history and step logs.
- Human approval gates.
- Dead-letter creation, duplicate safety, retryability classification, and UI.
- SOAR Operations UI.
- SOAR Metrics dashboard.
- SOC Command Center.
- Playbook execution visualization/timeline.
- Guarded Slack, Teams, email, and webhook real-mode paths.
- Firewall simulation/dry-run boundary.
- Integration status APIs and safety logging.
- Redacted integration audit logging.
- Adapter rate limiting/flood protection.
- Notification delivery deduplication/idempotency guard.
- Email and webhook staging smoke-test docs.
- Slack and Teams staging smoke-test docs.
- Final demo, reset, architecture, security-boundary, interview, and validation docs.

Do not re-add these as future roadmap items.

## Current Safe Production State

- Simulation-first by default.
- Real Slack/Teams/email/webhook execution is possible only when all real-mode
  guards pass.
- Real-mode guard model:
  - `INTEGRATION_MODE=real`
  - approved `SOAR_ENV`, normally staging for smoke tests
  - `SOAR_REAL_<ADAPTER>_ENABLED=true`
  - required credential env vars present and non-empty
- Missing guards fail closed to simulation or blocked/skipped safe results.
- Firewall remains dry-run only; no real firewall execution path exists.
- Approval-paused playbooks remain gated by human review.
- There is no autonomous destructive remediation path.
- Audit/log output must never expose credential values, webhook URLs, auth
  headers, SMTP passwords, or raw payloads.
- Rate limiting and idempotency guards protect notification delivery from floods
  and duplicate sends.

## Operational Workflows

### Demo / Interview

Use:

- [SOAR Demo Walkthrough](soar_demo_walkthrough.md)
- [SOAR Demo Reset Guide](soar_demo_reset_guide.md)
- [SOAR Interview Talking Points](soar_interview_talking_points.md)

Recommended demo order:

1. SOC Command Center.
2. One incident or playbook execution.
3. Playbook execution timeline.
4. SOAR Operations dead letters/retryability.
5. SOAR Metrics worker and queue health.
6. Integration safety status and real-mode guard explanation.

### Worker Operations

Use [SOAR Playbook Worker Daemon Runbook](soar_playbook_worker_daemon_runbook.md).

Key points:

- Start with one worker unless explicitly validating multi-worker behavior.
- Leases prevent two workers from completing the same execution.
- Stale recovery is explicit and should not move `awaiting_approval` executions.
- Worker logs and metrics must not contain secrets or raw payloads.

### Integration Smoke Tests

Use adapter-specific runbooks only:

- [Slack staging smoke test](soar_slack_staging_smoke_test_runbook.md)
- [Teams staging smoke test](soar_teams_staging_smoke_test_runbook.md)
- [Email staging smoke test](soar_email_staging_smoke_test_runbook.md)
- [Webhook staging smoke test](soar_webhook_staging_smoke_test_runbook.md)

Do not combine smoke tests. Do not enable unrelated adapters during a smoke test.

### Validation

Use [SOAR Final Validation Checklist](soar_final_validation_checklist.md).

Current focused checks:

```bash
cd frontend
CI=true npm test -- --runInBand App
CI=true npm test -- --runInBand SocCommandCenter
CI=true npm test -- --runInBand PlaybooksPanel
npm run build
```

```bash
python3 -m pytest tests/test_playbook_execution_leases.py \
  tests/test_playbook_step_executor.py \
  tests/test_dead_letter_store.py \
  tests/test_playbook_metrics_routes.py -v
```

## Frontend Surfaces

- **Dashboard:** SIEM alert/incident entry point.
- **SOC Command Center:** high-level SOC pressure, activity feed, attention
  panel, incident workspace, worker health, notification health, and integration safety.
- **SOAR Playbooks:** playbook definitions, execution list, execution detail,
  and read-only execution timeline.
- **SOAR Operations:** dead-letter operations and retry/dismiss visibility.
- **SOAR Metrics:** execution, worker, queue, stale recovery, dead-letter, and
  notification metrics.
- **SOAR Integrations:** adapter readiness, guard decisions, and circuit/safety state.

Viewer/auditor roles should not see analyst-only or super-admin-only operational controls.

## Intentionally Deferred / Future Work

Keep this list narrow. These are realistic future improvements, not stale
roadmap items:

- True heartbeat persistence for richer daemon liveness reporting.
- Persistent circuit-breaker state across worker/process restarts.
- Mobile and narrow-screen optimization beyond current readable layouts.
- Advanced analytics and trend modeling over SOAR outcomes.
- Optional future firewall OpenSpec for any live firewall path.
- Optional scheduler/playbook cron layer for time-based playbooks.
- Richer real-mode operational rollout with staged enablement and evidence gates.

## Do Not Regress

- Do not add schema/migration changes from documentation-only work.
- Do not alter backend execution semantics while updating docs.
- Do not add new mutation controls to visualization-only UI.
- Do not trigger real integrations during tests or demos.
- Do not convert firewall dry-run into live execution without a new approved spec.
- Do not commit secrets, `.env` values, webhook URLs, auth headers, SMTP
  passwords, or raw sensitive payloads.
