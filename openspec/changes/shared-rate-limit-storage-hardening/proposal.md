## Why

Phase 6 production WSGI hardening moves the backend to multiple Gunicorn workers. The current Flask-Limiter setup uses the default in-memory store, so each worker maintains independent counters and graceful reloads reset enforcement state.

This weakens authentication and mutation throttles exactly where production now needs shared, durable-enough enforcement across workers and reloads.

## What Changes

- Configure Flask-Limiter with a production shared storage backend instead of per-process memory.
- Use Redis only for rate-limit counters, with no caching, sessions, queues, SOAR state, or application data.
- Require production startup/readiness validation for the limiter storage URI and connectivity.
- Preserve all existing route decorators, rate-limit values, key function behavior, and JSON 429 response contract.
- Fail closed in production when shared limiter storage is unavailable instead of silently falling back to memory.
- Keep local development and tests able to use memory storage intentionally.
- Extend deployment verification so Gunicorn multi-worker rate limits are proven shared and survive graceful reload.
- Update active runtime and source-of-truth documentation to include limiter storage as a production dependency.

## Capabilities

### New Capabilities

- `shared-rate-limit-storage`: Defines the production contract for shared Flask-Limiter storage, validation, outage behavior, deployment verification, and documentation.

### Modified Capabilities

- None.

## Impact

- Affected code: `core/extensions.py`, `siem_backend.py`, production runtime validation scripts, backend deployment helper tests, and focused Flask-Limiter tests.
- Dependencies: add the Redis Python client required by Flask-Limiter storage support; VM runtime must provide a loopback-only Redis service for limiter counters.
- Configuration: add secret-safe `SIEM_RATE_LIMIT_STORAGE_URI`, defaulting to memory only for local development and tests.
- Deployment: validate Redis availability before restarting Gunicorn, verify shared counters across Gunicorn workers, and include rollback steps.
- Documentation: update `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, `docs/production_wsgi_runtime.md`, and active verification/deployment runbooks where backend production gates are listed.
