# SOAR Architecture Summary

Last updated: 2026-07-05

This document is the portfolio-ready overview of the SIEM/SOAR platform.

## System Shape

The platform separates detection from response:

```text
Telemetry ingestion -> detection/correlation -> alerts/incidents
  -> SOAR queue -> playbook worker -> guarded integrations
  -> audit, metrics, dead letters, and operations UI
```

The SOAR layer starts after alerts and incidents exist. It does not rewrite the
ingest, detection, or correlation pipeline.

## Major Components

- **Frontend console:** Dashboard, SOC Command Center, SOAR Playbooks, execution
  timeline, SOAR Operations, SOAR Metrics, integrations, approvals, incidents,
  and analyst workflows.
- **Backend API:** Flask routes expose alerts, incidents, playbooks,
  executions, approvals, dead letters, metrics, notification delivery attempts,
  and integration status.
- **Execution engine:** Claims queued playbook work, records step progress,
  handles approvals, records failures, and preserves execution metadata.
- **Worker daemon:** Runs playbook execution outside the request path with
  leases, stale recovery, bounded batch sizes, and metrics visibility.
- **Dead-letter store:** Captures failed executions with retryability
  classification and duplicate-safe handling.
- **Notification delivery layer:** Records delivery attempts, rate limits
  outbound pressure, deduplicates idempotent sends, and classifies failures.
- **Integration adapters:** Default to simulation. Email and webhook real-mode
  paths are guarded; firewall remains simulation/dry-run only.
- **Audit and redaction:** Integration attempts log safe metadata only, never
  secrets, webhook URLs, SMTP passwords, auth headers, or raw payloads.

## Worker Orchestration

The worker is designed for operational safety:

- Claims work with lease ownership.
- Respects bounded batch and poll settings.
- Recovers stale running executions through explicit recovery logic.
- Avoids recovering approval-paused work as stale execution.
- Emits metrics that the UI can show in SOAR Metrics and SOC Command Center.
- Routes failures into dead letters when execution cannot proceed safely.

## Playbook Execution Traceability

Executions keep status, timestamps, step logs, failure classes, retry metadata,
approval state, and recovery context where available. The Playbooks UI renders
this as a read-only execution timeline so reviewers can see exactly where an
automation succeeded, paused, failed, retried, or recovered.

## Canonical Response Outcomes

SOAR response outcome semantics are defined by the canonical decision/event
model in [SOAR Response Outcome Model](soar_response_outcome_model.md).

The model uses:

- `soar_response_decisions`: one selected response and the reason it was chosen.
- `soar_response_outcome_events`: append-only lifecycle events for that selected
  response.
- `soar_correlation_id`: a safe lifecycle id propagated across alerts, queue
  rows, playbook executions, approvals, notification delivery attempts, response
  logs, incidents, and relevant audit rows.

The canonical API/read model exposes `response_outcome` with selected action,
decision source, execution actor, mode/state, booleans, summary, reason code,
related ids, and timestamps. Latest outcome is derived from append-only events,
not from a rewritten status field.

Dashboard wording is canonicalized around `Observed only`, `Simulated`,
`Tracking only`, `Real executed`, `Failed`, `Blocked by approval`,
`Awaiting approval`, and `Skipped`. Standalone `Executed` is not a canonical
label because it hides the difference between simulation, tracking-only state,
and guarded real execution.

## Integration Safety Model

Real outbound execution requires all guards to pass:

- `INTEGRATION_MODE=real`
- `SOAR_ENV` set to staging or another approved safe value documented by the
  relevant runbook/spec
- `SOAR_REAL_<ADAPTER>_ENABLED=true`
- Required adapter credentials present and non-empty

Missing or invalid guards fail closed to simulation or a blocked/skipped result.
Credential values must never be logged or shown in UI output.

## Mac vs VM Workflow

- **Mac/local workflow:** edit code, run unit tests, run frontend build, and
  demo simulation-safe behavior.
- **VM/deployment workflow:** run only through approved deployment/runbook
  steps. VM service changes are operator actions, not part of docs or frontend
  polish tasks.
- **Smoke-test workflow:** use adapter-specific staging runbooks for Slack,
  Teams, email, and webhook. Do not combine smoke tests.

## Deployment References

- Frontend build command:

  ```bash
  cd frontend
  npm run build
  ```

- Frontend artifact helper: `deploy.sh`. This script includes git and rsync
  steps and should be reviewed before operator use.
- Backend/VM deployment reference: `scripts/deploy_backend_vm.sh` and
  [Schema Migration Workflow](schema_migration_workflow.md). Run only as an
  approved deployment action.
- Worker operations reference:
  [SOAR Playbook Worker Daemon Runbook](soar_playbook_worker_daemon_runbook.md).
- Response outcome rollout and rollback reference:
  [SOAR Response Outcome Rollout and Rollback](soar_response_outcome_rollout.md).
