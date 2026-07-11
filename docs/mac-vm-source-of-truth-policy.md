# Mac and VM Source-of-Truth Policy

## Non-Negotiable Rule

**Mac = development/source of truth. VM = deployment target only.**

Never write source code on the VM. Never use `git merge origin/main` or `git pull` to synchronize the VM — merging is never used to sync the VM, clean or dirty. After a clean-tree and approved-commit preflight (see VM Clean-Tree Gate), synchronize only with:

```bash
git fetch origin
git reset --hard origin/main
```

The only exception:

- **VM emergency hotfix** — requires explicit user authorization, a backup, and a documented rollback, and must be copied back into the Mac source of truth immediately and reconciled through normal version control.

## Authoritative Locations

Mac repository:

```text
/Users/jadengomez/Projects/siem-security-dashboard-public
```

VM repository/runtime:

```text
jaden@4.204.25.149:/home/jaden/siem-security-dashboard
```

The old `/Users/jadengomez/Desktop/siem-security-dashboard-public` checkout is obsolete and absent. Agents must not use or recreate it.

## Ownership

**Ownership test:** durable source, specification, migration, backend, frontend, test, and documentation changes belong to Mac AI. Live configuration, installed services, deployment, database/runtime cleanup, and production smoke tests belong to VM AI.

### Mac AI

Use the Mac repository for:

- audits and OpenSpec artifacts;
- frontend/backend source and deployment templates;
- migrations, schema snapshot, seed files, scripts, tests, and documentation;
- frontend production builds;
- commits and pushes, only when explicitly authorized.

### VM AI

Use the VM only for explicitly authorized:

- clean-tree preflight, `git fetch`, and syncing to the approved remote commit via `git reset --hard`;
- migration dry-runs/applies and approved backfills;
- runtime `.env`/secret configuration without exposing values;
- systemd install/reload/restart/status and journal review;
- database/runtime queue, approval, and dead-letter operations;
- backend health checks, frontend artifact deployment, and live smoke tests.

The VM AI must not invent or implement durable fixes. Any required source, migration, unit-template, wrapper, API, or UI change is handed back to the Mac AI.

## Spec-to-Deployment Workflow

1. Audit existing code, tests, active changes, legacy paths, and affected analyst/runtime workflows.
2. Create the minimum safe OpenSpec structure. Label each change and implementation phase **Mac AI** or **VM AI**.
3. Mac AI implements only the selected phase and runs focused plus affected regression checks.
4. The user explicitly authorizes any commit and push.
5. VM AI deploys only that approved commit after clean-tree verification.
6. VM AI captures sanitized before/after evidence and performs only the specified runtime/data remediation.
7. Work is complete only when all required source verification and production verification are complete.

Specs/docs/tests alone do not require VM synchronization. Source changes do not reach the VM until committed, pushed, and explicitly deployed.

## VM Clean-Tree Gate

Before every VM sync:

```bash
cd /home/jaden/siem-security-dashboard
git status --short
```

If any output appears, stop and report the exact files. Do not stash, reset, discard, overwrite, merge, or work around a dirty VM without explicit user direction.

Never create merge commits or reconciliation commits on the VM, and never use `git merge origin/main` or a bare `git pull`. If clean and deployment is explicitly approved, sync only the approved commit:

```bash
git fetch origin
git reset --hard origin/main
```

Record the approved commit SHA before deployment and verify VM HEAD contains that SHA after sync.

Before any deployment, all of the following must hold, or stop and do not merge/rebase/reset/migrate/build/restart services:

- `git status --short` is clean
- `git fetch origin` succeeded
- VM HEAD contains the explicitly approved commit
- VM branch is not behind or diverged from `origin/main`

## Deployment Decision Matrix

### Spec, docs, or tests only

- No VM sync.
- No service restart.
- No frontend deployment.

### Frontend source only

On the Mac:

```bash
cd /Users/jadengomez/Projects/siem-security-dashboard-public/frontend
npm test -- --runInBand --watchAll=false [AFFECTED_TESTS]
npm run build
```

After commit/push authorization, deploy only the built artifact when explicitly requested:

```bash
rsync -avz --delete \
  -e "ssh -i ~/.ssh/jadeng15.pem" \
  /Users/jadengomez/Projects/siem-security-dashboard-public/frontend/build/ \
  jaden@4.204.25.149:/home/jaden/siem-security-dashboard/frontend/build/
```

Frontend deployment does not require a backend restart unless backend code/config also changed.

### Backend/runtime source without migrations

After the VM clean-tree sync, use the repository deployment/runbook instructions. Restart only affected services and verify:

```bash
curl -fsS http://127.0.0.1:5051/health
```

Inspect relevant service status/journals and effective configuration without printing secrets.

### Migrations or schema changes

On the Mac, migration tests and schema snapshot validation must pass first. On the clean, synced VM:

```bash
bash scripts/deploy_backend_vm.sh --dry-run-migrations
bash scripts/deploy_backend_vm.sh
```

The deployment helper performs its own migration dry-run before apply, installs current SOAR worker units, restarts affected services, and checks backend health. Do not manually apply ad hoc schema changes outside an explicitly approved emergency procedure.

### Combined frontend and backend change

Deploy backend/migrations first, verify API/service health, then deploy the Mac-built frontend artifact and run end-to-end smoke tests.

## Runtime and Data Safety

- Never print or paste secret values. Report only presence and sanitized effective state.
- Do not blindly retry queues, approvals, deliveries, or dead letters. Classify relevance, idempotency, and duplicate-side-effect risk first; use a small canary.
- Preserve historical rows and audit evidence. Do not manufacture success or delete backlog as cleanup.
- Preserve the intended integration model unless a dedicated approved change says otherwise: real-capable actions remain fail-closed; simulation/tracking-only features must not be silently promoted.
- Runtime workarounds are temporary. Record them and create a Mac source fix before relying on them for future deployments.

## Completion Evidence

Every deployment handoff must report:

- requested and deployed commit;
- clean-tree preflight result;
- migrations/backfills run and results;
- services restarted and health/status results;
- sanitized configuration/guard state;
- frontend artifact deployment when applicable;
- database/runtime before-and-after counts when data was changed;
- smoke-test results, rollback readiness, unresolved risks, and next owner;
- explicit confirmation of whether a commit, push, deployment, or production mutation occurred.
