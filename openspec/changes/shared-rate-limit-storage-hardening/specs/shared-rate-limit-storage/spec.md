## ADDED Requirements

### Requirement: Production rate limits use shared storage
The system SHALL use a shared Redis-compatible storage backend for Flask-Limiter in production so rate-limit counters are consistent across Gunicorn workers and graceful reloads.

#### Scenario: Production limiter storage is Redis
- **WHEN** the backend starts with `SIEM_DEBUG=false`
- **THEN** Flask-Limiter is configured with `SIEM_RATE_LIMIT_STORAGE_URI` using a `redis://` or `rediss://` backend

#### Scenario: Gunicorn workers share counters
- **WHEN** requests for the same client key are served by different Gunicorn workers
- **THEN** the same rate-limit counter is consumed rather than separate per-worker memory counters

#### Scenario: Graceful reload preserves active counters
- **WHEN** `siem-backend.service` is gracefully reloaded before a rate-limit window expires
- **THEN** existing limiter counters remain effective until their configured TTL expires

### Requirement: Local development can use memory storage intentionally
The system SHALL allow in-memory Flask-Limiter storage only for local development and tests, never for production.

#### Scenario: Local debug mode omits shared storage
- **WHEN** the backend starts with `SIEM_DEBUG=true` and no `SIEM_RATE_LIMIT_STORAGE_URI`
- **THEN** the limiter may use memory storage without blocking startup

#### Scenario: Production rejects memory storage
- **WHEN** production runtime validation sees `SIEM_RATE_LIMIT_STORAGE_URI=memory://`
- **THEN** validation fails before Gunicorn serves production traffic

### Requirement: Limiter storage configuration is secret-safe
The system SHALL treat the limiter storage URI as secret-sensitive and SHALL NOT print credentials, tokens, query parameters, cookies, or full connection strings in logs, validation output, deployment output, tests, or error responses.

#### Scenario: Sanitized startup output
- **WHEN** production startup validation reports limiter storage state
- **THEN** it prints only the backend type and non-secret host, port, and database information

#### Scenario: Sanitized validation failure
- **WHEN** limiter storage validation fails for a URI containing credentials
- **THEN** the failure message does not include the password, full URI, query string, cookies, or request body

### Requirement: Production startup validates limiter storage
The system SHALL validate limiter storage configuration and connectivity before Gunicorn starts in production.

#### Scenario: Missing production storage is rejected
- **WHEN** production startup validation runs without `SIEM_RATE_LIMIT_STORAGE_URI`
- **THEN** validation fails before Gunicorn serves traffic

#### Scenario: Unsafe storage host is rejected
- **WHEN** production startup validation sees a Redis URI using a public or non-loopback host
- **THEN** validation fails unless a later approved infrastructure change explicitly documents that host

#### Scenario: Unreachable Redis is rejected
- **WHEN** production startup validation cannot connect to the configured Redis limiter storage
- **THEN** validation fails before Gunicorn serves traffic

#### Scenario: Missing Redis client is rejected
- **WHEN** the configured limiter storage requires the Redis Python client and the dependency is unavailable
- **THEN** validation fails before Gunicorn serves traffic

### Requirement: Limiter failures fail closed in production
The system SHALL fail closed for limiter-protected routes when shared limiter storage is unavailable at runtime and SHALL NOT silently disable rate limiting or fall back to per-process memory storage in production.

#### Scenario: Exceeded limits preserve existing response contract
- **WHEN** a request exceeds an existing Flask-Limiter policy
- **THEN** the response remains HTTP 429 with `{"error": "rate_limited", "message": "Too many requests. Please try again later."}`

#### Scenario: Storage outage returns sanitized failure
- **WHEN** a limiter-protected request cannot check shared storage because Redis is unavailable
- **THEN** the response is a sanitized fail-closed HTTP 503 and no credential or URI value is exposed

#### Scenario: Unprotected normal routes are not newly throttled
- **WHEN** a route has no default limit and no route-level limiter decorator
- **THEN** the shared storage change does not add a new rate limit to that route

### Requirement: Existing rate-limit policies are preserved
The system SHALL preserve the current route-level Flask-Limiter policies, client keying behavior, authentication behavior, and application response contracts except for the explicit production storage-outage failure response.

#### Scenario: Login limit remains unchanged
- **WHEN** repeated `POST /login` attempts are made from the same client key
- **THEN** the existing `5 per minute` limit applies

#### Scenario: Admin and mutation limits remain unchanged
- **WHEN** protected admin, alert mutation, and ingest endpoints are requested
- **THEN** their existing route-level limiter values remain unchanged

#### Scenario: Key function remains remote address based
- **WHEN** Flask-Limiter determines the client key
- **THEN** it continues to use the existing `get_remote_address` behavior behind the configured proxy handling

### Requirement: Deployment verifies shared limiter storage
The backend deployment workflow SHALL verify limiter storage readiness, shared counter behavior, graceful reload persistence, and unchanged production WSGI security gates before declaring rollout complete.

#### Scenario: Deploy helper reports sanitized limiter state
- **WHEN** `scripts/deploy_backend_vm.sh` runs production preflight and post-restart checks
- **THEN** it reports sanitized limiter storage configuration and connectivity without printing secrets

#### Scenario: Worker consistency is verified
- **WHEN** VM rollout verification runs against at least two Gunicorn workers
- **THEN** repeated login attempts from one client are limited consistently across worker handling

#### Scenario: Reload persistence is verified
- **WHEN** rollout verification triggers a graceful backend reload during an active rate-limit window
- **THEN** the limiter counter remains active after reload

#### Scenario: WSGI security gates remain true
- **WHEN** limiter storage deployment verification completes
- **THEN** `SIEM_DEBUG=false`, loopback-only backend binding, debugger absence, raw backend port isolation, secure session cookies, and Gunicorn production serving are still verified

### Requirement: Documentation defines limiter storage as a production dependency
The system SHALL document shared limiter storage as part of the production runtime contract and SHALL distinguish it from unrelated Redis uses.

#### Scenario: Source-of-truth policy is updated
- **WHEN** implementation documentation is reviewed
- **THEN** `docs/mac-vm-source-of-truth-policy.md` identifies shared limiter storage as a required production backend runtime dependency after this change

#### Scenario: Runtime runbook is updated
- **WHEN** production runtime documentation is reviewed
- **THEN** it describes `SIEM_RATE_LIMIT_STORAGE_URI`, startup validation, outage behavior, verification, and rollback

#### Scenario: Redis scope is constrained
- **WHEN** documentation describes Redis
- **THEN** it states Redis is used only for Flask-Limiter counters and not for sessions, caches, queues, SOAR execution, or application data
