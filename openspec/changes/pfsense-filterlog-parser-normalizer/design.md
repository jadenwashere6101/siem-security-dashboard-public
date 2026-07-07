## Context

The parent roadmap `pfsense-firewall-ingestion-roadmap` recommends this sequence: parser/normalizer, ingest route, UDP listener, detections/SOAR, then deployment/runtime readiness. Existing inbound adapters are small modules under `adapters/` and existing ingest routes call centralized validation and `ingest_normalized_event`; this child spec only defines the parser and normalizer contract.

This design inherits the Phase 2.5 threat model. Raw syslog bytes, decoded text, syslog envelope content, and pfSense `filterlog` fields are untrusted external input. The parser must fail safely, never crash on malformed input, reject oversized packets before parsing, handle malformed UTF-8 safely, strip unsafe control characters, avoid broad raw payload retention, and produce bounded parse-failure telemetry.

## Goals / Non-Goals

**Goals:**

- Define a unit-testable parser/normalizer for pfSense syslog `filterlog` data.
- Define byte, text, syslog envelope, and `filterlog` payload safety behavior.
- Support common IPv4 TCP and IPv4 UDP `filterlog` records.
- Safely classify IPv6, unknown variants, malformed input, invalid UTF-8, oversized input, and unsupported records without crashing.
- Define normalized output that fits existing unified event expectations and includes `source="pfsense"` and `source_type="firewall"`.
- Define bounded, sanitized parse-failure telemetry that does not retain full attacker-controlled raw payloads.

**Non-Goals:**

- No Flask route, `/ingest/pfsense` endpoint, API key guard, or route tests.
- No UDP socket, listener daemon, source IP allow-list enforcement, rate limiting, systemd service, or deployment script.
- No database writes, migrations, `ingest_normalized_event` call, detection rules, SOAR/playbook changes, dashboard changes, Azure NSG changes, VM firewall changes, port opening, uncle/pfSense handoff, commit, or push.

## Decisions

1. Parser input starts as bytes plus optional metadata.

   The later implementation should accept raw packet bytes and optional caller metadata such as pfSense sender IP, sender port, received timestamp, and environment. Accepting bytes lets the parser own the 4096-byte length gate and UTF-8 behavior without requiring network sockets, Flask, or database state.

2. Reject oversized input before decode and parse.

   The parser must enforce the parent roadmap's initial 4096-byte maximum. Oversized records are rejected before UTF-8 decode, syslog parsing, or payload parsing and produce only bounded telemetry.

3. Decode UTF-8 safely and strip unsafe control characters.

   Malformed UTF-8 must not crash the parser. The design allows either strict rejection or safe replacement as long as the result is deterministic, bounded, and test-covered. Unsafe control characters must be stripped or replaced before logging, telemetry, or normalized payload use while preserving normal syslog separators such as spaces, commas, and printable punctuation.

4. Treat syslog envelope parsing as a lightweight boundary.

   The parser should extract the pfSense `filterlog` payload from a recognizable syslog envelope but must not trust timestamp, host, process, or program values as authoritative. Non-`filterlog` messages are unsupported parser input and fail safely.

5. Parse common IPv4 TCP and UDP records first.

   The contract covers common pfSense `filterlog` payload fields needed for normalized firewall events: action, interface, direction, ip version, protocol, traffic source/destination IPs, optional ports, and rule/tracker identifiers when present. IPv6 and other variants are accepted only as safely handled unsupported records until a later spec expands them.

6. Normalize into existing event shape without writing.

   Successful normalization should return an event dictionary compatible with the existing unified ingest expectations: `event_type`, `severity`, `source_ip`, `source`, `source_type`, `message`, `app_name`, `environment`, optional `event_timestamp`, and `raw_payload`. The parser must not call Flask routes, database helpers, detection engines, or SOAR code.

7. Keep raw payload retention narrow.

   `raw_payload` may include parsed safe fields and a bounded sanitized summary for debugging. It must not store broad full raw syslog by default. Parse failures must return only bounded reason, stage, input length, and sanitized summary fields.

## Risks / Trade-offs

- [Risk] pfSense `filterlog` field variants differ by version and protocol -> Mitigation: specify IPv4 TCP/UDP only for this child and fail safely on unknown variants.
- [Risk] Future firewall taxonomy is not accepted yet -> Mitigation: expose `firewall_block` and `firewall_allow` only as candidate mappings while preserving raw action.
- [Risk] Rejecting or summarizing raw payloads can reduce debugging detail -> Mitigation: keep bounded sanitized summaries and parsed fields while avoiding unbounded attacker-controlled retention.
- [Risk] Syslog envelope formats vary -> Mitigation: require robust envelope extraction and unsupported-message telemetry rather than crashing or guessing.

## Open Questions

- Whether invalid UTF-8 should be rejected or decoded with replacement is left to implementation as long as it satisfies the safety requirements and tests.
- Final severity mapping for `block` and `pass` events should be confirmed by the later detection/taxonomy child spec.
- IPv6 field mapping should be specified by a future parser expansion if IPv6 support becomes required.
