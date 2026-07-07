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

- [x] 4.1 Decide where listener should live.
  - 2026-07-07 finding: future child spec should place the UDP listener outside Flask as a repo-owned script/daemon, with reusable parser/normalizer code in an adapter module. Do not bind UDP 514 inside the Flask app.
- [x] 4.2 Decide daemon vs one-shot service.
  - 2026-07-07 finding: listener should be a long-running `Type=simple` systemd daemon, not a one-shot/timer. UDP packet listening is continuous runtime behavior.
- [x] 4.3 Decide POST-to-Flask vs direct ingest pattern.
  - 2026-07-07 finding: recommended pattern is listener parses/normalizes/validates and POSTs to a future Flask `/ingest/pfsense` route with an ingest API key. Avoid direct DB ingest from the listener so post-commit playbook, queue, incident, and response orchestration remain centralized in backend route logic.
- [x] 4.4 Audit reusable systemd patterns.
  - 2026-07-07 finding: reuse `deploy/systemd/soar-playbook-worker.service` as the daemon template and `scripts/install_soar_playbook_worker_service.sh` as the install/update/rollback template. Reuse `scripts/deploy_backend_vm.sh` health/migration preflight style for deployment validation.
- [x] 4.5 Audit reusable adapter utilities.
  - 2026-07-07 finding: active ingest adapters are narrow parser/normalizer modules under `adapters/`; future pfSense code should follow that style rather than integration-action adapter style under `integrations/`.
- [x] 4.6 Audit parser/sanitization helpers.
  - 2026-07-07 finding: no generic syslog parser/control-character sanitizer exists. Future child specs must add focused helpers for packet length, source allow-list, UTF-8 handling, control-character stripping, syslog envelope validation, and pfSense filterlog parsing.
- [x] 4.7 Audit validation and normalization functions.
  - 2026-07-07 finding: reuse IP validation patterns, `helpers/ingest_normalizers`, and `engines/ingest_engine.ingest_normalized_event`. Existing port-scan detection reads destination ports from `raw_payload.destination_port`, `dest_port`, `dst_port`, or `port`.
- [x] 4.8 Define exact ingestion flow.
  - 2026-07-07 finding: recommended flow is listener -> source IP allow-list -> packet length limit -> UTF-8 decode policy -> strip unsafe control characters -> validate syslog envelope -> parse pfSense filterlog -> normalize to `source=pfsense`, `source_type=firewall`, event type, IPs, protocol, direction, interface, action, destination port -> validate schema -> POST to `/ingest/pfsense` -> `ingest_normalized_event` -> detection/correlation -> playbook/SOAR orchestration.

## 5. Phase 2 - Security Review

- [x] 5.1 Create Azure NSG rule plan.
  - 2026-07-07 decision: Azure NSG must be the primary network allow-list layer. No Azure NSG rule should be opened until the listener is implemented and locally tested with synthetic packets. Eventual inbound rule must restrict UDP listener traffic to the expected pfSense public IP if possible; do not use `Any` source unless explicitly accepted as a temporary test exception with cleanup/removal task.
- [x] 5.2 Create VM firewall rule plan.
  - 2026-07-07 finding: UFW is inactive; iptables/ip6tables exist; INPUT policy is ACCEPT with no custom inbound restrictions shown; Docker-related FORWARD chains exist. VM-local filtering should be considered defense-in-depth but must not be assumed to already protect the listener. Do not implement VM firewall rules in Phase 2.
- [x] 5.3 Make UDP exposure decision.
  - 2026-07-07 decision: prefer a high unprivileged UDP port such as 5514 instead of privileged UDP 514 unless pfSense cannot send to a custom port. UDP 514 is currently unused and reserved.
- [x] 5.4 Define source IP allow-list.
  - 2026-07-07 decision: listener/adapter must validate packet sender source IP against an allow-list before parsing/ingest; unexpected sources must be rejected before parsing, with rejected counts logged/metriced without full attacker-controlled payload storage.
- [x] 5.5 Define expected pfSense public IP handling.
  - 2026-07-07 decision: allow-list must include the expected pfSense public IP. Final pfSense public IP confirmation remains a future gate before Azure NSG changes or uncle handoff.
- [x] 5.6 Define packet size limit.
  - 2026-07-07 decision: define maximum UDP packet length before parsing; recommended initial limit is 4096 bytes unless implementation audit justifies another value. Oversized packets must be rejected or truncated before parsing.
- [x] 5.7 Define malformed syslog handling.
  - 2026-07-07 decision: malformed syslog/filterlog lines must not crash the listener. Count/log malformed lines and either reject or store only sanitized parse-failure telemetry depending on child spec decision.
- [x] 5.8 Define malformed UTF-8 handling.
  - 2026-07-07 decision: decode syslog as UTF-8 with strict or safe replacement behavior, but never crash on malformed UTF-8.
- [x] 5.9 Define control-character stripping.
  - 2026-07-07 decision: strip unsafe control characters before logging/storing while preserving enough parseable context for debugging.
- [x] 5.10 Define rate limiting.
  - 2026-07-07 decision: UDP syslog is unauthenticated and spoofable, so listener/application-level rate limiting is required. Include per-source and global bounds if possible.
- [x] 5.11 Review spoofing/replay considerations.
  - 2026-07-07 decision: treat source IP allow-list and Azure NSG restriction as mandatory controls, but still assume UDP can be spoofed/noisy. Avoid unbounded DB writes from malformed or repeated noise.
- [x] 5.12 Define logging/monitoring.
  - 2026-07-07 decision: log/metric accepted packets, rejected source IP counts, malformed counts, oversized counts, parser failures, and ingest failures without storing full attacker-controlled payloads by default.
- [x] 5.13 Complete DoS/storage-risk review.
  - 2026-07-07 decision: storage growth must be monitored. Prefer normalized event storage over raw full-payload retention and avoid unbounded writes from malformed or repeated noise.
- [x] 5.14 Complete data retention and privacy review.
  - 2026-07-07 decision: pfSense logs may contain real business network metadata. Logs will be stored on the Azure VM in the SIEM PostgreSQL database. Decide later whether raw syslog is retained temporarily, redacted, or dropped after parsing.
- [x] 5.15 Confirm what to tell uncle about where logs are stored.
  - 2026-07-07 decision: before asking uncle to configure pfSense, tell him logs are stored on the Azure VM in the SIEM PostgreSQL database and describe what types of firewall logs are being sent.

### Phase 2 Future Gates - Not Executed In Parent Roadmap

- [ ] 5.16 Confirm final listener port selection, including whether pfSense supports the selected custom port.
- [ ] 5.17 If pfSense requires UDP 514, document the privilege/capability plan before implementation.
- [ ] 5.18 Confirm expected pfSense public IP for Azure NSG and listener allow-list.
- [ ] 5.19 Create Azure NSG rule later only after listener implementation and local synthetic packet testing.
- [ ] 5.20 Decide later whether to add VM firewall defense-in-depth rules for the selected UDP port.
- [ ] 5.21 If a temporary broader Azure NSG source is approved for testing, add an explicit cleanup/removal task.
- [ ] 5.22 Draft uncle handoff message later, after deployment/runtime validation gates pass.

## 5.5. Phase 2.5 - Threat Model

- [x] 5.5.1 Threat model completed.
  - 2026-07-07 finding: parent-level threat model created in `phase-2.5-threat-model.md`.
- [x] 5.5.2 Assets documented.
  - 2026-07-07 finding: protected assets include the Azure VM, SIEM backend, PostgreSQL database, SOAR worker, future listener/adapter, detection/playbook engines, firewall telemetry, business metadata, deployment pipeline, and GitHub source repository.
- [x] 5.5.3 Trust boundaries documented.
  - 2026-07-07 finding: trust boundaries are documented from Internet ingress through Azure NSG, VM networking, listener, parser, normalizer, Flask ingest, database, detection, SOAR, and dashboard.
- [x] 5.5.4 Threats documented.
  - 2026-07-07 finding: network, parser, application, operational, and privacy threats are documented.
- [x] 5.5.5 Mitigations documented.
  - 2026-07-07 finding: network, listener, parser, pipeline, and operational mitigations are documented.
- [x] 5.5.6 Security principles documented.
  - 2026-07-07 finding: least privilege, defense in depth, fail-safely behavior, centralized validation, explicit trust boundaries, source-of-truth architecture, reproducible deployment, and auditable runtime behavior are documented.
- [x] 5.5.7 Child-spec inheritance documented.
  - 2026-07-07 finding: future child specs must inherit this threat model and reference it instead of redefining shared mitigations.

## 6. Phase 3 - Child Spec Planning and Scope Boundaries

Phase 3 does not implement anything, does not create code, does not open Azure/VM ports, and does not create child specs. Phase 3 exists to define the child specs that will be created next. The existing pfSense parent roadmap is enough to coordinate this work; no separate Phase 3 parent coordination spec is needed.

- [x] 6.1 Phase 3 remodeled inside parent roadmap.
  - 2026-07-07 finding: Phase 3 now defines the five future child specs and scope boundaries in `phase-3-child-spec-plan.md`.
- [x] 6.2 Child spec categories recorded.
  - 2026-07-07 finding: child specs are categorized as CODE SPEC, CODE + DEPLOYMENT SPEC, or NON-CODE + DEPLOYMENT SPEC.
- [x] 6.3 Code vs non-code/operator topics recorded.
  - 2026-07-07 finding: each child spec has explicit implementation and operator/deployment boundaries.
- [x] 6.4 Sequencing recorded.
  - 2026-07-07 finding: sequence is parser/normalizer, ingest route, UDP listener, detections/SOAR, deployment/runtime readiness.
- [x] 6.5 Dependencies recorded.
  - 2026-07-07 finding: ingest route depends on parser contract; UDP listener depends on parser and route contracts; detections/SOAR depend on stable taxonomy; deployment depends on code specs.
- [x] 6.6 No separate Phase 3 parent spec needed.
  - 2026-07-07 finding: existing parent roadmap will track the five child specs.
- [x] 6.7 First child spec identified as `pfsense-filterlog-parser-normalizer`.
  - 2026-07-07 finding: parser/normalizer is first because it defines the normalized firewall event contract for downstream specs.

### Phase 3 Future Child Specs - Not Created Yet

- [x] 6.8 Create `pfsense-filterlog-parser-normalizer` later.
  - 2026-07-07 update: child spec created at `openspec/changes/pfsense-filterlog-parser-normalizer/` and scoped to parser/normalizer only. It does not implement a listener, Flask route, detection rules, deployment, Azure NSG changes, VM firewall changes, or uncle/pfSense handoff.
  - 2026-07-07 implementation update: parser/normalizer implementation and unit tests completed in the Mac repo only. Listener, route, detections, deployment, Azure NSG, VM firewall, and uncle/pfSense handoff remain separate future child specs.
- [ ] 6.9 Create `pfsense-ingest-route-pipeline` later.
- [ ] 6.10 Create `pfsense-udp-listener-daemon` later.
- [ ] 6.11 Create `pfsense-firewall-detections-soar` later.
- [ ] 6.12 Create `pfsense-deployment-runtime-readiness` later.

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
