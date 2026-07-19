## 1. Audit And Preflight

- [x] 1.1 Re-read `AGENTS.md` and `docs/mac-vm-source-of-truth-policy.md` before implementation.
- [x] 1.2 Re-confirm current backend startup paths in `siem_backend.py`, `scripts/deploy_backend_vm.sh`, deploy/systemd units, and active deployment docs.
- [x] 1.3 Confirm whether Gunicorn is already declared in runtime dependencies; add it only if missing.
- [x] 1.4 Identify stale docs that still describe VM merge, direct Flask production serving, or backend restart without Gunicorn verification.

## 2. Gunicorn Backend Runtime

- [x] 2.1 Add `deploy/systemd/siem-backend.service` with Gunicorn `siem_backend:app`, sync worker class, loopback bind, default 2 workers, 120 second timeout, 30 second graceful timeout, journald logging, restart policy, and graceful reload.
- [x] 2.2 Add `scripts/validate_backend_runtime_env.sh` to fail closed for `SIEM_DEBUG=true`, non-loopback `SIEM_BIND_HOST`, missing Gunicorn, missing secret/admin/database settings, or unsafe production defaults without printing secrets.
- [x] 2.3 Add `scripts/install_siem_backend_service.sh` with `--dry-run`, install/update, `--enable`, `--start`, `--reload`, and `--rollback` behavior following existing service-helper patterns.
- [x] 2.4 Keep Flask `app.run()` local-development-only and ensure no production unit or deploy helper calls it.

## 3. Deployment Script Hardening

- [x] 3.1 Update `scripts/deploy_backend_vm.sh` preflight to verify Gunicorn availability and print sanitized Gunicorn/runtime settings.
- [x] 3.2 Update normal deployment order to run migration dry-run, apply migrations, install/update backend unit, restart backend, verify backend health/security gates, then install/restart worker units.
- [x] 3.3 Add post-restart checks for `systemctl cat`, Gunicorn command evidence, absence of Flask development-server command lines, loopback bind, `/health`, debugger absence, and secure-cookie effective config where locally checkable.
- [x] 3.4 Ensure `--dry-run-migrations`, `--skip-restart`, and `--skip-health-check` semantics remain explicit and safe.
- [x] 3.5 Ensure deployment failure before backend verification prevents worker restarts.

## 4. Documentation Updates

- [x] 4.1 Update `AGENTS.md` with a concise production WSGI safeguard.
- [x] 4.2 Update `docs/mac-vm-source-of-truth-policy.md` backend deployment matrix and completion evidence for Gunicorn/systemd/security gates.
- [x] 4.3 Add `docs/production_wsgi_runtime.md` covering architecture, env vars, install, reload, restart, logs, health, security checks, rollback, and troubleshooting.
- [x] 4.4 Update `docs/schema_migration_workflow.md`, `docs/soar_handoff.md`, `docs/soar_worker_deployment_checklist.md`, `docs/pfsense_deployment_runtime_readiness.md`, `docs/verification-checklist.md`, and `docs/behavior-checks.md` with precise Gunicorn/backend-service corrections.
- [x] 4.5 Review `deploy.sh` and either mark it legacy/example-only or align its text with the documented Mac build to VM rsync policy.

## 5. Automated Verification

- [x] 5.1 Add tests for `deploy/systemd/siem-backend.service` ExecStart, environment loading, loopback bind, Gunicorn target, restart policy, logging, and absence of Flask development-server startup.
- [x] 5.2 Add tests for `scripts/validate_backend_runtime_env.sh` success and fail-closed cases without secret leakage.
- [x] 5.3 Add tests for `scripts/install_siem_backend_service.sh` dry-run, install, start/reload, rollback, and effective unit verification commands.
- [x] 5.4 Update `tests/test_deploy_backend_vm_script.py` for migration-before-restart order, backend unit install before restart, worker restarts after backend security verification, bounded health retry, and redaction.
- [x] 5.5 Run focused backend runtime/deployment tests and existing affected backend smoke tests for health, auth, AI route importability, SOAR route importability, and migration helper behavior.

## 6. VM Rollout Verification Plan

- [x] 6.1 Document VM preflight: clean tree, approved commit, prior backend unit capture, current service status, current health, current listening sockets, and rollback SHA.
- [x] 6.2 Document deployment verification: Gunicorn master/workers, `siem_backend:app`, `/health`, loopback-only backend bind, nginx public path, raw `5051` unreachable, debugger absent, secure cookies.
- [x] 6.3 Document compatibility smoke: authenticated login, AI routes including a bounded long AI request, SOAR metrics/approval/playbook/dead-letter routes, PostgreSQL migration ledger, bank app, honeypot, and frontend static serving.
- [x] 6.4 Document graceful reload test with `systemctl reload siem-backend.service` or `kill -HUP` through systemd and verify no health interruption beyond the bounded retry window.
- [x] 6.5 Document rollback test or dry-run rollback evidence using the helper and prior unit/commit restoration procedure.

## 7. Final Validation And Handoff

- [x] 7.1 Run `python3 -m py_compile` for changed Python modules/scripts where applicable.
- [x] 7.2 Run focused pytest suites for deployment scripts, runtime validation, and affected backend smoke tests.
- [x] 7.3 Run `git diff --check`.
- [x] 7.4 Run `openspec validate production-wsgi-hardening --strict`.
- [x] 7.5 Prepare a VM handoff that states no implementation deployment occurred on the Mac and that VM sync is required after implementation.

## Implementation Verification Evidence

- `bash -n scripts/validate_backend_runtime_env.sh && bash -n scripts/install_siem_backend_service.sh && bash -n scripts/deploy_backend_vm.sh && bash -n deploy.sh` passed.
- `python3 -m py_compile siem_backend.py scripts/pfsense_deployment_readiness_check.py tests/test_production_wsgi_hardening.py tests/test_deploy_backend_vm_script.py tests/test_pfsense_deployment_runtime_readiness.py` passed.
- `.venv/bin/python -m pytest tests/test_production_wsgi_hardening.py tests/test_deploy_backend_vm_script.py tests/test_pfsense_deployment_runtime_readiness.py tests/test_auth_rbac.py tests/test_ai_gateway_foundation.py tests/test_ai_explainer_and_chat.py tests/test_ai_drafting_assistant.py tests/test_ai_advanced_soc_assistance.py tests/test_playbook_routes.py tests/test_playbook_metrics_routes.py tests/test_approval_routes.py tests/test_dead_letter_routes.py tests/test_incident_routes.py` passed with 148 passed, 176 skipped, and 1 existing Flask-Limiter in-memory warning.
- `git diff --check` passed.
- `openspec validate production-wsgi-hardening --strict` passed.
- No VM deployment or live runtime verification was performed during implementation; VM rollout verification is documented for the later authorized sync.

## Scope Exclusions

- No Docker, Kubernetes, Redis, Celery, async rewrite, load balancer change, nginx redesign, database migration, provider configuration change, SOAR behavior change, bank app change, honeypot change, firewall/NSG change, VM access, commit, push, or deployment during spec creation.

## VM Sync Required After Implementation

Yes. Implementation changes backend runtime files, deployment scripts, and documentation. Production rollout requires a later explicit commit/push authorization and VM deployment approval.
