## 1. Overall Goal

Track the full pfSense firewall log ingestion integration from audit through production readiness without implementing code, changing application source files, creating child specs, committing, or pushing.

This is a coordination-only parent roadmap. It may track non-repo operational tasks that happen outside the Mac repo, including Azure NSG changes, VM firewall checks, uncle/pfSense configuration, deployment verification, and runtime validation.

## 2. Hard Guardrails

- [ ] 2.1 Confirm Mac repo is the source of truth for specs, code, tests, commits, and pushes.
- [ ] 2.2 Confirm Azure VM is deployment/runtime only.
- [ ] 2.3 Confirm no source code edits happen on the VM unless explicitly labeled VM emergency hotfix.
- [ ] 2.4 Confirm every runtime-affecting feature has a deployment plan before implementation.
- [ ] 2.5 Confirm no port opening happens until security review is complete.
- [ ] 2.6 Confirm no uncle/pfSense configuration request happens until our side is fully deployed and tested.
- [ ] 2.7 Confirm no implementation starts until Phase 0 and Phase 1 audits are complete.
- [ ] 2.8 Confirm no production/live log collection starts until runtime validation passes.

## 3. Phase 0 - Read-only Environment Audit

- [x] 3.1 Check Mac repo clean.
  - 2026-07-07 finding: not clean because roadmap/policy files are uncommitted; no application source files are dirty from this audit.
- [x] 3.2 Check GitHub up to date.
  - 2026-07-07 finding: Mac `HEAD`, local `origin/main`, and remote `origin/main` all resolve to `af24fae54ad1a1c91e7e62c2d52921793fe42321`.
- [x] 3.3 Check VM repo synced and clean.
  - 2026-07-07 finding: VM working tree is clean, but VM Git history is not synced with GitHub `main`. VM `HEAD` is `489e4ed4be2789e82709af77ccce84c6da930d45`; current remote `origin/main` is `af24fae54ad1a1c91e7e62c2d52921793fe42321`. Do not merge/deploy until this divergence is intentionally handled.
- [x] 3.4 Check backend health.
  - 2026-07-07 finding: `curl http://127.0.0.1:5051/health` returned HTTP 200 with `status=ok`.
- [x] 3.5 Check `soar-playbook-worker.service`.
  - 2026-07-07 finding: active/running.
- [x] 3.6 Check `soar-response-action-worker.timer/service`.
  - 2026-07-07 finding: timer active/waiting; one-shot service inactive/dead after last successful run, which matches timer-triggered service behavior.
- [x] 3.7 Check current open/listening ports.
  - 2026-07-07 finding: listening ports observed include TCP 22, 80, 443, 5051, 5052, 8080, local PostgreSQL 5432, local MySQL 3306/33060, local DNS 53, DHCP UDP 68, and chrony UDP 323.
- [x] 3.8 Check whether UDP 514 conflicts with anything.
  - 2026-07-07 finding: no UDP 514 listener found.
- [x] 3.9 Check whether any syslog listener already exists.
  - 2026-07-07 finding: `rsyslogd` process exists for host logging, but no UDP 514 socket is listening.
- [x] 3.10 Check existing adapters/listeners.
  - 2026-07-07 finding: active ingestion adapters are request/normalizer based (`adapters/nginx_adapter.py`, `adapters/azure_insights_adapter.py`, `adapters/otel_adapter.py`) and feed Flask ingest routes; no existing raw UDP/syslog listener was found.
- [x] 3.11 Check honeypot listener/deployment patterns.
  - 2026-07-07 finding: honeypot is a separate runtime service on TCP 8080 that posts normalized events to `/ingest/honeypot`; backend stores `source=honeypot` and `source_type=honeypot`.
- [x] 3.12 Check existing normalization helpers.
  - 2026-07-07 finding: reusable pieces include `engines/ingest_engine.ingest_normalized_event`, `helpers/ingest_normalizers`, and the narrow adapter normalizers for nginx/Azure/OTEL.
- [x] 3.13 Check existing detection rules overlapping firewall behavior.
  - 2026-07-07 finding: overlapping detections include `port_scan`, `failed_login`/`unauthorized_access`, `http_error`, scanner/admin/env probe honeypot detections, correlated activity, and targeted correlation.
- [x] 3.14 Check existing tests that can be reused.
  - 2026-07-07 finding: reusable tests/patterns include `tests/test_ingest_api_contracts.py`, `tests/test_ingest_normalized_event.py`, `tests/test_port_scan_detection.py`, `tests/test_honeypot_ingest_adapter.py`, `tests/test_honeypot_event_detections.py`, `tests/test_correlated_activity.py`, `tests/test_targeted_correlation.py`, `tests/test_deploy_backend_vm_script.py`, and `tests/test_response_action_worker_deployment.py`.

## 4. Phase 1 - Architecture Audit

- [ ] 4.1 Decide where listener should live.
- [ ] 4.2 Decide daemon vs one-shot service.
- [ ] 4.3 Decide POST-to-Flask vs direct ingest pattern.
- [ ] 4.4 Audit reusable systemd patterns.
- [ ] 4.5 Audit reusable adapter utilities.
- [ ] 4.6 Audit parser/sanitization helpers.
- [ ] 4.7 Audit validation and normalization functions.
- [ ] 4.8 Define exact ingestion flow.

## 5. Phase 2 - Security Review

- [ ] 5.1 Create Azure NSG rule plan.
- [ ] 5.2 Create VM firewall rule plan.
- [ ] 5.3 Make UDP exposure decision.
- [ ] 5.4 Define source IP allow-list.
- [ ] 5.5 Define expected pfSense public IP handling.
- [ ] 5.6 Define packet size limit.
- [ ] 5.7 Define malformed syslog handling.
- [ ] 5.8 Define malformed UTF-8 handling.
- [ ] 5.9 Define control-character stripping.
- [ ] 5.10 Define rate limiting.
- [ ] 5.11 Review spoofing/replay considerations.
- [ ] 5.12 Define logging/monitoring.
- [ ] 5.13 Complete DoS/storage-risk review.
- [ ] 5.14 Complete data retention and privacy review.
- [ ] 5.15 Confirm what to tell uncle about where logs are stored.

## 6. Phase 3 - Detailed OpenSpec Creation

- [ ] 6.1 Create actual child implementation specs only after Phase 0 and Phase 1 audits are complete.
- [ ] 6.2 Ensure listener flow documents:
  - listener
  - validate source IP
  - validate packet length
  - strip control characters
  - reject malformed syslog
  - parse pfSense filterlog
  - normalize
  - validate schema
  - ingest
  - detection engine
  - SOAR/playbooks
- [ ] 6.3 Include explicit acceptance criteria in each child spec.
- [ ] 6.4 Include explicit validation plan in each child spec.
- [ ] 6.5 Confirm child specs do not skip security/deployment prerequisites.

## 7. Phase 4 - Milestone Implementation Plan

Track child specs/milestones separately. Each milestone must stop for validation before moving forward.

- [ ] 7.1 Listener only.
- [ ] 7.2 Parser only.
- [ ] 7.3 Adapter/route only.
- [ ] 7.4 Event types only.
- [ ] 7.5 Detection rules only.
- [ ] 7.6 Deployment/service setup only.
- [ ] 7.7 Confirm each milestone has its own validation stop before the next milestone starts.

## 8. Phase 5 - Deployment Checklist

- [ ] 8.1 Commit.
- [ ] 8.2 Push.
- [ ] 8.3 VM clean status check.
- [ ] 8.4 VM fetch/merge.
- [ ] 8.5 Verify requirements.
- [ ] 8.6 Verify migrations.
- [ ] 8.7 Apply migrations if needed.
- [ ] 8.8 Restart backend if needed.
- [ ] 8.9 Restart workers if needed.
- [ ] 8.10 Verify health endpoint.
- [ ] 8.11 Verify workers.
- [ ] 8.12 Verify logs.
- [ ] 8.13 Verify dashboard.
- [ ] 8.14 Verify API.
- [ ] 8.15 Confirm VM clean after deployment.

## 9. Phase 6 - Runtime Validation

- [ ] 9.1 Inject realistic fake pfSense syslog lines.
- [ ] 9.2 Confirm UDP listener receives packet.
- [ ] 9.3 Confirm parser extracts action/interface/protocol/source IP/destination IP/destination port/direction.
- [ ] 9.4 Confirm normalized event inserted.
- [ ] 9.5 Confirm dashboard shows `source=pfsense`.
- [ ] 9.6 Confirm detection rules fire where expected.
- [ ] 9.7 Confirm playbook execution if applicable.
- [ ] 9.8 Test malformed input.
- [ ] 9.9 Test oversized input.
- [ ] 9.10 Test unauthorized source IP rejection.
- [ ] 9.11 Test listener restart behavior.
- [ ] 9.12 Test service logs.

## 10. Phase 7 - Production Readiness / Uncle Handoff

- [ ] 10.1 Confirm our side fully ready.
- [ ] 10.2 Confirm Azure NSG restricted to expected IP if possible.
- [ ] 10.3 Confirm service active.
- [ ] 10.4 Confirm validation complete.
- [ ] 10.5 Prepare exact pfSense instructions:
  - Status -> System Logs -> Settings
  - enable Firewall Events
  - remote server: `<Azure VM IP>:514`
- [ ] 10.6 Only then ask uncle to configure pfSense.

## Safety Boundaries

- [ ] This parent change contains no implementation steps that authorize source edits.
- [ ] Do not modify application source files.
- [ ] Do not create child implementation specs as part of this parent roadmap.
- [ ] Do not implement listener/parser/adapter/detections.
- [ ] Do not open ports as part of this parent roadmap.
- [ ] Do not request uncle/pfSense configuration as part of this parent roadmap.
- [ ] Do not commit.
- [ ] Do not push.
