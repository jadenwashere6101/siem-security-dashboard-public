## 1. Audit And Preflight

- [x] 1.1 Re-read `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, and the production WSGI hardening OpenSpec before implementation.
- [x] 1.2 Re-confirm current Flask-Limiter initialization in `core/extensions.py` and `siem_backend.py`.
- [x] 1.3 Re-confirm all current `@limiter.limit(...)` decorators and verify no route policy changes are required.
- [x] 1.4 Re-confirm Redis is not already an active production dependency and that this change uses it only for Flask-Limiter counters.

## 2. Limiter Configuration

- [x] 2.1 Add a small limiter storage configuration helper that resolves `SIEM_RATE_LIMIT_STORAGE_URI` before `limiter.init_app(app)`.
- [x] 2.2 Configure Flask-Limiter to use Redis storage in production and memory storage only for local development/tests.
- [x] 2.3 Preserve `get_remote_address`, existing route decorators, default limits, and the existing JSON 429 handler.
- [x] 2.4 Add a sanitized fail-closed handler for production limiter storage failures without exposing URI credentials.

## 3. Runtime Validation And Dependencies

- [x] 3.1 Add the Redis Python client dependency required by Flask-Limiter storage support.
- [x] 3.2 Extend `scripts/validate_backend_runtime_env.sh` to require and validate `SIEM_RATE_LIMIT_STORAGE_URI` in production.
- [x] 3.3 Validate production URI scheme, loopback host, optional port/database parsing, and reject `memory://`.
- [x] 3.4 Validate Redis connectivity with the project venv dependency before Gunicorn starts.
- [x] 3.5 Ensure validation output and errors redact passwords, tokens, query strings, cookies, and full URIs.

## 4. Deployment And Documentation

- [x] 4.1 Update `scripts/deploy_backend_vm.sh` preflight and security-gate output to include sanitized limiter storage state and connectivity.
- [x] 4.2 Keep deployment helper behavior scoped: no Redis package installation, firewall changes, nginx redesign, database schema changes, or provider changes.
- [x] 4.3 Update `AGENTS.md` with a concise production safeguard against in-memory limiter storage under Gunicorn.
- [x] 4.4 Update `docs/mac-vm-source-of-truth-policy.md` and `docs/production_wsgi_runtime.md` with limiter storage runtime, rollout, rollback, and completion evidence.
- [x] 4.5 Update active verification/deployment runbooks where backend production gates are listed.

## 5. Automated Verification

- [x] 5.1 Add tests for limiter storage config resolution: production Redis, local memory, missing URI, `memory://`, unsafe scheme, public host, and redaction.
- [x] 5.2 Add tests proving limiter config is applied before `limiter.init_app(app)` and default route limits are unchanged.
- [x] 5.3 Add focused auth/rate-limit tests proving `POST /login` still returns the existing 429 JSON body when exceeded.
- [x] 5.4 Add focused failure tests proving production storage outages fail closed with sanitized 503 behavior and no credential leakage.
- [x] 5.5 Update deployment script tests for limiter validation ordering, sanitized preflight output, and no worker restart before backend security/limiter verification.

## 6. VM Rollout Verification Plan

- [x] 6.1 Document VM preflight for Redis service status, loopback listening socket, configured `SIEM_RATE_LIMIT_STORAGE_URI` presence, and approved commit.
- [x] 6.2 Document Gunicorn multi-worker verification proving login counters are shared across workers.
- [x] 6.3 Document graceful reload verification proving counters survive `systemctl reload siem-backend.service` until TTL expiry.
- [x] 6.4 Document Redis outage verification proving approved fail-closed behavior without credential leakage.
- [x] 6.5 Document regression smoke for auth, normal routes, AI, SOAR, PostgreSQL, bank app, honeypot, nginx, and production WSGI security gates.

## 7. Final Validation And Handoff

- [x] 7.1 Run `bash -n scripts/validate_backend_runtime_env.sh` and `bash -n scripts/deploy_backend_vm.sh`.
- [x] 7.2 Run `python3 -m py_compile` for new and modified Python modules.
- [x] 7.3 Run focused pytest suites for limiter config, auth limits, deployment scripts, and production WSGI hardening.
- [x] 7.4 Run `git diff --check`.
- [x] 7.5 Run `openspec validate shared-rate-limit-storage-hardening --strict`.
- [x] 7.6 Prepare a VM handoff stating that no VM deployment occurred and VM sync is required after implementation.

## Scope Exclusions

- No authentication redesign, route-limit value redesign, nginx redesign, Gunicorn worker redesign, database-backed limiter tables, Redis queues, caching, session migration, SOAR queue migration, Celery/RQ, firewall/NSG automation, VM access, commit, push, or deployment during implementation.

## VM Sync Required After Implementation

Yes. Implementation changes backend runtime configuration, dependencies, deployment validation, and production documentation. Production rollout requires a later explicit commit/push authorization and VM deployment approval.

## Implementation Verification Evidence

- `bash -n scripts/validate_backend_runtime_env.sh && bash -n scripts/deploy_backend_vm.sh` passed.
- `python3 -m py_compile core/rate_limit_config.py core/extensions.py siem_backend.py tests/test_rate_limit_storage_config.py tests/test_production_wsgi_hardening.py tests/test_deploy_backend_vm_script.py` passed.
- `.venv/bin/python -m pytest tests/test_rate_limit_storage_config.py tests/test_production_wsgi_hardening.py tests/test_deploy_backend_vm_script.py tests/test_auth_rbac.py` passed with 59 passed.
- `git diff --check` passed.
- `openspec validate shared-rate-limit-storage-hardening --strict` passed.
- Automated tests cover production Redis URI resolution, local memory-only behavior, rejection of missing/memory/unsafe/public storage, redaction, fail-closed storage outage handling, unchanged login 429 response, and deployment validation ordering.
- Live Gunicorn multi-worker shared-counter and graceful-reload persistence checks were not run because this implementation phase did not access or deploy the VM; those checks are documented as required VM rollout verification.
