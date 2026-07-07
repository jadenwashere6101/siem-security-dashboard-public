# Mac and VM Source-of-Truth Policy

The clean rule:

**Mac = development. VM = deployment/runtime.**

Do not let Terminal AI edit source code on the VM unless the task is explicitly declared a **VM emergency hotfix**.

The main rule:

**Never write code on the VM. Never merge on a dirty VM.**

## Mac Responsibilities

Save code changes only on the Mac source-of-truth repo:

```text
/Users/jadengomez/Desktop/siem-security-dashboard-public
```

Use the Mac for:

- specs
- code
- tests
- commits
- pushes

## VM Responsibilities

Use the VM only for deployment and runtime operations:

```text
jaden@4.204.25.149:/home/jaden/siem-security-dashboard
```

Use the VM for:

- `git fetch`
- `git merge origin/main`
- migrations
- seed scripts
- service restarts
- logs and smoke tests
- database/runtime playbook edits

Do not edit source code on the VM unless this is explicitly called a **VM emergency hotfix**.

## When To Sync The VM

Sync the VM after backend/runtime code changes.

A VM sync is required after pushing changes to:

- `core/`
- `engines/`
- `routes/`
- `helpers/`
- `scripts/`
- `migrations/`
- `schema.sql`
- playbook seed files

## When VM Sync Is Not Needed

No VM sync is needed after docs/spec-only changes.

No sync is needed for:

- `openspec/`
- docs only
- tests only
- frontend source unless deploying the frontend build

## Frontend Changes

Frontend UI changes are different. Build on the Mac, then copy only the built frontend output to the VM.

On the Mac:

```bash
cd /Users/jadengomez/Desktop/siem-security-dashboard-public/frontend
npm run build
rsync -avz --delete \
  -e "ssh -i ~/.ssh/jadeng15.pem" \
  /Users/jadengomez/Desktop/siem-security-dashboard-public/frontend/build/ \
  jaden@4.204.25.149:/home/jaden/siem-security-dashboard/frontend/build/
```

## Permanent VM Sync Command

Before syncing on the VM:

```bash
cd /home/jaden/siem-security-dashboard
git status --short
```

If `git status --short` prints anything, stop. Do not merge on a dirty VM.

If the VM is clean:

```bash
git fetch origin
git merge origin/main
```

Then, if backend code changed:

```bash
sudo systemctl restart siem-backend.service
sudo systemctl restart soar-playbook-worker.service
curl http://127.0.0.1:5051/health
```

If migrations changed:

```bash
bash scripts/deploy_backend_vm.sh --skip-restart
bash scripts/deploy_backend_vm.sh --dry-run-migrations
```

## AI Agent Instruction

When working in this project:

1. Treat the Mac repo as the only source-of-truth for source code.
2. Make specs, code, tests, commits, and pushes from the Mac repo only.
3. Use the VM only for deployment/runtime commands.
4. Before any VM merge, run `git status --short`.
5. If the VM is dirty, stop and report the dirty files.
6. Do not edit VM source code unless the user explicitly says this is a VM emergency hotfix.
7. Do not commit or push unless the user explicitly asks.

