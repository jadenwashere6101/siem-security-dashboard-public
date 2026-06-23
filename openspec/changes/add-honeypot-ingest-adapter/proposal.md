## Why

### Problem

The Flask honeypot emits flat, honeypot-native telemetry, while the SIEM ingestion pipeline expects normalized SIEM events. Sending honeypot payloads directly to the standard `/ingest` route would force the honeypot to know SIEM internals and increases the risk of unsafe credential handling.

### Goals

- Add a dedicated `POST /ingest/honeypot` adapter endpoint.
- Accept flat honeypot-native payloads and normalize them into the existing `ingest_normalized_event()` contract.
- Stamp `source="honeypot"` and `source_type="honeypot"` internally.
- Preserve honeypot metadata in `raw_payload` without storing raw passwords.
- Preserve existing detection, correlation, SOAR enqueue, approval, playbook, queue, and schema behavior.

### Non-Goals

- No honeypot route or companion repo changes.
- No frontend changes.
- No SOAR worker, playbook, queue, approval, protected-target, or integration adapter changes.
- No database schema changes.
- No correlation behavior changes.

## What Changes

- Add a new authenticated SIEM route: `POST /ingest/honeypot`.
- Accept honeypot event types: `env_probe`, `admin_probe`, `scanner_detected`, `credential_stuffing`, and `http_error`.
- Map flat honeypot payloads to normalized SIEM event dictionaries.
- Map `timestamp` to `event_timestamp`.
- Generate `severity`, `message`, `app_name`, and `environment`.
- Preserve honeypot-specific fields and future metadata in `raw_payload`.
- Reject raw password fields before storage or forwarding into the normalized ingest pipeline.

## Capabilities

### New Capabilities

- `honeypot-ingest-adapter`: Dedicated authenticated adapter endpoint for normalizing flat honeypot telemetry into the SIEM ingestion pipeline.

### Modified Capabilities

None.

## Impact

- Backend API: one new ingest route in the existing ingest blueprint.
- Backend normalization: new adapter-specific payload validation and mapping.
- Tests: focused route contract, authentication, normalization, password rejection, and post-commit handoff coverage.
- Detection/SOAR/schema: no direct behavior changes; the adapter reuses the existing normalized ingest path.

## User-Visible Behavior

Operators can point the Flask honeypot at `/ingest/honeypot` instead of shaping payloads for the generic `/ingest` endpoint. Honeypot events appear in SIEM storage and alerts as `source="honeypot"` and `source_type="honeypot"` when detections fire through the existing pipeline.

## Risks

- A loose adapter could accidentally store raw credentials if password rejection is incomplete.
- If `http_error` is translated to a non-error event type, existing HTTP error detection could be bypassed.
- Adapter-generated severity and message text must be deterministic so tests and analyst workflows remain clear.
- Future honeypot metadata must be preserved without allowing unsafe keys.

## Rollback Plan

Remove the `/ingest/honeypot` route, adapter validation/mapping helpers, and focused tests. Because this change does not require schema, SOAR, approval, playbook, queue, or frontend changes, rollback should be limited to the route and helper surface.
