## Why

pfSense firewall events can now enter the centralized ingestion pipeline through the parser, route, and listener child specs. The next boundary is defining how those already-ingested firewall events become alerts, correlations, MITRE-enriched detections, and SOAR candidates without changing parsing, transport, deployment, or runtime exposure behavior.

## What Changes

- Define the firewall event taxonomy for `source="pfsense"` and `source_type="firewall"` events after ingestion.
- Define `firewall_block` versus `firewall_allow` behavior and how each maps to alerts.
- Define severity guidance, expected alert fields, expected `response_action` values, and MITRE mapping expectations.
- Define correlation opportunities for port scans, repeated denies, noisy sources, allow-after-deny patterns, and related source-IP context.
- Define SOAR playbook trigger expectations and approval workflow expectations for firewall-driven alerts.
- Define validation strategy and acceptance criteria for later implementation.
- Keep this child scope to detections and SOAR behavior only after pfSense events have already entered centralized ingest.

## Capabilities

### New Capabilities
- `pfsense-firewall-detections-soar`: firewall detection taxonomy, alert mapping, correlation, and SOAR behavior for already-ingested pfSense firewall events.

### Modified Capabilities
- (none)

## Impact

- **Affected code later:** likely detection/correlation rules, alert enrichment, playbook trigger mapping, SOAR queue metadata, and focused tests.
- **Affected APIs later:** existing ingest and SOAR behavior may emit richer firewall alerts, but this spec does not add ingestion endpoints.
- **Affected systems now:** none. This spec creation does not modify application source files, create tests, touch the VM, deploy services, open ports, or perform runtime validation.
- **Dependencies:** depends on normalized pfSense events entering the centralized pipeline through the parser, route, and listener contracts.
- **Parent roadmap:** item 6.11 is marked created with a detections/SOAR-only boundary note.
