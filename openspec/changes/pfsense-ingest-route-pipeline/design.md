## Context

The parent roadmap sequence places `pfsense-ingest-route-pipeline` after `pfsense-filterlog-parser-normalizer` and before the UDP listener daemon. The parser child defines sanitized normalized pfSense firewall events with `source="pfsense"`, `source_type="firewall"`, and candidate event types `firewall_block` / `firewall_allow`.

Current ingest route patterns in `routes/ingest_routes.py` enforce API-key guards, validate payloads, call `ingest_normalized_event`, commit the ingest result, and then run existing post-commit playbook scheduling, queue enqueueing, and incident creation. This child spec should preserve that route-level orchestration. The route must not write directly to the database outside the centralized ingest path.

This design inherits the Phase 2 security decisions, the Phase 2.5 threat model, and the parser child safety contract. Even though the future listener should send sanitized parser output, the Flask route remains a trust boundary and must validate all received data.

## Goals / Non-Goals

**Goals:**

- Define `POST /ingest/pfsense` for normalized pfSense firewall events from the future listener.
- Validate required normalized fields and pfSense-specific source fields at the route boundary.
- Enforce the existing ingest API-key pattern.
- Accept `firewall_block` and `firewall_allow` when paired with `source="pfsense"` and `source_type="firewall"`.
- Call the existing centralized normalized ingest function and preserve existing downstream detection/correlation/SOAR/queue/incident orchestration.
- Return safe structured success and error responses.
- Include future API tests for success, authentication, validation, malformed payload, and orchestration behavior.

**Non-Goals:**

- No UDP socket/listener implementation.
- No systemd service, deployment script, Azure NSG change, VM firewall change, port opening, runtime validation, or pfSense/uncle handoff.
- No firewall detection rule implementation, SOAR/playbook tuning, dashboard change, parser redesign, or parser test changes.
- No direct database writes outside the centralized normalized ingest path.

## Decisions

1. Route accepts normalized parser output, not raw syslog.

   The route should receive structured events produced by the parser/normalizer contract. Raw syslog packet handling, syslog envelope parsing, UTF-8 handling, control-character stripping, packet-size enforcement, and source IP allow-listing remain parser/listener responsibilities.

2. Route performs independent validation.

   The listener and parser are not sufficient trust boundaries. The route must validate JSON shape, required normalized fields, source/source_type, event type, severity, source IP, message, app name, environment, and safe `raw_payload` structure before calling centralized ingest.

3. Use existing ingest API-key guard.

   `POST /ingest/pfsense` should use the current ingest API-key pattern unless a later security decision introduces a pfSense-specific key. Missing or invalid keys must reject before processing.

4. Preserve centralized ingest and post-commit orchestration.

   The route should call `ingest_normalized_event` or the equivalent current centralized ingest function for database insertion and detection/correlation. It should reuse the existing route-level post-commit playbook scheduling, queue enqueueing, and incident creation pattern so pfSense events do not bypass current SOAR behavior.

5. Keep responses safe and bounded.

   Success responses may include existing structured alert summaries, but validation errors must not echo full payloads, raw syslog, attacker-controlled summaries, stack traces, or internal exception details.

6. Keep parser and route tests separate.

   Parser unit tests should continue to exercise parser behavior directly. Route/API tests for this child should focus on authentication, schema validation, centralized ingest calls, safe responses, and orchestration behavior.

## Risks / Trade-offs

- [Risk] The current valid event-type allowlist may not include `firewall_block` / `firewall_allow` -> Mitigation: the future implementation should update route validation narrowly for the pfSense route without changing unrelated event semantics.
- [Risk] Route validation duplicates some parser checks -> Mitigation: duplicate only trust-boundary checks required to prevent malformed or forged listener payloads from entering centralized ingest.
- [Risk] Existing route orchestration is duplicated across ingest endpoints -> Mitigation: follow existing patterns first; extract a helper only if implementation can do so without unrelated refactor churn.
- [Risk] Request-size enforcement may depend on app-level Flask configuration -> Mitigation: require a bounded request-size strategy when supported by existing app patterns and verify through API tests where feasible.

## Open Questions

- Whether `/ingest/pfsense` should use the shared ingest API key or a pfSense-specific key remains open for future implementation; this spec requires at least the existing API-key guard.
- Final severity policy for `firewall_block` and `firewall_allow` remains tied to the parser contract and later detection/taxonomy specs.
