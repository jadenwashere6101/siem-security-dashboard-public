# Phase 1 Architecture Audit

Date: 2026-07-07

Scope: architecture audit for `pfsense-firewall-ingestion-roadmap`. No application source files were edited. No VM files or services were modified. No child implementation specs were created. No ports were opened. No commits or pushes were performed.

## Summary

Recommended architecture:

```text
pfSense firewall
  -> UDP syslog packet
  -> dedicated pfSense listener daemon
  -> validate source IP allow-list
  -> validate packet length
  -> decode with explicit UTF-8 policy
  -> strip unsafe control characters
  -> validate syslog envelope
  -> parse pfSense filterlog
  -> normalize firewall event
  -> validate normalized schema
  -> POST to Flask /ingest/pfsense
  -> engines.ingest_engine.ingest_normalized_event
  -> detection/correlation
  -> SOAR/playbooks
```

Key decision: keep the raw UDP listener outside Flask, but keep database writes and post-commit orchestration inside the Flask/backend ingestion path.

## 4.1 Listener Location

Decision: the listener should live outside the Flask app as a repo-owned Python daemon entrypoint, with parser/normalizer logic in an adapter-style module.

Recommended future layout for child specs:

- `scripts/pfsense_syslog_listener.py` for the long-running UDP listener entrypoint.
- `adapters/pfsense_filterlog_adapter.py` for syslog/filterlog parsing and normalization helpers.
- `routes/ingest_routes.py` for a future `/ingest/pfsense` POST route.
- `deploy/systemd/pfsense-syslog-listener.service` for the VM systemd unit.
- `scripts/install_pfsense_syslog_listener_service.sh` for operator-controlled install/update/rollback.

Reasoning:

- Flask currently owns HTTP routes, app setup, CORS, sessions, rate limiting, and frontend serving.
- Long-running workers are already modeled as separate scripts and systemd services.
- Binding UDP 514 inside Flask would mix packet listener lifecycle with web app lifecycle and complicate restart/error boundaries.

## 4.2 Daemon vs One-shot Service

Decision: use a daemon service, not a one-shot/timer.

The pfSense integration needs a process continuously bound to a UDP socket. The closest existing repo pattern is:

- `deploy/systemd/soar-playbook-worker.service`
- `scripts/soar_playbook_worker_daemon.py`
- `scripts/install_soar_playbook_worker_service.sh`

The response-action worker timer pattern is not appropriate for UDP packet collection because it runs bounded one-shot batches and exits.

## 4.3 POST-to-Flask vs Direct Ingest

Decision: prefer POST-to-Flask.

Recommended split:

- Listener daemon performs network-edge safety checks and pfSense parsing/normalization.
- Listener daemon sends normalized payloads to a future backend route, likely `/ingest/pfsense`, using an ingest API key.
- Flask route performs final schema validation and calls `ingest_normalized_event`.

Reasons to avoid direct DB ingest from the listener:

- Existing route flow centralizes post-commit playbook execution creation, response queue enqueueing, and incident creation.
- Direct DB ingest would require duplicating route orchestration or importing Flask-adjacent behavior into a daemon.
- A POST route keeps database credentials out of the listener if the listener only needs the ingest URL and API key.

Tradeoff:

- POST-to-Flask adds one local HTTP hop and requires a new route.
- That cost is acceptable because the existing backend route pattern already handles ingestion side effects.

## 4.4 Reusable systemd Patterns

Reusable daemon pattern:

- `deploy/systemd/soar-playbook-worker.service`
  - `Type=simple`
  - `User=jaden`
  - `Group=jaden`
  - `WorkingDirectory=/home/jaden/siem-security-dashboard`
  - `EnvironmentFile=/home/jaden/siem-security-dashboard/.env`
  - `Restart=on-failure`
  - `RestartSec=15`
  - `StandardOutput=journal`
  - `StandardError=journal`

Reusable install/update/rollback pattern:

- `scripts/install_soar_playbook_worker_service.sh`
  - preflight repo path
  - verify source unit exists
  - dry-run mode
  - explicit enable/start flags
  - rollback path
  - `systemctl daemon-reload`

Reusable deployment validation style:

- `scripts/deploy_backend_vm.sh`
  - preflight output
  - bounded health checks
  - migration dry-run before apply
  - restart only after successful preflight/apply

## 4.5 Reusable Adapter Utilities

Active ingestion adapters are narrow normalization modules:

- `adapters/nginx_adapter.py`
- `adapters/azure_insights_adapter.py`
- `adapters/otel_adapter.py`

The pfSense parser should follow this style: small, focused parser/normalizer helpers with explicit supported input shape and tests.

Do not model pfSense ingestion after SOAR action adapters under `integrations/soar_adapters/`; those are outbound action execution adapters, not inbound ingestion adapters.

## 4.6 Parser And Sanitization Helpers

No generic reusable syslog parser or control-character sanitizer exists today.

Future child specs must define and test:

- UDP packet byte-length limit.
- Source IP allow-list validation before parsing.
- Explicit malformed UTF-8 policy.
- Control-character stripping rules.
- Syslog envelope validation.
- pfSense `filterlog` field parsing.
- Malformed input rejection and metrics/logging behavior.

## 4.7 Validation And Normalization Functions

Reusable validation/normalization patterns:

- IP parsing via `ipaddress.ip_address`.
- `helpers/ingest_normalizers` for shared ingest helper patterns.
- `engines.ingest_engine.ingest_normalized_event` as the central normalized ingest function.
- Existing route-side payload validation in `routes/ingest_routes.py`.

Important detection contract:

- `port_scan` detection reads destination port from `raw_payload` keys:
  - `destination_port`
  - `dest_port`
  - `dst_port`
  - `port`

Future pfSense normalization should include `destination_port` in `raw_payload` when a valid destination port is present.

Recommended normalized pfSense fields:

- `event_type`: likely `port_scan`, `unauthorized_access`, `normal_activity`, or a future firewall-specific event type depending on parser/detection child specs.
- `severity`: derived from action/direction/protocol/port and future rule design.
- `source_ip`: packet traffic source IP from filterlog, not necessarily the pfSense sender IP.
- `source`: `pfsense`.
- `source_type`: `firewall`.
- `app_name`: `pfsense_filterlog`.
- `environment`: from listener config, defaulting to `prod`.
- `raw_payload`: sanitized original message plus parsed fields such as action, interface, protocol, direction, source IP, destination IP, destination port, rule number, tracker, and pfSense sender IP.

## 4.8 Exact Ingestion Flow

Recommended future implementation flow:

```text
UDP listener
  -> receive datagram
  -> capture sender IP/port
  -> reject sender not in allow-list
  -> reject packet over configured byte limit
  -> decode bytes with strict or replace-and-reject policy defined by security review
  -> strip unsafe control characters while preserving parseable separators
  -> validate syslog envelope shape
  -> require pfSense filterlog marker
  -> parse filterlog fields
  -> validate traffic source IP, destination IP, protocol, action, direction, and destination port where applicable
  -> normalize event dict
  -> validate normalized schema
  -> POST normalized payload to Flask /ingest/pfsense with API key
  -> backend route calls ingest_normalized_event
  -> backend commits event/alerts
  -> backend schedules playbooks and SOAR queue work
  -> backend creates/links incidents
```

## Architecture Gates For Later Phases

- Phase 2 security review must decide UDP exposure, allow-list behavior, packet-size limit, malformed UTF-8 behavior, rate limiting, spoofing/replay stance, and logging/retention rules before any implementation.
- Child specs should be split by milestone: listener, parser, route/adapter, event types, detection rules, deployment/service setup.
- Each child spec must include tests and deployment validation before moving to the next milestone.
- VM divergence found in Phase 0 remains a deployment blocker until intentionally resolved.

