# Production WSGI Runtime

The SIEM backend production runtime is Gunicorn under systemd. Flask's `app.run()`
path in `siem_backend.py` is local-development-only and must not serve production
traffic.

## Architecture

```text
public HTTP/HTTPS
  -> nginx
  -> 127.0.0.1:5051
  -> siem-backend.service
  -> Gunicorn sync workers
  -> siem_backend:app
```

The backend service is source-controlled at:

```text
deploy/systemd/siem-backend.service
```

Installed path on the VM:

```text
/etc/systemd/system/siem-backend.service
```

## Production Environment

Mandatory production values:

- `SIEM_DEBUG=false`
- `SIEM_BIND_HOST=127.0.0.1`
- `SIEM_PORT=5051`
- `SIEM_SECRET_KEY` or `SECRET_KEY`
- `SIEM_ADMIN_USERNAME` and `SIEM_ADMIN_PASSWORD`
- `DATABASE_URL` or complete `SIEM_DB_*` / `DB_*` settings
- `SIEM_RATE_LIMIT_STORAGE_URI` pointing at loopback Redis for Flask-Limiter counters

Optional Gunicorn tuning:

- `SIEM_GUNICORN_WORKERS`, default `2`
- `SIEM_GUNICORN_TIMEOUT`, default `120`
- `SIEM_GUNICORN_GRACEFUL_TIMEOUT`, default `30`
- `SIEM_GUNICORN_KEEPALIVE`, default `5`
- `SIEM_GUNICORN_LOG_LEVEL`, default `info`

Do not print secret values when validating `.env`, including Redis limiter URI
credentials or query parameters.

`SIEM_RATE_LIMIT_STORAGE_URI` is mandatory in production and must use `redis://`
or `rediss://` loopback storage, for example:

```text
SIEM_RATE_LIMIT_STORAGE_URI=redis://127.0.0.1:6379/0
```

Redis is scoped only to Flask-Limiter counters. Do not use it for sessions,
caches, queues, SOAR execution, notification delivery, or application data as
part of this runtime.

## Install Or Update

Run only on the VM after an approved commit has been synced by the source-of-truth
policy.

```bash
cd /home/jaden/siem-security-dashboard
scripts/install_siem_backend_service.sh --dry-run
scripts/install_siem_backend_service.sh --enable --start
```

Routine backend deployments should use:

```bash
bash scripts/deploy_backend_vm.sh --dry-run-migrations
bash scripts/deploy_backend_vm.sh
```

The deploy helper installs the repo-owned backend unit before restart and verifies
health, shared limiter storage, and local security gates before worker restarts.

## Reload, Restart, And Logs

Graceful reload:

```bash
sudo systemctl reload siem-backend.service
curl -fsS http://127.0.0.1:5051/health
```

Restart:

```bash
sudo systemctl restart siem-backend.service
sudo systemctl status siem-backend.service --no-pager
```

Effective unit and logs:

```bash
sudo systemctl cat siem-backend.service --no-pager
journalctl -u siem-backend.service -n 100 --no-pager
```

The effective unit must show Gunicorn and `siem_backend:app`; it must not show
`python siem_backend.py`, `flask run`, or `app.run`.

## Security Verification

Every production backend deployment must verify:

```bash
curl -fsS http://127.0.0.1:5051/health
ss -ltnp | grep '127.0.0.1:5051'
ss -ltnp | grep '127.0.0.1:6379'
sudo systemctl cat siem-backend.service --no-pager | grep gunicorn
sudo systemctl cat siem-backend.service --no-pager | grep 'siem_backend:app'
```

Also verify:

- `SIEM_DEBUG=false`
- `SIEM_BIND_HOST=127.0.0.1`
- `SIEM_RATE_LIMIT_STORAGE_URI` is present, redacted in logs, and reachable
- raw public port `5051` is not reachable
- Werkzeug debugger probes do not return debugger signatures
- public `/login` session cookies include `Secure`, `HttpOnly`, and `SameSite=Lax`
- repeated `/login` attempts share one limiter counter across Gunicorn workers
- limiter counters survive `systemctl reload siem-backend.service` until their TTL expires
- nginx is the only public HTTP/HTTPS entrypoint for SIEM traffic
- AI, SOAR, PostgreSQL, bank app, honeypot, and static frontend checks still pass

## Rollback

Before rollout, capture the approved SHA and current installed unit:

```bash
git rev-parse HEAD
sudo systemctl cat siem-backend.service --no-pager
```

If the new unit fails before restart, stop and leave the current service running.
If restart or security checks fail after restart, restore the prior approved commit
and prior backend unit, then run:

```bash
sudo systemctl daemon-reload
sudo systemctl restart siem-backend.service
curl -fsS http://127.0.0.1:5051/health
```

Do not alter nginx, database rows, migrations, bank app, honeypot, provider
configuration, VM firewall, or Azure NSG rules as part of this rollback unless a
separate approved incident procedure requires it.

If Redis limiter storage is the failing component, restore the prior approved
commit and prior limiter environment state. Do not silently configure production
memory storage on the new code.
