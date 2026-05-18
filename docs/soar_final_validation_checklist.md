# SOAR Final Validation Checklist

Last updated: 2026-05-18

Use this checklist before demos, portfolio review, or final handoff.

## Frontend Validation

Run from `frontend/`:

```bash
CI=true npm test -- --runInBand App
CI=true npm test -- --runInBand SocCommandCenter
CI=true npm test -- --runInBand PlaybooksPanel
npm run build
```

Optional focused UI checks:

```bash
CI=true npm test -- --runInBand SoarMetricsDashboard
CI=true npm test -- --runInBand PlaybookExecutionTimeline
CI=true npm test -- --runInBand DeadLettersPanel
```

## Backend Validation

Run from the repo root:

```bash
python3 -m pytest tests/test_playbook_execution_leases.py \
  tests/test_playbook_step_executor.py \
  tests/test_dead_letter_store.py \
  tests/test_playbook_metrics_routes.py -v
```

## Demo Environment Verification

- SOC Command Center loads without a full-page crash.
- SOAR Playbooks shows execution history and timeline detail when data exists.
- SOAR Operations loads dead-letter state.
- SOAR Metrics loads worker, queue, execution, and notification health.
- Integration status clearly labels simulation-safe or guarded real-mode state.
- Viewer/auditor roles do not see analyst-only or super-admin-only controls.

## Deployment Verification References

- Frontend build command: `cd frontend && npm run build`.
- Frontend artifact helper: `deploy.sh` after operator review.
- Backend/VM deploy reference: `scripts/deploy_backend_vm.sh` plus
  [Schema Migration Workflow](schema_migration_workflow.md).
- Worker reference:
  [SOAR Playbook Worker Daemon Runbook](soar_playbook_worker_daemon_runbook.md).
- Integration smoke tests:
  [Slack](soar_slack_staging_smoke_test_runbook.md),
  [Teams](soar_teams_staging_smoke_test_runbook.md),
  [Email](soar_email_staging_smoke_test_runbook.md), and
  [Webhook](soar_webhook_staging_smoke_test_runbook.md).

Do not perform VM/runtime deployment actions unless explicitly requested.

## Secret and Redaction Review

- No screenshots include secrets, webhook URLs, SMTP credentials, auth headers,
  private IPs that should not be shared, or raw sensitive payloads.
- Docs use credential env var names only, never credential values.
- Logs/audit evidence shown in a demo includes safe metadata only.

## Git Cleanliness

Run from the repo root:

```bash
git diff --check
git status --short
```

Expected final state for a committed release candidate is no unexpected local
changes. During implementation, expected local changes should be limited to the
current approved OpenSpec scope.

