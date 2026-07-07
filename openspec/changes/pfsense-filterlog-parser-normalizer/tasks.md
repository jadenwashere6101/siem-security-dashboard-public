## 1. Audit / Verification

- [x] 1.1 Re-read the parent roadmap and confirm this child still maps only to Phase 3 item 6.8.
- [x] 1.2 Re-check `adapters/`, `helpers/ingest_normalizers.py`, and `routes/ingest_routes.py` for current normalization patterns before implementation.
- [x] 1.3 Confirm implementation scope remains parser/normalizer only with no Flask route, DB writes, UDP listener, systemd service, Azure NSG, VM firewall, detection rules, or pfSense handoff.
- [x] 1.4 Confirm Phase 2.5 threat model requirements are represented in implementation notes and tests.

## 2. Parser / Normalizer Implementation Later

- [x] 2.1 Add a focused pfSense filterlog parser/normalizer module following the existing adapter style.
- [x] 2.2 Enforce the 4096-byte raw packet size limit before UTF-8 decode or parse.
- [x] 2.3 Implement safe UTF-8 handling for malformed byte sequences.
- [x] 2.4 Implement unsafe control-character stripping or replacement for decoded text.
- [x] 2.5 Extract the pfSense `filterlog` payload from a recognizable syslog envelope.
- [x] 2.6 Parse common IPv4 TCP `filterlog` records into structured fields.
- [x] 2.7 Parse common IPv4 UDP `filterlog` records into structured fields.
- [x] 2.8 Safely handle IPv6, unsupported protocols, unknown variants, malformed records, empty input, and non-filterlog syslog.
- [x] 2.9 Return bounded sanitized parse-failure telemetry without broad raw payload retention.
- [x] 2.10 Normalize successful records into the existing unified event shape with `source="pfsense"` and `source_type="firewall"`.
- [x] 2.11 Preserve safe parsed firewall fields in `raw_payload`, including destination port when present.
- [x] 2.12 Preserve `action` and expose candidate `firewall_block` / `firewall_allow` taxonomy mapping without adding detection behavior.
- [x] 2.13 Keep the parser free of Flask, DB, network socket, listener, deployment, and SOAR side effects.

## 3. Unit Tests Later

- [x] 3.1 Add tests proving a common IPv4 TCP filterlog line parses correctly.
- [x] 3.2 Add tests proving a common IPv4 UDP filterlog line parses correctly.
- [x] 3.3 Add tests proving blocked traffic normalizes as a `firewall_block` candidate.
- [x] 3.4 Add tests proving passed traffic normalizes as a `firewall_allow` candidate.
- [x] 3.5 Add tests proving malformed lines do not crash the parser.
- [x] 3.6 Add tests proving oversized input is rejected before parse.
- [x] 3.7 Add tests proving invalid UTF-8 does not crash the parser.
- [x] 3.8 Add tests proving unsafe control characters are stripped or sanitized.
- [x] 3.9 Add tests proving IPv6 and unsupported variants are handled safely.
- [x] 3.10 Add tests proving normalized output matches existing unified event expectations.
- [x] 3.11 Add tests proving parser/normalizer behavior can be exercised without Flask, DB, or network sockets.

## 4. Parent Roadmap Update Later

- [x] 4.1 After implementation and unit tests pass, update `pfsense-firewall-ingestion-roadmap` to record parser/normalizer completion status.
- [x] 4.2 Keep later roadmap notes clear that listener, route, detections, deployment, Azure NSG, VM firewall, and uncle/pfSense handoff remain separate child specs.
