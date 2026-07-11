## Why

**Owner: Mac AI.** The pfSense listener currently forwards every successfully parsed IPv4 TCP/UDP `block` and `pass` record, and `/ingest/pfsense` enriches and stores every valid payload. Before production firewall logs arrive, the SIEM needs a runtime-editable, fail-closed retention policy that preserves security-relevant traffic while dropping routine allowed traffic before enrichment and database insertion.

## What Changes

- Add a source-controlled default policy and `pfsense_ingest_config` persistence for block retention, inbound sensitive-port allows, all allows, DNS traffic (TCP/UDP destination port 53), allowed ICMP traffic, and the canonical sensitive-port list.
- Evaluate normalized, validated pfSense events in `/ingest/pfsense` before geolocation and `ingest_normalized_event()`; filtered payloads are not written to `events` or any secondary raw-event table.
- Default to retaining every block and inbound sensitive-port allow while dropping routine allows; configuration failures fall back to those safe defaults rather than ingesting everything.
- Make the sensitive-port configuration authoritative for both retention and suspicious-allow detection, replacing the detector’s independent hardcoded list.
- Extend the bounded filterlog parser/normalizer and route validator for supported IPv4 ICMP records so the ICMP control is functional; IPv6 and non-filterlog categories remain out of scope.
- Return a distinct filtered response and expose bounded aggregate decision counters/reasons without retaining dropped payloads.
- Add super-admin configuration APIs, validation, audit logging, and a dark-theme Administration panel whose changes affect the next request without service restart.
- Add migrations, schema snapshot updates, backend/frontend tests, end-to-end decision matrices, documentation, and a VM handoff.

## Capabilities

### New Capabilities

- `pfsense-runtime-ingest-filter-policy`: Persistent defaults, validation, decision precedence, fail-closed fallback, canonical ports, ICMP support, and pre-storage filtering.
- `pfsense-ingest-filter-administration`: Super-admin read/update APIs and Administration UI for toggles and sensitive ports.
- `pfsense-ingest-filter-observability`: Distinct filtered outcomes plus bounded aggregate retained/filtered/rejected counters and reasons without raw dropped-event storage.

### Modified Capabilities

<!-- Existing pfSense implementation specs are completed change artifacts, not base capabilities under openspec/specs. This change adds compatible contracts without duplicating a base spec. -->

## Impact

Expected Mac source scope includes the pfSense parser, listener response accounting, ingest route, detection configuration/engine, a new configuration store, admin routes, migration/schema snapshot, Administration navigation/panel/service, tests, and deployment documentation. Existing authentication, API-key guards, listener source/rate limits, centralized ingest, detections, correlation, SOAR orchestration, and Mac/VM ownership remain intact. Actual DNS query logs, IPv6, other pfSense services, production deployment, commits, and pushes are excluded.
