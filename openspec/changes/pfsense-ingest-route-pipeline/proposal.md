## Why

The parser/normalizer child spec defines safe pfSense firewall event output, but the backend still needs a dedicated ingestion route contract before any listener can post normalized events. This child spec defines the future `/ingest/pfsense` route and pipeline behavior without implementing code.

## What Changes

- Define a future `POST /ingest/pfsense` backend route for sanitized, parsed pfSense firewall events from the future listener.
- Reuse the `pfsense-filterlog-parser-normalizer` normalized event contract instead of redesigning parser behavior.
- Require the existing ingest API-key guard and route-level validation for all external payload fields.
- Require acceptance of `source="pfsense"`, `source_type="firewall"`, and firewall taxonomy candidates `firewall_block` and `firewall_allow`.
- Require the route to call the existing centralized `ingest_normalized_event` flow or equivalent current ingest function.
- Preserve existing detection, correlation, SOAR queue, playbook scheduling, and incident orchestration performed by current ingest routes.
- Require safe structured API responses and safe 4xx rejection for malformed or invalid payloads without leaking raw attacker-controlled input.
- Keep this child scope backend route/pipeline only: no UDP listener, systemd service, Azure NSG rule, VM firewall change, pfSense/uncle handoff, firewall detection implementation, SOAR tuning, parser redesign, deployment, commit, or push.

## Capabilities

### New Capabilities
- `pfsense-ingest-route-pipeline`: backend route and centralized ingest pipeline contract for normalized pfSense firewall events.

### Modified Capabilities
- (none)

## Impact

- **Affected code later:** likely `routes/ingest_routes.py` and route/API tests, plus any narrow helper needed for pfSense route validation.
- **Affected APIs later:** adds `POST /ingest/pfsense`.
- **Affected systems now:** none. This spec creation does not modify application source files, tests, runtime configuration, VM state, Azure NSG, or deployment artifacts.
- **Dependencies:** depends on the parser/normalizer contract from `pfsense-filterlog-parser-normalizer`.
- **Parent roadmap:** item 6.9 is marked created/in progress with a route/pipeline-only boundary note.
