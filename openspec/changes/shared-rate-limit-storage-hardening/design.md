## Context

`core/extensions.py` currently creates a process-local Flask-Limiter instance with `key_func=get_remote_address` and no configured storage URI. `siem_backend.create_app()` calls `limiter.init_app(app)` and registers a JSON 429 handler returning `{"error": "rate_limited", "message": "Too many requests. Please try again later."}`.

The limiter-protected HTTP routes are:

- `POST /login`: `5 per minute`
- selected admin routes in `routes/admin_routes.py`: mostly `30 per minute`, with two `10 per minute` operations
- `routes/alert_mutation_routes.py`: `30 per minute`
- `routes/ingest_routes.py`: `200 per minute`

Production WSGI hardening defines the backend as Gunicorn sync workers under `siem-backend.service`, defaulting to two workers, loopback bind, and graceful reload. With Flask-Limiter memory storage, each worker has separate counters. Effective production limits can multiply by worker count and reset on worker restart or graceful reload. The recent test run also reports Flask-Limiter's in-memory storage warning.

No Redis runtime dependency or service is currently part of the active production architecture. Redis appears only in roadmap or non-goal language for unrelated future queue/cache work. This change introduces Redis strictly as Flask-Limiter storage.

## Goals / Non-Goals

**Goals:**

- Enforce existing Flask-Limiter policies consistently across Gunicorn workers.
- Preserve route-level limits, keying, 429 response shape, authentication behavior, nginx routing, Gunicorn architecture, database behavior, SOAR workers, bank app, and honeypot behavior.
- Fail closed in production when shared limiter storage is missing or unavailable.
- Keep local development and tests simple by allowing explicit in-memory storage outside production.
- Add secret-safe validation, logging, documentation, deployment verification, rollback, and focused tests.

**Non-Goals:**

- No authentication redesign, nginx redesign, Gunicorn redesign, Flask route redesign, database-backed limiter tables, application caching, session storage migration, Celery/RQ, Redis queues, SOAR queue migration, background telemetry analysis, or firewall/NSG automation.
- No implementation, commit, push, VM access, or deployment during this spec phase.
- No changes to actual rate-limit values unless a focused test reveals an existing typo or route registration defect directly blocking the storage change.

## Decisions

### Shared Storage Technology

Use Redis as Flask-Limiter storage with a production URI:

```text
SIEM_RATE_LIMIT_STORAGE_URI=redis://127.0.0.1:6379/0
```

Rationale: Flask-Limiter supports Redis through its `limits` storage layer, Redis provides atomic counter operations and TTLs, and a loopback-only Redis service is the smallest common shared backend for multi-process rate limits. PostgreSQL was rejected because Flask-Limiter does not provide a first-class PostgreSQL counter backend and implementing one would be broader and riskier. Memcached was rejected because Redis gives better TTL/counter semantics and operational familiarity for this use case.

Redis is only for limiter counters. The implementation must not introduce Redis for caching, sessions, task queues, SOAR execution, notification delivery, deduplication, or application data.

### Configuration Contract

Add `SIEM_RATE_LIMIT_STORAGE_URI`.

Production requirements:

- `SIEM_DEBUG=false`
- `SIEM_BIND_HOST=127.0.0.1`
- `SIEM_RATE_LIMIT_STORAGE_URI` present
- URI scheme must be `redis://` or `rediss://`
- URI host must be loopback (`127.0.0.1`, `localhost`, or `::1`) unless a later approved infrastructure change documents a managed Redis endpoint
- Redis connectivity ping must pass before Gunicorn starts
- logs and preflight output must redact credentials and query parameters

Local development and tests:

- If `SIEM_DEBUG=true` or a test disables the limiter, `SIEM_RATE_LIMIT_STORAGE_URI` may be unset and the app may use Flask-Limiter memory storage.
- Developers may explicitly set `SIEM_RATE_LIMIT_STORAGE_URI=memory://` only for local development/tests.
- Production validation must reject `memory://`.

### Flask-Limiter Ownership

Keep limiter ownership in `core/extensions.py`. Add a small configuration helper there or in a nearby `core/rate_limit_config.py` module to resolve storage settings. `siem_backend.create_app()` should apply the resolved config before `limiter.init_app(app)`.

Do not move limiter decorators, route ownership, auth logic, or route response contracts. The existing `@limiter.limit(...)` decorators remain the policy source of truth.

### Fail-Safe Behavior

Production startup fails before Gunicorn serves traffic if Redis is unavailable, the URI is missing/unsafe, or the Redis client dependency is missing.

Runtime outage behavior must fail closed for limiter-protected routes:

- Exceeded limits continue returning the existing 429 JSON body.
- Limiter storage failures return a sanitized 503 JSON response such as `{"error": "rate_limit_storage_unavailable", "message": "Rate limiting is temporarily unavailable. Please try again later."}`.
- The app must not silently disable limits or fall back to memory in production.
- Error logs may name the storage role and exception class but must not include passwords, tokens, full URIs, cookies, or request bodies.

Normal routes without limiter decorators should continue to work unless the application-level readiness policy intentionally marks the instance unhealthy. `/health` remains the basic process health check; add either deployment helper validation or a small readiness check script for Redis rather than changing public API behavior broadly.

### Startup, Readiness, And Deployment

Extend `scripts/validate_backend_runtime_env.sh` to validate the limiter storage URI and ping Redis in production. The validator should use the project venv Python and the Redis client dependency so it tests the same runtime dependency Gunicorn uses.

Extend `scripts/deploy_backend_vm.sh` preflight output with sanitized limiter storage state:

- storage backend type: `redis`
- host/port/database without credentials
- connectivity: checked

Deployment order:

1. VM AI confirms clean tree and approved commit in a later authorized rollout.
2. Ensure VM Redis service is installed/enabled/running and loopback-only.
3. Install Python requirements into the venv if needed.
4. Run `scripts/deploy_backend_vm.sh --dry-run-migrations`.
5. Run `scripts/deploy_backend_vm.sh`.
6. Validate Gunicorn/security gates from production WSGI hardening.
7. Validate limiter storage, shared counters, and graceful reload behavior.

Do not add Redis package installation or firewall changes to `deploy_backend_vm.sh`; document them as VM runtime preflight steps. The deployment helper should fail clearly if the runtime dependency is missing.

### Monitoring And Logging

Startup and deployment logs must show sanitized effective state only. Required evidence:

- Redis limiter storage configured
- Redis ping successful
- Redis service listening on loopback only
- no credentials in logs
- Gunicorn workers still serving `siem_backend:app`
- production security gates still true

Do not add background telemetry, metric exporters, dashboards, or external monitoring integrations in this change.

### Verification Strategy

Automated tests should cover:

- storage URI resolution for production Redis and local memory
- production rejection of missing URI, `memory://`, unsafe scheme, public host, and missing dependency/connectivity
- no secret leakage in validation/preflight failures
- limiter config applied before `limiter.init_app(app)`
- existing 429 JSON response still returned for exceeded login limits
- storage failure returns the approved sanitized fail-closed response
- deployment helper ordering and redacted limiter preflight output
- production WSGI security tests remain intact

Manual VM rollout verification, later and only after approval, should prove:

- Redis service is loopback-only and not public
- two or more Gunicorn workers share the same `/login` limit
- counters survive `systemctl reload siem-backend.service` until their TTL expires
- restarting/rotating one worker does not reset counters
- Redis outage causes approved fail-closed behavior and health/readiness evidence
- auth, normal pages, AI, SOAR, PostgreSQL, bank app, honeypot, nginx, secure cookies, debugger absence, and raw port isolation remain intact

## Risks / Trade-offs

- Redis adds a new production runtime dependency -> keep it loopback-only, limited to rate-limit counters, and validate startup explicitly.
- Redis outage can block protected routes -> fail closed is intentional for authentication and mutation safety; document operator remediation and rollback.
- Existing tests disable the limiter globally in `tests/conftest.py` -> add focused tests that explicitly enable limiter behavior for the storage change.
- Full multi-worker consistency is difficult to prove with unit tests alone -> require a VM rollout smoke using Gunicorn with at least two workers.
- URI values may contain credentials -> always redact full URIs in logs and test secret-leak paths.
- Redis counters are not durable across Redis flush/restart -> acceptable for rate limiting; this is not audit, queue, session, or application persistence.

## Rollout Plan

Mac AI implementation phase:

1. Implement Redis-backed limiter configuration and validation.
2. Add dependency and focused tests.
3. Update deployment helper preflight/security checks and docs.
4. Run focused backend tests, syntax checks, `git diff --check`, and OpenSpec validation.
5. Stop for user review, commit/push authorization, and separate VM rollout authorization.

VM AI rollout phase after authorization:

1. Confirm VM clean tree and approved commit.
2. Confirm Redis package/service availability, loopback bind, and sanitized config.
3. Sync approved commit according to the source-of-truth policy.
4. Update venv requirements.
5. Configure `SIEM_RATE_LIMIT_STORAGE_URI` in `.env` without exposing secrets.
6. Run backend deploy helper.
7. Run production WSGI security gates and limiter shared-counter verification.
8. Capture sanitized before/after evidence.

## Rollback Plan

- Before rollout, capture approved commit SHA, current `.env` key presence, Redis service status, backend effective unit, and `/health`.
- If validation fails before backend restart, stop rollout and keep the current backend running.
- If Redis-backed limiter fails after restart, restore the prior approved commit and prior limiter environment setting, restart `siem-backend.service`, and verify `/health` and auth.
- If Redis is the only failing component and the prior code requires no Redis, disable only the Redis limiter env setting as part of restoring the prior commit; do not silently configure production memory storage on the new code.
- Do not change nginx, Gunicorn worker strategy, database schema/data, SOAR behavior, bank app, honeypot, firewall/NSG, sessions, or provider configuration as part of rollback unless separately authorized.

## Documentation Update Plan

Update during implementation:

- `AGENTS.md`: add a concise production safeguard that shared limiter storage must remain production-safe and must not regress to in-memory under Gunicorn.
- `docs/mac-vm-source-of-truth-policy.md`: add limiter storage to backend/runtime deployment expectations and completion evidence.
- `docs/production_wsgi_runtime.md`: add Redis limiter storage env, validation, rollout, rollback, and security checks.
- `docs/schema_migration_workflow.md`, `docs/soar_worker_deployment_checklist.md`, `docs/verification-checklist.md`, and `docs/behavior-checks.md`: add precise limiter storage verification where backend production gates are listed.
- Environment/runbook documentation: document `SIEM_RATE_LIMIT_STORAGE_URI` as production mandatory and secret-sensitive.

## Open Questions

- None blocking. The exact Redis package/service installation command is a VM operational detail and should be confirmed during authorized VM rollout based on the VM OS, but the production runtime contract is fixed: Redis-compatible Flask-Limiter storage on loopback only.

## Acceptance Criteria

- Production Flask-Limiter storage is Redis-backed and shared across Gunicorn workers.
- Production startup fails closed for missing, memory, unsafe, or unreachable limiter storage.
- Existing rate-limit values, keying, decorators, and exceeded-limit 429 response are preserved.
- Storage outages do not silently disable limiter enforcement or leak credentials.
- Deployment verification proves shared counters, reload persistence, Redis loopback binding, and unchanged production WSGI security gates.
- Documentation identifies shared limiter storage as a mandatory production runtime dependency.
