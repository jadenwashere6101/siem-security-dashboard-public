## Why

The recent production runtime audit found that the SIEM backend is still started through Flask's development-server entrypoint in production. That leaves production safety dependent on environment flags and runtime discipline instead of a durable WSGI architecture.

## What Changes

- Introduce a source-controlled production WSGI runtime for the SIEM backend using Gunicorn in front of the existing `siem_backend:app` object.
- Add a repo-owned `siem-backend.service` systemd unit and install/update/rollback workflow so production no longer depends on an undocumented VM-local unit.
- Update backend deployment scripts to install and verify the backend unit, restart Gunicorn safely, and run explicit post-restart health and security checks.
- Add production runtime validation for `SIEM_DEBUG=false`, `SIEM_BIND_HOST=127.0.0.1`, secure session cookies, debugger absence, raw backend port isolation, nginx-only public exposure, and Gunicorn process evidence.
- Preserve the existing Flask app factory/module-level app compatibility, frontend static serving, nginx proxy topology, PostgreSQL access, AI routes, SOAR workers, bank app, honeypot, and deployment workflow boundaries.
- Update deployment and operations documentation to make Gunicorn the only supported production backend runtime and Flask `app.run()` local-development-only.

## Capabilities

### New Capabilities

- `production-wsgi-hardening`: Production backend runtime hardening for Gunicorn, systemd, deployment scripts, runtime configuration, security gates, rollout, rollback, and verification.

### Modified Capabilities

- None. This change introduces a deployment/runtime capability without changing application API behavior.

## Impact

- Expected implementation files: `deploy/systemd/siem-backend.service`, a backend service install/rollback helper under `scripts/`, `scripts/deploy_backend_vm.sh`, deployment tests, and requirements/dependency metadata if Gunicorn is not already declared.
- Expected documentation files: `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, backend/deployment runbooks, SOAR handoff/deployment docs, pfSense deployment readiness docs, schema migration workflow docs, and verification/security checklists.
- No database migration, frontend behavior change, nginx redesign, provider configuration change, SOAR redesign, bank app change, or honeypot change is required.
- Implementation will require a later VM sync/deployment because production runtime behavior and systemd units change. This spec creation phase does not require VM access or deployment.
