# SOAR Demo Reset Guide

Last updated: 2026-05-18

This guide describes safe reset and cleanup practices for demos. It does not
introduce destructive cleanup scripts or database wiping instructions.

## Reset Principles

- Prefer repeatable simulation data and existing safe workflows.
- Do not drop databases, truncate SOAR tables, reset migrations, or clear audit
  evidence for a demo.
- Do not modify VM runtime state unless a deployment/reset task was explicitly
  requested and approved.
- Do not enable real integrations to make a demo look more active.
- Preserve evidence before cleanup if the session is being used for validation.

## Pre-Reset Checklist

1. Capture current state:

   ```bash
   git status --short
   ```

2. Capture screenshots if the current state is useful evidence.
3. Confirm no real-mode smoke test is in progress.
4. Confirm no operator is relying on the same database/session.
5. Review visible data for secrets before sharing screenshots.

## Safe Local UI Reset

Use these steps when the frontend looks stale or the browser session is noisy:

1. Refresh the browser.
2. Log out and back in with the demo role if needed.
3. Restart only the local frontend dev server if necessary:

   ```bash
   cd frontend
   npm start
   ```

4. Avoid browser autofill or pasted credentials in screenshots.

## Safe Demo Data Guidance

- Use existing seeded or simulation-generated demo data when available.
- If a scenario needs a known incident/playbook state, create it through the
  existing application or existing approved seed workflow for the environment.
- Do not add a cleanup script that deletes incidents, executions, approvals,
  notification attempts, dead letters, or audit records.
- Do not manually edit production-like data for a visual demo.

## Worker and Backend Reset Boundaries

- For local validation, restart the backend only through the normal local
  development command used by the repo.
- For worker behavior, use
  [SOAR Playbook Worker Daemon Runbook](soar_playbook_worker_daemon_runbook.md)
  as the operational reference.
- VM service restarts and deployment resets are operator actions. They are not
  part of this local productization polish pass.

## Post-Demo Cleanup

1. Stop local development servers if they are no longer needed.
2. Confirm no unexpected changes were created:

   ```bash
   git status --short
   ```

3. Remove local screenshots that contain private data.
4. Leave integration env vars in their safe baseline state.
5. Record any follow-up issues separately instead of editing runtime data.

