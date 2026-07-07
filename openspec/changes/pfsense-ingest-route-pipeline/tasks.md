## 1. Audit / Verification

- [x] 1.1 Re-read the parent roadmap and confirm this child still maps only to Phase 3 item 6.9.
- [x] 1.2 Re-read `pfsense-filterlog-parser-normalizer` and confirm the route uses the parser normalized event contract without redesigning parser behavior.
- [x] 1.3 Re-check `routes/ingest_routes.py`, `helpers/ingest_normalizers.py`, `adapters/`, and related ingest tests for current route, auth, validation, and orchestration patterns.
- [x] 1.4 Confirm implementation scope remains backend route/pipeline only with no UDP listener, systemd service, Azure NSG, VM firewall, detections, SOAR tuning, deployment, or pfSense/uncle handoff.
- [x] 1.5 Confirm Phase 2 security decisions, Phase 2.5 threat model, and parser safety contract are represented in implementation notes and tests.

## 2. Route Implementation Later

- [x] 2.1 Add `POST /ingest/pfsense` to the existing ingest route blueprint.
- [x] 2.2 Apply the existing ingest API-key guard before processing request data.
- [x] 2.3 Validate JSON shape and reject malformed payloads with safe 4xx responses.
- [x] 2.4 Validate required normalized fields: `event_type`, `severity`, `source_ip`, `source`, `source_type`, `message`, `app_name`, `environment`, and `raw_payload`.
- [x] 2.5 Validate `source="pfsense"` and `source_type="firewall"`.
- [x] 2.6 Accept pfSense firewall taxonomy candidates `firewall_block` and `firewall_allow` for this route.
- [x] 2.7 Validate safe parsed firewall fields in `raw_payload`, including action, interface, direction, IP version, protocol, source/destination IPs, ports when present, and rule/tracker fields when present.
- [x] 2.8 Ensure error responses do not echo full raw payloads, raw syslog, stack traces, or attacker-controlled summaries.
- [x] 2.9 Use existing request-size protections or add a route-level request bound if current app patterns support it.
- [x] 2.10 Call `ingest_normalized_event` or the equivalent current centralized ingest function for valid pfSense events.
- [x] 2.11 Preserve existing post-commit playbook scheduling, queue enqueueing, and incident creation flow.
- [x] 2.12 Avoid direct database writes outside the centralized ingest path.

## 3. API Tests Later

- [x] 3.1 Add a success test proving a valid parsed `firewall_block` pfSense payload ingests through `/ingest/pfsense`.
- [x] 3.2 Add a success test proving a valid parsed `firewall_allow` pfSense payload ingests through `/ingest/pfsense`.
- [x] 3.3 Add tests proving missing required fields are rejected with safe 4xx responses.
- [x] 3.4 Add tests proving malformed payloads are rejected without raw attacker-controlled content in responses.
- [x] 3.5 Add tests proving missing and invalid API keys are rejected before centralized ingest.
- [x] 3.6 Add tests proving the route calls the centralized ingest pipeline for valid payloads.
- [x] 3.7 Add tests proving the route does not directly write events outside the centralized ingest path.
- [x] 3.8 Add tests proving successful ingest preserves existing downstream playbook, queue, and incident orchestration behavior.
- [x] 3.9 Add tests proving parser tests remain separate and route tests do not depend on raw syslog parsing.
- [x] 3.10 Add tests proving no listener, socket, systemd, Azure, VM firewall, detection, SOAR tuning, or deployment behavior is included.

## 4. Parent Roadmap Update Later

- [x] 4.1 After implementation and API tests pass, update `pfsense-firewall-ingestion-roadmap` to record route/pipeline completion status.
- [x] 4.2 Keep later roadmap notes clear that UDP listener, detections, deployment, Azure NSG, VM firewall, and uncle/pfSense handoff remain separate child specs.
