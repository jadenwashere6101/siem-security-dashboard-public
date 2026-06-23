## Why

### Problem

The SIEM is preparing to receive security telemetry from a separate Flask honeypot companion project, but the current ingest whitelist and detection dispatch do not recognize honeypot-specific events. Without SIEM-side preparation, honeypot traffic could be rejected, stored without detection, or routed inconsistently through the existing alert and SOAR handoff flow.

### Goals

- Accept honeypot event types through the SIEM ingest path.
- Store honeypot metadata safely without raw passwords or schema changes unless implementation proves they are unavoidable.
- Detect sensitive-path probing, admin-path probing, scanner activity, and credential stuffing.
- Keep all honeypot rule defaults configurable through the existing `detection_config` runtime configuration model.
- Preserve existing alert creation, correlation, incident, SOAR enqueue, playbook scheduling, and dashboard runtime configurability behavior.

### Non-Goals

- Do not create or deploy the Flask honeypot repo.
- Do not open Azure ports, change VM services, or modify deployment topology.
- Do not change SOAR worker, playbook, approval gate, protected-target, or adapter behavior.
- Do not change frontend behavior unless implementation later proves backend runtime config surfaces cannot already display the new rules.
- Do not change integration adapter behavior in this phase.

## What Changes

- Add `env_probe`, `admin_probe`, `scanner_detected`, and `credential_stuffing` to the accepted SIEM event type set.
- Add detection dispatch for the new event types in the normalized ingest pipeline.
- Add four runtime-configurable detection rule defaults:
  - `honeypot_env_probe_threshold`
  - `honeypot_admin_probe_threshold`
  - `honeypot_scanner_detected`
  - `honeypot_credential_stuffing_threshold`
- Add detection logic that queries safe metadata in `events.raw_payload`.
- Add focused tests for ingest acceptance, storage, detection thresholds, password rejection, and SOAR handoff preservation.

## Capabilities

### New Capabilities

- `honeypot-event-detections`: SIEM-side support for accepting, storing, detecting, configuring, and testing honeypot event telemetry.

### Modified Capabilities

None.

## Impact

- Backend ingest: event whitelist and normalized dispatch.
- Backend detection: new detection functions and rule defaults.
- Backend tests: focused ingest and detection coverage for honeypot events.
- Data model: expected to reuse existing `events.raw_payload`; no schema migration planned.
- SOAR: no direct behavior change. Honeypot alerts use the existing alert creation return path so post-commit enqueue and playbook scheduling continue normally.

## User-Visible Behavior

Operators can ingest honeypot events and see resulting alerts with `source="honeypot"` and `source_type="honeypot"` when the ingest adapter stamps those fields. Runtime detection rule configuration should expose the new rules through the existing detection rules surface if it already renders backend rule defaults generically.

## Risks

- JSONB queries over `raw_payload` are flexible but less indexed than dedicated columns.
- Weak path normalization could either miss equivalent paths or overcount noisy variants.
- Scanner signatures can drift, so the initial rule may need tuning after real traffic.
- Credential payloads are high-risk because bots may submit real breached passwords; tests must prove raw `password` fields are rejected.

## Rollback Plan

Revert the whitelist additions, dispatch entries, detection rule defaults, detection functions, and focused tests for this change. Because the proposal avoids schema changes, rollback should not require database migration rollback.
