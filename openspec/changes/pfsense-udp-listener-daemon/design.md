## Context

The parent roadmap sequence places `pfsense-udp-listener-daemon` after the parser/normalizer and backend route specs. The parser contract owns syslog/filterlog parsing, UTF-8 safety, control-character stripping, malformed input behavior, parse failure telemetry, and normalized event shape. The route contract owns API-key validation, route-level validation, centralized ingest, and downstream detection/correlation/SOAR/incident orchestration.

This listener sits at the network edge of the application. It receives untrusted UDP datagrams, validates sender source IP before parsing, enforces size and rate limits, uses the parser contract, and forwards only valid normalized events to `/ingest/pfsense`. It must not import Flask app state, access the database, write directly to the database, implement detection logic, tune playbooks, or open cloud/VM firewall exposure.

The design inherits Phase 2 security decisions and the Phase 2.5 threat model. UDP is unauthenticated and spoofable, so the listener must fail safely and avoid broad raw payload retention. The default listener port is the high unprivileged UDP port `5514` unless final pfSense port support confirmation requires a different port.

## Goals / Non-Goals

**Goals:**

- Define a long-running UDP listener daemon that binds to configurable host/interface and port.
- Require configurable pfSense source IP allow-list enforcement before parsing or forwarding.
- Enforce the initial 4096-byte packet limit before parse.
- Use the parser/normalizer contract for UTF-8 safety, control-character sanitization, malformed packet handling, and normalized event generation.
- Forward valid normalized events to `/ingest/pfsense` with the configured ingest API key/header.
- Log accepted, rejected, malformed, oversized, parser-failure, rate-limited, and backend-failure outcomes safely.
- Define rate limiting/backpressure behavior and local synthetic packet test support.
- Define future systemd daemon placement, environment variables, service health/logging expectations, install/update/rollback expectations, and explicit external exposure gates.

**Non-Goals:**

- No Flask `/ingest/pfsense` route implementation.
- No parser redesign beyond consuming the parser contract.
- No detection rule implementation, SOAR/playbook tuning, dashboard change, migration, or direct database write.
- No Azure NSG rule, VM firewall rule, live external exposure, production traffic collection, or uncle/pfSense handoff.
- No systemd unit or install script creation in this spec-creation task.

## Decisions

1. Use a standalone Python daemon entrypoint.

   The future implementation should follow the existing daemon style under `scripts/`, likely `scripts/pfsense_syslog_listener.py`, rather than binding UDP inside Flask. This keeps UDP listener lifecycle separate from the web app and matches the parent architecture audit.

2. Default to UDP `5514` with configurable bind settings.

   The listener should default to a high unprivileged port, `5514`, and a configurable bind host/interface. UDP `514` remains reserved unless final pfSense capability confirmation requires it and a privilege/capability plan is documented.

3. Validate sender IP before parse.

   The listener must validate the UDP sender IP against a configured allow-list before parsing or forwarding. Unexpected sources are rejected with counts/logs that avoid retaining full attacker-controlled payloads.

4. Enforce packet and rate bounds at the listener.

   The listener enforces the 4096-byte packet size limit before parser handoff. It also applies global and per-source rate limiting/backpressure where feasible so noisy or spoofed UDP traffic cannot cause unbounded parsing, logging, forwarding, or storage pressure.

5. Use parser and route contracts without bypassing them.

   Valid packets are passed to the parser/normalizer contract. Successful normalized events are POSTed to `/ingest/pfsense` using the configured API key/header. The listener does not call `ingest_normalized_event`, does not connect to PostgreSQL, and does not implement route validation itself beyond listener-edge checks.

6. Do not retry UDP packet forwarding by default.

   UDP input has no delivery guarantee and can be high-volume or spoofed. Backend 4xx/5xx/network failures should be logged safely and counted, then dropped by default. If future implementation adds bounded retry, it must prove no unbounded memory/disk queue or duplicate-ingest risk.

7. Use structured safe logging.

   Logs should include outcome, sender IP, packet size, parse failure reason/stage, backend status class, and rate-limit counts. Logs must not dump full raw packets, full raw syslog, API keys, or attacker-controlled payloads.

8. Follow existing service patterns later.

   Future deployment files should follow the `Type=simple` daemon pattern used by `soar-playbook-worker.service`, with `EnvironmentFile`, `PYTHONUNBUFFERED=1`, journal logging, `Restart=on-failure`, explicit stop behavior, and an operator-controlled install/update/rollback helper that does not auto-start unless requested.

## Risks / Trade-offs

- [Risk] UDP spoofing can bypass sender identity assumptions -> Mitigation: combine listener allow-listing with future Azure NSG restriction and avoid storing/forwarding unexpected source traffic.
- [Risk] Dropping backend failures loses firewall events -> Mitigation: log safe counters and rely on runtime health checks; avoid unbounded queues unless a later bounded durability design is specified.
- [Risk] Rate limits can drop legitimate bursts -> Mitigation: make limits configurable and testable, and log rate-limited counts for tuning.
- [Risk] Opening a UDP port too early creates exposure -> Mitigation: this spec forbids Azure NSG/VM firewall/live exposure and defers external traffic to deployment/runtime readiness.
- [Risk] Systemd install helpers can accidentally start services -> Mitigation: require operator-controlled install behavior with explicit `--enable` / `--start` flags.

## Open Questions

- Confirm whether pfSense can send firewall syslog to custom UDP port `5514`; if not, document the UDP `514` privilege/capability plan before implementation.
- Confirm expected pfSense public IP before listener allow-list and Azure NSG readiness work.
- Decide in the deployment/runtime readiness child spec whether VM firewall defense-in-depth rules will be added.
