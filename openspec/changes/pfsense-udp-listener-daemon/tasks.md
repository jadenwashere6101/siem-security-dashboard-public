## 1. Audit / Verification

- [ ] 1.1 Re-read the parent roadmap and confirm this child still maps only to Phase 3 item 6.10.
- [ ] 1.2 Re-read `pfsense-filterlog-parser-normalizer` and confirm the listener consumes the parser contract without redesigning parser behavior.
- [ ] 1.3 Re-read `pfsense-ingest-route-pipeline` and confirm the listener forwards normalized events to `/ingest/pfsense` without bypassing the route.
- [ ] 1.4 Re-check `scripts/`, `deploy/systemd/`, service install helpers, worker daemon scripts, honeypot/deployment patterns if present, and service/listener tests before implementation.
- [ ] 1.5 Confirm implementation scope remains listener daemon only with no Flask route, parser redesign, detections, SOAR tuning, Azure NSG, VM firewall, live exposure, production traffic, or uncle/pfSense handoff.
- [ ] 1.6 Confirm Phase 2 security decisions and Phase 2.5 threat model requirements are represented in implementation notes and tests.

## 2. Listener Implementation Later

- [ ] 2.1 Add a standalone pfSense UDP listener daemon entrypoint, likely under `scripts/`.
- [ ] 2.2 Add configuration parsing for bind host/interface, port, source IP allow-list, backend ingest URL, API key/header, packet size limit, rate limits, timeout, log level, and test controls.
- [ ] 2.3 Default the listener port to UDP `5514` unless final port confirmation requires a documented alternative.
- [ ] 2.4 Bind a UDP socket to the configured host and port.
- [ ] 2.5 Validate UDP sender source IP against the configured allow-list before parsing or forwarding.
- [ ] 2.6 Enforce the 4096-byte packet size limit before UTF-8 decode, parser handoff, or forwarding.
- [ ] 2.7 Use the parser/normalizer contract for UTF-8 safety, control-character sanitization, parsing, malformed handling, and normalized event output.
- [ ] 2.8 Forward valid normalized events to `/ingest/pfsense` with the configured API key/header.
- [ ] 2.9 Handle backend 4xx, backend 5xx, timeout, and network failures safely without crashing or leaking secrets.
- [ ] 2.10 Implement no-retry/drop-after-attempt behavior for UDP packets unless a later bounded durability design is approved.
- [ ] 2.11 Implement configurable global and per-source rate limiting or backpressure.
- [ ] 2.12 Emit structured safe logs/metrics for accepted, rejected, oversized, malformed, parse-failed, rate-limited, forwarded, backend-failed, startup, and shutdown events.
- [ ] 2.13 Keep the listener free of Flask app state, database connections, direct DB writes, detection logic, and SOAR/playbook behavior.

## 3. Service / Systemd / Deployment-File Tasks Later

- [ ] 3.1 Add a future systemd unit for the listener using the existing `Type=simple` daemon pattern.
- [ ] 3.2 Add future environment variable documentation or comments for listener bind, port, allow-list, backend URL, API key/header, bounds, rate limits, timeout, and log level.
- [ ] 3.3 Add a future operator-controlled install/update/rollback helper that does not enable or start the listener unless explicit flags are passed.
- [ ] 3.4 Add future service health/logging expectations using journal output and bounded status checks.
- [ ] 3.5 Keep Azure NSG creation, VM firewall creation, external exposure, and uncle/pfSense handoff out of this child spec and deferred to deployment/runtime readiness.
- [ ] 3.6 Add a future port-confirmation gate documenting whether pfSense can send to UDP `5514` before any external exposure work.

## 4. Tests Later

- [ ] 4.1 Add tests proving the listener binds to configured UDP host and port.
- [ ] 4.2 Add tests proving unauthorized source IPs are rejected before parse or backend forwarding.
- [ ] 4.3 Add tests proving oversized packets are rejected before parser handoff.
- [ ] 4.4 Add tests proving malformed UTF-8 and malformed packets do not crash the listener.
- [ ] 4.5 Add tests proving valid packets use the parser contract and forward normalized events to `/ingest/pfsense`.
- [ ] 4.6 Add tests proving backend 4xx, backend 5xx, timeout, and network failures are logged safely.
- [ ] 4.7 Add tests proving malformed packets do not reach the backend.
- [ ] 4.8 Add tests proving rate-limit behavior is deterministic and testable.
- [ ] 4.9 Add tests proving the listener performs no database access or direct database writes.
- [ ] 4.10 Add tests proving structured logs do not include raw full packets, raw full syslog, or API keys.
- [ ] 4.11 Add text or behavior tests for future systemd unit and install helper patterns.
- [ ] 4.12 Add tests proving no Azure NSG, VM firewall, live exposure, detection, SOAR tuning, or uncle handoff behavior is included.

## 5. Runtime Validation Tasks Later

- [ ] 5.1 Run local synthetic UDP packet tests against the configured listener without opening Azure NSG or VM firewall exposure.
- [ ] 5.2 Verify local accepted packet, unauthorized source, oversized packet, malformed packet, parser failure, backend failure, and rate-limit outcomes.
- [ ] 5.3 Verify listener startup, graceful shutdown, restart-on-failure, and journal logging behavior under the future systemd pattern.
- [ ] 5.4 Verify the listener can run without DB credentials or DB connectivity.
- [ ] 5.5 Stop before any live external exposure, Azure NSG change, VM firewall change, or uncle/pfSense handoff.

## 6. Parent Roadmap Update Later

- [ ] 6.1 After implementation and tests pass, update `pfsense-firewall-ingestion-roadmap` to record listener daemon completion status.
- [ ] 6.2 Keep later roadmap notes clear that detections, deployment/runtime readiness, Azure NSG, VM firewall, live exposure, and uncle/pfSense handoff remain separate child specs.
