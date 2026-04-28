# Web Log Detection Phase 2.5 Spec

## Feature Overview

This change extends detection so nginx/web-log events can generate alerts, not just be stored.

The goal is to complete the web-log ingestion loop by allowing normalized web-log events to participate in the existing alerting pipeline while preserving the current bank app ingestion and detection behavior.

## Current State

- Phase 2 added `POST /ingest/web-log`
- nginx logs normalize into:
  - `unauthorized_access` for HTTP `401` / `403`
  - `http_error` for HTTP `5xx`
  - `normal_activity` for HTTP `2xx` / `3xx`
- Events are stored with:
  - `source = "nginx"`
  - `source_type = "web_log"`
- The existing detection engine already handles:
  - failed login threshold
  - password spraying
  - port scan
  - successful login after spray

## Requirements

1. Extend failed-login / brute-force threshold detection to include `unauthorized_access`.
   - `unauthorized_access` should count alongside `failed_login` and `login_failure` where appropriate.
   - Preserve the existing threshold and window config behavior.

2. Add a simple `http_error` threshold detector.
   - Detect repeated `http_error` events from the same `source_ip` within a configurable time window.
   - Use constants first, following the existing detection-rule pattern:
     - `HTTP_ERROR_THRESHOLD = 5`
     - `HTTP_ERROR_WINDOW_MINUTES = 15`

3. Detection config integration:
   - Add `http_error_threshold` to detection config metadata only if the current detection-config system supports it safely without broadening scope too much.
   - If metadata/config integration is too risky for this phase, keep constants only and document that limitation.

4. Generate alert for repeated HTTP server errors:
   - `alert_type = http_error_threshold`
   - `severity = medium` or `high`
   - `message = repeated HTTP server errors detected from <source_ip>`

5. Preserve duplicate alert suppression.
   - Do not create duplicate open alerts for the same `alert_type` and `source_ip`.

6. Do not implement `high_request_rate` in this phase.
   - `high_request_rate` remains a future detector.

7. Do not change:
   - `/ingest` behavior
   - bank app integration
   - web-log parser behavior
   - schema unless clearly required
   - frontend unless needed only to display already-existing alert data

8. Add MITRE mapping only if there is an appropriate and defensible existing pattern; otherwise leave it out in this phase.

## Non-Goals

- No `high_request_rate` detector
- No parser redesign
- No bank app changes
- No `/ingest` contract changes
- No schema redesign
- No broad detection engine rewrite
- No frontend redesign
- No new batch web-log ingestion behavior

## Acceptance Criteria

1. `401` / `403` nginx logs can contribute to threshold-based unauthorized access alerts.
2. Repeated `5xx` nginx logs generate `http_error_threshold` alerts.
3. Duplicate open alerts are not created.
4. Existing bank app failed-login detection still works.
5. `high_request_rate` is not implemented.
6. Syntax check passes.

## Risks and Mitigations

- Risk: accidentally changing existing failed-login detector behavior
  - Mitigation: extend the counted event set narrowly and preserve the current threshold/window logic and dispatch order

- Risk: duplicate alert generation
  - Mitigation: reuse the same duplicate-open-alert suppression pattern already used by existing detectors

- Risk: over-alerting from normal server instability or noisy `5xx` bursts
  - Mitigation: keep the initial threshold conservative, start with constants, and avoid broader config work unless clearly safe

- Risk: mixing `high_request_rate` into this phase
  - Mitigation: explicitly exclude it from implementation and keep this phase scoped to `unauthorized_access` and `http_error`

- Risk: detection config integration becomes too broad
  - Mitigation: treat `http_error_threshold` config integration as optional in this phase and fall back to constants-only if integration expands scope too much

- Risk: MITRE mapping becomes forced or low quality
  - Mitigation: only add a mapping if there is a defensible existing pattern; otherwise leave it out for now
