## ADDED Requirements

### Requirement: Production backend uses Gunicorn WSGI only
The system SHALL run production SIEM backend traffic through Gunicorn serving the existing Flask WSGI app object and SHALL NOT run production traffic through Flask's development server.

#### Scenario: Gunicorn serves production traffic
- **WHEN** `siem-backend.service` is started in production
- **THEN** the effective process command uses Gunicorn with WSGI target `siem_backend:app`

#### Scenario: Flask development server is absent from production startup
- **WHEN** the effective production backend unit is inspected
- **THEN** it does not invoke `python siem_backend.py`, `flask run`, `app.run`, or Werkzeug development-server startup

#### Scenario: Existing app shell remains compatible
- **WHEN** Gunicorn imports `siem_backend:app`
- **THEN** the existing Flask app factory, module-level app, route registration, `/health`, and frontend static serving continue to work

### Requirement: Backend systemd unit is source-controlled and hardened
The system SHALL provide a repository-owned `siem-backend.service` unit that runs the backend as the `jaden` user, loads the VM `.env`, starts Gunicorn with bounded workers and timeouts, captures logs in journald, and supports graceful reload and shutdown.

#### Scenario: Unit has production Gunicorn ExecStart
- **WHEN** the repository backend service unit is reviewed
- **THEN** `ExecStart` runs `/home/jaden/siem-security-dashboard/venv/bin/gunicorn` with `siem_backend:app`, sync workers, loopback bind, access/error logs to stdout/stderr, and capture-output enabled

#### Scenario: Unit uses safe restart and signal behavior
- **WHEN** the backend service is stopped, restarted, or reloaded
- **THEN** systemd uses `SIGTERM` for shutdown, `HUP` for graceful reload, bounded stop timeout, `Restart=on-failure`, and no PID file requirement

#### Scenario: Unit loads environment without printing secrets
- **WHEN** the backend service starts
- **THEN** it loads `/home/jaden/siem-security-dashboard/.env` and startup validation reports only sanitized presence/effective-state information

### Requirement: Production runtime configuration fails closed
The system SHALL validate mandatory production runtime settings before starting Gunicorn and SHALL fail startup when unsafe values are present.

#### Scenario: Debug mode is rejected
- **WHEN** production startup validation sees `SIEM_DEBUG=true`
- **THEN** startup fails before Gunicorn serves traffic

#### Scenario: Public backend bind is rejected
- **WHEN** production startup validation sees `SIEM_BIND_HOST` unset to a public bind value such as `0.0.0.0`
- **THEN** startup fails before Gunicorn serves traffic

#### Scenario: Required secrets and database settings are present
- **WHEN** production startup validation runs
- **THEN** it requires a secret key, admin credentials, and either `DATABASE_URL` or complete database environment settings without printing secret values

#### Scenario: Secure cookies are effective
- **WHEN** the backend runs with production configuration
- **THEN** Flask session cookies are configured with `Secure`, `HttpOnly`, and `SameSite=Lax`

### Requirement: Deployment helper installs and verifies the backend WSGI unit
The system SHALL update the VM backend deployment helper to install the source-controlled backend service unit, restart through systemd, verify Gunicorn health and security gates, and only then proceed to dependent worker restarts.

#### Scenario: Migration order is preserved
- **WHEN** `scripts/deploy_backend_vm.sh` runs a normal backend deployment
- **THEN** it runs migration dry-run and migration apply before backend restart

#### Scenario: Backend unit is installed before restart
- **WHEN** backend deployment reaches the restart step
- **THEN** the helper copies the repository `siem-backend.service`, reloads systemd, and restarts `siem-backend.service`

#### Scenario: Worker restarts wait for backend verification
- **WHEN** backend health or production security verification fails
- **THEN** the helper stops before restarting SOAR worker services or timers

#### Scenario: Deployment output is sanitized
- **WHEN** deployment preflight and verification output is printed
- **THEN** it includes service/runtime state and redacts database passwords, secret keys, API keys, cookies, and provider credentials

### Requirement: Production security gates are verified after deployment
Every production backend deployment SHALL explicitly verify debug mode, bind address, debugger absence, raw backend port isolation, secure cookies, nginx-only public exposure, and Gunicorn process evidence.

#### Scenario: Loopback backend bind is verified
- **WHEN** deployment verification inspects listening sockets
- **THEN** the SIEM backend is listening only on `127.0.0.1:${SIEM_PORT}`

#### Scenario: Raw backend port is not public
- **WHEN** the public VM address is probed on the backend port
- **THEN** the connection is refused, timed out, or otherwise unreachable from outside the VM

#### Scenario: Debugger middleware is absent
- **WHEN** Werkzeug debugger probe URLs are requested
- **THEN** responses do not contain debugger console, Werkzeug debugger, or interactive traceback signatures

#### Scenario: nginx is the public HTTP entrypoint
- **WHEN** public SIEM HTTP or HTTPS traffic is checked
- **THEN** the public response is served through nginx and proxied to the loopback Gunicorn backend rather than exposing Gunicorn directly

### Requirement: Production behavior remains compatible with existing SIEM workflows
The WSGI migration SHALL preserve existing backend behavior for health, authentication, AI routes, SOAR workflows, PostgreSQL-backed routes, frontend static serving, bank app integration, and honeypot integration.

#### Scenario: Health endpoint remains available
- **WHEN** Gunicorn is serving the backend
- **THEN** `GET /health` on loopback returns a successful SIEM health response

#### Scenario: Authentication remains functional
- **WHEN** a user accesses login-protected SIEM routes through nginx
- **THEN** existing authentication, session, RBAC, and secure-cookie behavior remains intact

#### Scenario: AI routes remain functional
- **WHEN** focused AI route smoke tests run through the production backend
- **THEN** existing AI explain/chat/draft/investigation routes respond according to their configured provider mode without Gunicorn timeouts breaking bounded requests

#### Scenario: SOAR remains functional
- **WHEN** SOAR metrics, approval, playbook, dead-letter, and worker health routes are checked
- **THEN** they behave as before and no production action is executed by the deployment verification itself

#### Scenario: Adjacent services are unaffected
- **WHEN** deployment verification checks bank app and honeypot availability
- **THEN** their public/listening behavior remains unchanged by the SIEM backend WSGI migration

### Requirement: Rollback restores prior backend runtime safely
The system SHALL define and support rollback from the Gunicorn backend service change without modifying unrelated infrastructure or data.

#### Scenario: Pre-restart validation failure leaves current service running
- **WHEN** the new backend unit or runtime validation fails before restart
- **THEN** deployment stops and the current running backend is not replaced

#### Scenario: Post-restart failure restores prior authorized runtime
- **WHEN** Gunicorn restart fails health or security verification
- **THEN** operators restore the prior authorized commit and prior backend unit, reload systemd, restart `siem-backend.service`, and recheck health

#### Scenario: Rollback avoids unrelated mutation
- **WHEN** backend runtime rollback is performed
- **THEN** it does not alter nginx, database rows, migrations, bank app, honeypot, provider configuration, VM firewall, or Azure NSG rules unless separately authorized

### Requirement: Documentation identifies Gunicorn as the production contract
The system SHALL update active deployment and operations documentation so production backend startup is documented as Gunicorn under systemd and Flask development-server startup is documented as local-development-only.

#### Scenario: Source-of-truth policy is updated
- **WHEN** implementation documentation is reviewed
- **THEN** `docs/mac-vm-source-of-truth-policy.md` includes Gunicorn backend deployment and security-gate evidence in the backend deployment workflow

#### Scenario: Active runbooks are corrected
- **WHEN** active backend, SOAR, pfSense, schema migration, and verification runbooks reference backend restart or health checks
- **THEN** they point to the source-controlled Gunicorn service workflow and remove stale production Flask-development-server assumptions

#### Scenario: AGENTS safeguard is updated
- **WHEN** future agents read `AGENTS.md`
- **THEN** they see that production backend deployments must use the documented Gunicorn/systemd path and must not use Flask's development server in production
