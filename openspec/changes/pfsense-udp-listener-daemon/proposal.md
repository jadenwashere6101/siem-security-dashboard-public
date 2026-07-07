## Why

The parser and backend route contracts now define how pfSense firewall events are normalized and ingested, but a dedicated UDP listener daemon is still needed to receive pfSense syslog packets safely and forward normalized events to `/ingest/pfsense`. This child spec defines that future listener and service contract without implementing code or exposing any network port now.

## What Changes

- Define a future repo-owned UDP listener daemon for pfSense syslog/filterlog packets.
- Select a high unprivileged default UDP port, preferably `5514`, unless final pfSense capability confirmation contradicts it.
- Require configurable bind host/interface, port, pfSense sender IP allow-list, backend ingest URL, ingest API key/header, rate limits, and logging.
- Require listener-side source IP allow-listing before parsing or forwarding.
- Require 4096-byte packet size enforcement before parse, UTF-8 safe handling, malformed packet handling, and safe control-character sanitization through the parser contract.
- Require integration with `pfsense-filterlog-parser-normalizer` and forwarding of valid normalized events to `/ingest/pfsense`.
- Require safe handling of backend 4xx/5xx/network failures, explicit no-retry behavior for UDP input unless later design changes it, rate limiting/backpressure, structured logs, rejected packet counts/metrics, and local synthetic packet test support.
- Define future systemd/service placement and environment variable expectations without creating service files now.
- Keep this child scope listener daemon only: no Flask route implementation, parser redesign, detection rules, SOAR tuning, Azure NSG rule, VM firewall rule, live external exposure, pfSense/uncle handoff, production traffic collection, commit, or push.

## Capabilities

### New Capabilities
- `pfsense-udp-listener-daemon`: UDP listener daemon and future service/deployment contract for safely receiving pfSense syslog and forwarding normalized events to the backend route.

### Modified Capabilities
- (none)

## Impact

- **Affected code later:** likely a listener script under `scripts/`, listener helper code if needed, future systemd unit/install helper files, and focused tests.
- **Affected APIs later:** consumes the existing/future `/ingest/pfsense` backend route; does not add a Flask route.
- **Affected systems now:** none. This spec creation does not modify application source files, create tests, create systemd units, touch the VM, open ports, create Azure NSG rules, or deploy anything.
- **Dependencies:** depends on `pfsense-filterlog-parser-normalizer` and `pfsense-ingest-route-pipeline`.
- **Parent roadmap:** item 6.10 is marked created/in progress with a listener-daemon-only boundary note.
