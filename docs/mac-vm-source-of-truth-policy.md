# Mac, Azure VM, and Mini PC Source-of-Truth Policy

## Non-Negotiable Rule

**Mac = development/source of truth. Azure VM = production application/runtime. Mini PC = production local-AI inference host.**

Never write source code on the VM. Never use `git merge origin/main` or `git pull` to synchronize the VM — merging is never used to sync the VM, clean or dirty. After a clean-tree and approved-commit preflight (see VM Clean-Tree Gate), synchronize only with:

```bash
git fetch origin
git reset --hard origin/main
```

The only exception:

- **VM emergency hotfix** — requires explicit user authorization, a backup, and a documented rollback, and must be copied back into the Mac source of truth immediately and reconciled through normal version control.

Do not develop application source on the Mini PC. It is an inference appliance, not a second source checkout, SIEM deployment target, worker host, or application database host.

## Verified Production Architecture

The following topology was verified read-only on 2026-08-03:

```text
Mac source-of-truth repository
  -> OpenSpec, implementation, tests, builds, approved commit/push
  -> approved source or frontend artifact
  -> Azure VM

Analyst browser
  -> public HTTPS /siem/
  -> Azure VM nginx and static frontend
  -> Azure VM Gunicorn/Flask on 127.0.0.1:5051
     -> PostgreSQL, queues, conversation state, SOC tools, and audit state
     -> synchronous planner and Quick Explain orchestration
     -> queued asynchronous workflow requests

Azure VM systemd runtime
  -> siem-backend.service
  -> anakin-workflow-worker.timer/service
  -> soc-briefing-worker.timer/service
  -> soar-playbook-worker.service
  -> soar-response-action-worker.timer/service
  -> pfsense-syslog-listener.service

Azure VM backend or AI worker
  -> local-only AI Gateway
  -> AI_LOCAL_BASE_URL over Tailscale
  -> Mini PC Ollama HTTP API on TCP 11434
     -> qwen3:14b planner inference
     -> llama3.2:3b or llama3.1:8b for existing non-planner profiles
  -> result returns to the calling VM process
  -> backend/worker validates and persists the response
  -> frontend polls or receives and renders the result
```

Verified live facts:

- the Azure VM's effective AI gateway is `local_only` with provider `ollama`;
- the VM's effective `AI_LOCAL_BASE_URL` matches the Mini PC's Tailscale address;
- VM-to-Mini-PC Tailscale ping and Ollama `/api/version` and `/api/tags` calls succeed;
- the Mini PC runs Ollama `0.32.5` and has `llama3.2:3b`, `llama3.1:8b`, and benchmarked `qwen3:14b` available;
- a live `plan_turn` request from the VM reached the Mini PC and received a successful Ollama generation response;
- no paid fallback is part of this verified path.

Do not store the Mini PC's Tailscale IP, tailnet name, or private endpoint in this public repository. The exact endpoint belongs only in protected runtime configuration. Verify endpoint identity by comparing sanitized VM configuration, Mini PC listener state, and Tailscale peer identity.

## Mini PC Runtime Contract

The production inference host is `ANAKIN-MINI-PC`, a Windows 11 GMKtec NucBox K8 Plus. Ollama is installed per-user and runs as `ollama.exe serve` from that runtime user's Windows startup session; it is not a Windows service.

Ollama is intentionally bound to the Mini PC's Tailscale address, not to `127.0.0.1`, the LAN address, or all interfaces. Windows Firewall allows TCP `11434` only from the Azure SIEM VM's Tailscale peer. Therefore:

- a failed `http://127.0.0.1:11434` check does **not** prove Ollama is stopped;
- an audit run under a different Windows account may not find the per-user executable, startup entry, process context, or model store;
- Mini PC verification must inspect the actual Ollama runtime account, effective `OLLAMA_HOST`, Tailscale-bound listener, process, and API through that bound address;
- Azure verification must originate from the VM and use its protected `AI_LOCAL_BASE_URL`.

The Mini PC has approximately 32 GB installed RAM and stores the required Ollama models in the Ollama runtime user's profile. The current installed model contract is:

| Model | Production use | Verified state |
| --- | --- | --- |
| `qwen3:14b` | Current verified deployed `agentic_planning` baseline pending an authorized hybrid rollout | Installed and benchmarked; materially outperforms the previous local planner model |
| `llama3.2:3b` | Existing `fast_triage` default, including Quick Explain | Installed; generation works; assignment unchanged |
| `llama3.1:8b` | Guided Analysis, Deep Briefing, and Developer Assistant; previous planner model | Installed and retained; no longer the configured `agentic_planning` model after deployment |

## Planner Model Verification Status

An apples-to-apples Mini PC benchmark changed only the planner model while preserving architecture, prompts, facts, schema, validator, temperature, token limit, and prompt limit. Compared with `llama3.1:8b`, `qwen3:14b` improved semantic action accuracy from `16.7%` to `70%`, complete valid-plan rate after repair from `0%` to `36.7%`, and repair success from `0%` to `24%`; clarification collapse fell from `93%` to `17%`, and meaningful action diversity increased from effectively two classes to eight.

The previously deployed local `agentic_planning` baseline is therefore `qwen3:14b`. Phase 2 Mac source assigns `agentic_planning` to a feature-disabled Anthropic profile, while production remains on the verified local baseline until an approved commit, later paid-budget controls, deployment, and browser-path acceptance exist. Median local initial planner generation was approximately `44.9s`, maximum initial generation approximately `76.7s`, and an initial-plus-repair path may approach `2.4` minutes.

Do not report the planner as working based only on provider success or benchmark results. Distinguish `provider_status=success` from `plan validation accepted` and from a grounded analyst-facing result.

## Authoritative Locations

Mac repository:

```text
/Users/jadengomez/Projects/siem-security-dashboard-public
```

VM repository/runtime:

```text
jaden@4.204.25.149:/home/jaden/siem-security-dashboard
```

The repository path `/home/jaden/siem-security-dashboard` is deployment/runtime only. Model and profile source changes originate in the Mac repository, are tested there, and require an explicitly authorized commit and push before the VM may sync and verify them. Never edit source code on the VM.

Mini PC inference runtime:

```text
Host identity: ANAKIN-MINI-PC
Transport: Tailscale-private Ollama HTTP endpoint on TCP 11434
Exact address: protected Azure VM runtime configuration, not source control
```

`ANAKIN-MINI-PC` is an inference host only. It is not a source-code repository; model installation or runtime changes require separate authorization and do not replace Mac implementation plus VM deployment verification.

The old `/Users/jadengomez/Desktop/siem-security-dashboard-public` checkout is obsolete and absent. Agents must not use or recreate it.

## Ownership

**Ownership test:** durable source, specification, migration, backend, frontend, test, and documentation changes belong to Mac AI. Azure VM AI owns deployment, application runtime, database/queues/workers, and production acceptance. Mini PC runtime work is limited to Ollama, installed models, Tailscale-bound inference, and model performance/capability verification.

### Mac AI

Use the Mac repository for:

- audits and OpenSpec artifacts;
- frontend/backend source and deployment templates;
- migrations, schema snapshot, seed files, scripts, tests, and documentation;
- frontend production builds;
- temporary model-evaluation harnesses generated from source, using identical packets/settings across compared models;
- commits and pushes, only when explicitly authorized.

### VM AI

Use the VM only for explicitly authorized:

- clean-tree preflight, `git fetch`, and syncing to the approved remote commit via `git reset --hard`;
- migration dry-runs/applies and approved backfills;
- runtime `.env`/secret configuration without exposing values;
- systemd install/reload/restart/status and journal review;
- database/runtime queue, approval, and dead-letter operations;
- backend health checks, frontend artifact deployment, and live smoke tests;
- sanitized effective AI gateway/profile verification and VM-to-Mini-PC connectivity checks;
- end-to-end production acceptance through the real `/siem/` browser path.

The VM AI must not invent or implement durable fixes. Any required source, migration, unit-template, wrapper, API, or UI change is handed back to the Mac AI.

### Mini PC Runtime

Use the Mini PC only for explicitly authorized:

- Tailscale and Ollama readiness/listener checks;
- installed-model inventory and direct generation tests;
- model-only capability, latency, resource, and thermal evaluation;
- separately approved Ollama/model installation or configuration work.

Do not use the Mini PC for source implementation, OpenSpec work, SIEM application deployment, PostgreSQL changes, queue/worker execution, or production acceptance by itself. Direct Ollama success proves inference availability only; it does not prove planner validation, VM orchestration, worker completion, or frontend rendering.

## Machine Responsibility Matrix

| Activity | Authoritative machine | Rule |
| --- | --- | --- |
| Feature implementation, OpenSpec, migrations, tests, and documentation | Mac | All durable source changes originate here. |
| Commit and push | Mac | Only with explicit user authorization. |
| Application deployment, migrations, nginx, backend, workers, timers, and PostgreSQL | Azure VM | Sync only an approved commit through the clean-tree gate. |
| Runtime and queue verification | Azure VM | Verify effective installed state, not only repository templates. |
| Ollama service, model inventory, and model-only evaluation | Mini PC | Inspect the actual Ollama Windows account and Tailscale-bound endpoint. |
| End-to-end AI performance | Azure VM plus Mini PC | Separate application/queue latency from Ollama generation latency. |
| Production acceptance | Azure VM `/siem/` path plus Mini PC | Must include the configured provider, worker when applicable, and rendered UI. |

## AI Runtime Verification Procedure

For every AI deployment or model evaluation:

1. On the Mini PC, verify the actual Ollama runtime account, `ollama.exe serve`, effective `OLLAMA_HOST`, TCP `11434` listener, Tailscale identity, `/api/version`, `/api/tags`, and installed models. Do not substitute loopback when Ollama is Tailscale-bound.
2. On the Azure VM, verify sanitized effective `AI_GATEWAY_MODE`, `AI_LOCAL_PROVIDER`, `AI_LOCAL_BASE_URL` host identity, and effective model per profile. Source defaults alone are insufficient.
3. From the Azure VM, run Tailscale ping, TCP connectivity, `/api/version`, and `/api/tags` against the configured endpoint.
4. Exercise the actual application path and record provider status, selected profile/model, validation status, repair status, latency, and final UI result.
5. For model comparisons, use byte-identical planner packets, prompts, generation settings, and repeated trials. Provider success and structurally valid JSON are separate measurements from semantically valid plans.

## Spec-to-Deployment Workflow

1. Audit existing code, tests, active changes, legacy paths, and affected analyst/runtime workflows.
2. Create the minimum safe OpenSpec structure. Label each change and implementation phase **Mac AI** or **VM AI**.
3. Mac AI implements only the selected phase and runs focused plus affected regression checks.
4. The user explicitly authorizes any commit and push.
5. VM AI deploys only that approved commit after clean-tree verification.
6. VM AI captures sanitized before/after evidence and performs only the specified runtime/data remediation.
7. Work is complete only when all required source verification and production verification are complete.

Specs/docs/tests alone do not require VM synchronization. Source changes do not reach the VM until committed, pushed, and explicitly deployed.

## Anakin Production Completion Gate

All Anakin changes must follow [Anakin Production Acceptance Policy](anakin-production-acceptance-policy.md) before being reported as working, done, fully verified, or production-ready.

Automated tests, OpenSpec validation, frontend builds, service health, direct-backend localhost 200s, and offline acceptance harness success are not sufficient for Anakin completion. Final acceptance requires browser-path verification through:

```text
browser -> /siem/ -> nginx -> frontend -> backend -> worker/Ollama -> frontend-rendered result
```

In the verified production topology, nginx, frontend, backend, and workers run on the Azure VM; Ollama inference runs on the Mini PC over Tailscale. Synchronous paths may call Ollama directly from Gunicorn, while asynchronous paths include the Azure VM worker before Ollama.

If that browser-path verification was not performed, the only allowed completion wording is:

```text
Implementation complete; production behavior unverified.
```

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

After the VM clean-tree sync, use the repository deployment/runbook instructions. Production SIEM backend traffic must be served by Gunicorn through `siem-backend.service`; Flask's development server is local-development-only and must not serve production traffic. Restart only affected services and verify:

```bash
curl -fsS http://127.0.0.1:5051/health
```

Inspect relevant service status/journals and effective configuration without printing secrets. Backend verification must include Gunicorn process/effective-unit evidence, `SIEM_DEBUG=false`, `SIEM_BIND_HOST=127.0.0.1`, loopback-only backend bind, debugger absence, raw port `5051` not publicly reachable, `Secure` session cookies, and shared Redis-backed Flask-Limiter storage on loopback. Redis is used only for Flask-Limiter counters, not sessions, queues, caches, SOAR execution, or application data.

### Migrations or schema changes

On the Mac, migration tests and schema snapshot validation must pass first. On the clean, synced VM:

```bash
bash scripts/deploy_backend_vm.sh --dry-run-migrations
bash scripts/deploy_backend_vm.sh
```

The deployment helper performs its own migration dry-run before apply, installs the current Gunicorn backend unit and SOAR worker units, restarts affected services, and checks backend health plus production runtime security gates. Do not manually apply ad hoc schema changes outside an explicitly approved emergency procedure.

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
- sanitized configuration/guard state, including Gunicorn runtime evidence and production security gates;
- frontend artifact deployment when applicable;
- database/runtime before-and-after counts when data was changed;
- smoke-test results, rollback readiness, unresolved risks, and next owner;
- explicit confirmation of whether a commit, push, deployment, or production mutation occurred.
