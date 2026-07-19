## Context

The Mac repository is the source of truth and the VM is deployment/runtime only. Current source defines a Flask app shell in `siem_backend.py` with `create_app()`, module-level `app = create_app()`, `/health`, frontend static serving, and a `__main__` block that calls `app.run(host=SIEM_BIND_HOST, port=SIEM_PORT, debug=SIEM_DEBUG)`. Production has been audited as running through that Flask development-server path. The audit findings that govern this design are:

- `SIEM_DEBUG` must be false in production.
- `SIEM_BIND_HOST` must be `127.0.0.1` in production.
- Flask's development server and Werkzeug debugger must be impossible in production.
- Gunicorn is the required production WSGI server.

The deployment helper `scripts/deploy_backend_vm.sh` applies migrations, restarts `siem-backend.service`, installs/restarts worker units, and probes `http://127.0.0.1:${SIEM_PORT:-5051}/health`. It assumes `siem-backend.service` already exists on the VM; the repo has worker/listener systemd units but no source-controlled backend unit. Existing nginx remains the only public HTTP entrypoint and proxies to the backend on loopback.

## Goals / Non-Goals

**Goals:**

- Permanently remove Flask development-server usage from production.
- Make `siem-backend.service` source-controlled, installable, reviewable, and verifiable.
- Run production traffic through Gunicorn using the existing Flask WSGI object.
- Preserve current API behavior, static frontend serving, AI routes, SOAR, PostgreSQL, bank app, honeypot, and nginx topology.
- Add deployment and verification gates that fail closed when production runtime settings are unsafe.
- Document the production runtime contract clearly enough that future deployments cannot regress to `python siem_backend.py`.

**Non-Goals:**

- No Kubernetes, Docker, Celery, Redis, async rewrite, load balancer, reverse-proxy redesign, database migration, frontend redesign, bank app migration, honeypot migration, or SOAR architecture redesign.
- No VM implementation during this spec phase.
- No change to AI provider routing, SOAR action safety, authentication semantics, or application routes except runtime startup validation where needed.

## Architecture Findings

- `siem_backend:app` is already compatible with Gunicorn and should be the production WSGI target.
- `SIEM_BIND_HOST` currently defaults to `0.0.0.0`, which is acceptable only for local development; production must set and verify `127.0.0.1`.
- `SESSION_COOKIE_SECURE` is derived from `not SIEM_DEBUG`; therefore `SIEM_DEBUG=false` is mandatory for secure cookies.
- The `__main__` block is the only source path that invokes Flask's development server. Production must not call it.
- `deploy_backend_vm.sh` has a strong migration-before-restart flow and should be extended rather than replaced.
- Existing worker install helpers provide an appropriate dry-run/install/rollback/systemd-cat pattern for the backend service.
- Long AI investigations and provider calls can run longer than ordinary CRUD requests. The production WSGI timeout must accommodate bounded AI requests without masking true hangs.

## Decisions

### Runtime

- Use Gunicorn as the only production backend server with WSGI target `siem_backend:app`.
- Use the default synchronous worker class (`sync`) for Phase 1. The application is mostly request/response Flask with PostgreSQL and bounded external calls; an async worker would require broader dependency and behavior review.
- Use `--workers ${SIEM_GUNICORN_WORKERS:-2}` by default. Two workers provide isolation from one long request without multiplying process-local memory and in-memory counters excessively. Operators may set 3 only after memory review.
- Use `--bind ${SIEM_BIND_HOST:-127.0.0.1}:${SIEM_PORT:-5051}` and require production `.env` to set `SIEM_BIND_HOST=127.0.0.1`.
- Use `--timeout ${SIEM_GUNICORN_TIMEOUT:-120}`. This covers bounded AI requests and report generation while still killing stuck workers.
- Use `--graceful-timeout ${SIEM_GUNICORN_GRACEFUL_TIMEOUT:-30}` and `--keep-alive ${SIEM_GUNICORN_KEEPALIVE:-5}`.
- Use `--access-logfile -`, `--error-logfile -`, `--capture-output`, and `--log-level ${SIEM_GUNICORN_LOG_LEVEL:-info}` so journald captures stdout/stderr without app-specific log file paths.
- Keep `preload_app` off. It avoids copy-on-write surprises with environment loading and keeps startup failures isolated per worker.
- Do not remove the local-development `if __name__ == "__main__"` block in the first hardening change. Instead, document it as local-only and ensure production systemd never executes it. Removing or guarding it can be a later cleanup if needed.

### systemd

Add `deploy/systemd/siem-backend.service`:

```ini
[Unit]
Description=SIEM Backend API (Gunicorn WSGI)
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=jaden
Group=jaden
WorkingDirectory=/home/jaden/siem-security-dashboard
EnvironmentFile=/home/jaden/siem-security-dashboard/.env
Environment=PYTHONUNBUFFERED=1
Environment=SIEM_BIND_HOST=127.0.0.1
Environment=SIEM_PORT=5051
Environment=SIEM_DEBUG=false
ExecStartPre=/home/jaden/siem-security-dashboard/scripts/validate_backend_runtime_env.sh
ExecStart=/home/jaden/siem-security-dashboard/venv/bin/gunicorn --workers ${SIEM_GUNICORN_WORKERS:-2} --worker-class sync --bind ${SIEM_BIND_HOST:-127.0.0.1}:${SIEM_PORT:-5051} --timeout ${SIEM_GUNICORN_TIMEOUT:-120} --graceful-timeout ${SIEM_GUNICORN_GRACEFUL_TIMEOUT:-30} --keep-alive ${SIEM_GUNICORN_KEEPALIVE:-5} --access-logfile - --error-logfile - --capture-output --log-level ${SIEM_GUNICORN_LOG_LEVEL:-info} siem_backend:app
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=10
KillSignal=SIGTERM
TimeoutStopSec=45
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Implementation may use an `Environment=GUNICORN_CMD_ARGS=...` split if systemd variable expansion becomes hard to test, but the effective unit must still show the same runtime choices.

Add `scripts/validate_backend_runtime_env.sh` for startup validation. It must fail production startup when `SIEM_DEBUG` is true, `SIEM_BIND_HOST` is not `127.0.0.1`, required secret/admin/database settings are absent, or `venv/bin/gunicorn` is missing. It must not print secret values.

Add `scripts/install_siem_backend_service.sh` using the existing helper pattern: `--dry-run`, install, `--enable`, `--start`, `--reload`, `--rollback`, preflight, `systemctl daemon-reload`, `systemctl status`, `systemctl cat`, and safe rollback.

### Deployment

Update `scripts/deploy_backend_vm.sh` to:

1. Preflight repo root, venv, `.env`, database settings, and Gunicorn availability.
2. Print sanitized runtime preflight including `SIEM_DEBUG`, `SIEM_BIND_HOST`, `SIEM_PORT`, Gunicorn workers, timeout, and service name.
3. Run migration dry-run.
4. Apply migrations.
5. Install/update `siem-backend.service` from the repo and reload systemd.
6. Restart backend through systemd.
7. Verify service status and `systemctl cat` contains Gunicorn and not `python siem_backend.py`.
8. Verify `/health` on loopback.
9. Verify production security gates.
10. Install/restart worker units only after backend health and security gates pass.

Do not add `git fetch`, `git reset`, frontend build, nginx reload, migrations beyond existing flow, or provider configuration changes to this helper.

### Environment

Mandatory production values:

- `SIEM_DEBUG=false`
- `SIEM_BIND_HOST=127.0.0.1`
- `SIEM_PORT=5051` unless nginx and docs are intentionally updated together
- `SIEM_SECRET_KEY` or `SECRET_KEY` present
- `SIEM_ADMIN_USERNAME` and `SIEM_ADMIN_PASSWORD` present
- `DATABASE_URL` or complete `SIEM_DB_*`/`DB_*` settings present
- `SESSION_COOKIE_SECURE=True` as effective Flask config, derived from `SIEM_DEBUG=false`

Optional production values:

- `SIEM_GUNICORN_WORKERS`, default 2
- `SIEM_GUNICORN_TIMEOUT`, default 120
- `SIEM_GUNICORN_GRACEFUL_TIMEOUT`, default 30
- `SIEM_GUNICORN_KEEPALIVE`, default 5
- `SIEM_GUNICORN_LOG_LEVEL`, default info

### Health, Security, And Operational Verification

Every backend deployment must verify:

- Gunicorn master/workers are serving `siem_backend:app`.
- No process command line for `siem-backend.service` uses `python siem_backend.py`, `flask run`, or `app.run`.
- `curl -fsS http://127.0.0.1:5051/health` returns ok.
- `ss -ltnp` shows backend listening only on `127.0.0.1:5051`.
- Public raw backend port `5051` is not reachable.
- Werkzeug debugger probes return no debugger signature.
- Public `/login` sets a `Secure; HttpOnly; SameSite=Lax` session cookie when a session is created.
- nginx is the only public HTTP/HTTPS listener for SIEM traffic.
- AI routes respond through authenticated workflows, including a focused long-running AI smoke with timeout below Gunicorn timeout.
- SOAR metrics/approval/read routes still load and workers remain healthy.
- PostgreSQL connectivity and migration ledger are intact.
- Bank app and honeypot listeners/services are unaffected.

### Documentation Update Plan

Update during implementation:

- `AGENTS.md`: add a short protective duplicate that production backend deployments must use Gunicorn/systemd, never Flask development server.
- `docs/mac-vm-source-of-truth-policy.md`: update backend/runtime deployment matrix and completion evidence to include Gunicorn service installation and security gates.
- `docs/schema_migration_workflow.md`: change app health example to loopback production backend and include Gunicorn runtime validation after schema apply.
- `docs/soar_handoff.md`: replace "nginx sits in front of Flask" with "nginx sits in front of Gunicorn serving the Flask WSGI app".
- `docs/soar_worker_deployment_checklist.md`: require backend Gunicorn/security verification before worker restarts.
- `docs/pfsense_deployment_runtime_readiness.md`: replace `git merge origin/main` with source-of-truth reset workflow and include Gunicorn backend service verification.
- `docs/verification-checklist.md` and `docs/behavior-checks.md`: add production security gate checks where backend health is referenced.
- Add a focused backend runtime runbook, for example `docs/production_wsgi_runtime.md`, covering install, start, reload, rollback, security checks, logs, and troubleshooting.
- Update stale docs that imply backend production is direct Flask. Do not broadly rewrite historical handoff docs unless they are active runbooks.

`deploy.sh` is a frontend example helper with unsafe generic git behavior. Implementation should either mark it legacy/example-only or replace its wording with the documented Mac build to VM rsync model if it is still retained.

## Implementation Plan

1. Add Gunicorn to runtime dependencies if missing and verify it installs in the VM venv.
2. Add `deploy/systemd/siem-backend.service`.
3. Add `scripts/validate_backend_runtime_env.sh`.
4. Add `scripts/install_siem_backend_service.sh`.
5. Update `scripts/deploy_backend_vm.sh` to install/update backend service before restart and run runtime/security checks after restart.
6. Add focused script/unit tests for service template, install helper, deployment ordering, redaction, failure handling, and security gate checks.
7. Update the documentation listed above.
8. Run local verification, then hand off for a later authorized VM deployment.

## Rollout Plan

Mac AI implementation phase:

1. Implement source-controlled unit/helper/script/docs/tests.
2. Run `python3 -m py_compile` for changed scripts where applicable.
3. Run focused pytest for deployment scripts plus affected backend smoke tests.
4. Run `git diff --check` and `openspec validate production-wsgi-hardening --strict`.
5. Stop for review, commit/push authorization, and VM deployment authorization.

VM deployment phase after authorization:

1. Confirm VM clean tree and approved commit.
2. Sync VM to approved commit using the source-of-truth policy.
3. Run migration dry-run.
4. Run backend deployment helper.
5. Verify Gunicorn, loopback bind, health, debugger absence, secure cookies, raw port isolation, nginx proxy, AI routes, SOAR, PostgreSQL, bank app, and honeypot.
6. Record sanitized before/after evidence.

## Rollback Plan

- Keep the prior authorized commit SHA and current installed `/etc/systemd/system/siem-backend.service` content captured before rollout.
- If the new unit fails preflight before restart, stop rollout and keep the current backend running.
- If Gunicorn restart fails health/security checks, restore the prior authorized commit and prior backend unit, run `systemctl daemon-reload`, restart `siem-backend.service`, and verify `/health`.
- If migrations were applied before failure, use only existing forward-compatible migration policy; do not improvise destructive rollback.
- If worker restarts have not run yet, leave workers untouched. If workers were restarted after backend success, verify or roll back them through their existing helpers.
- Do not change nginx, bank app, honeypot, provider config, database rows, or firewall/NSG rules as part of rollback unless a separate approved incident procedure requires it.

## Risks / Trade-offs

- Gunicorn sync workers can be occupied by long AI requests -> default to two workers and 120 second timeout, keep AI requests bounded, and verify long AI smoke.
- Process-local counters reset per worker and on restart -> document existing limitation; do not introduce shared state in this hardening change.
- More workers increase PostgreSQL connections and memory -> default to 2 and require memory review before increasing.
- systemd environment expansion can be brittle -> cover the effective unit with tests and `systemctl cat` verification.
- Startup validation can block production if `.env` is incomplete -> fail closed with sanitized messages.
- Existing docs contain stale VM sync commands -> update active runbooks precisely and point them to the source-of-truth policy.

## Open Questions

- None blocking. Operators may tune `SIEM_GUNICORN_WORKERS` after measuring VM memory, but the default production design is fixed at 2 sync workers.

## Acceptance Criteria

- Production backend service uses Gunicorn and never invokes Flask development server.
- Source-controlled unit/helper/deploy script can install, restart, reload, verify, and roll back the backend service.
- Production startup fails closed for unsafe debug/bind settings.
- Deployment verification proves loopback-only backend, nginx-only public exposure, debugger absence, secure cookies, health, AI, SOAR, PostgreSQL, bank app, and honeypot are intact.
- Documentation clearly states that `python siem_backend.py` and Flask `app.run()` are local-development-only.
