# High Request Rate Detector Spec

## Feature Overview

This change adds a `high_request_rate_threshold` detector for burst traffic from web and telemetry sources.

The goal is to detect suspicious short-window request spikes from the same `source_ip` using normalized nginx and OpenTelemetry events, while keeping this logic separate from earlier web-log ingestion work.

## Current State

- nginx web logs ingest through `POST /ingest/web-log`
- OpenTelemetry JSON ingests through `POST /ingest/otlp`
- Events include:
  - `source`
  - `source_type`
- `high_request_rate` was intentionally skipped in earlier phases and has not yet been implemented
- Existing detectors currently cover:
  - failed login threshold
  - password spraying
  - successful login after spray
  - port scan
  - http error threshold

## Requirements

1. Add a new detector:
   - `high_request_rate_threshold`

2. Count request-style events from the same `source_ip` within a time window.

3. Initial constants:
   - `HIGH_REQUEST_RATE_THRESHOLD = 20`
   - `HIGH_REQUEST_RATE_WINDOW_MINUTES = 5`

4. Event types counted:
   - `normal_activity`
   - `unauthorized_access`
   - `http_error`

5. Source types counted:
   - `web_log`
   - `telemetry`

6. Generate alert:
   - `alert_type = high_request_rate_threshold`
   - `severity = medium` or `high`
   - `message = high request rate detected from <source_ip>`

7. Preserve duplicate alert suppression:
   - do not create duplicate open alerts for the same `alert_type` and `source_ip`

8. Trigger the detector after relevant nginx and OTEL events are ingested.

9. Include `source` and `source_type` on created alerts.

10. Do not:
   - change ingestion endpoints
   - change parsers or adapters
   - change schema unless clearly required
   - change bank app behavior
   - change existing detection rules
   - change frontend

## Non-Goals

- No parser changes
- No endpoint changes
- No schema redesign
- No frontend work
- No bank app traffic counting
- No automatic blocking or firewall action changes
- No rate-limiting policy changes
- No analytics dashboard redesign

## Acceptance Criteria

1. A burst of 20 request-style nginx events from the same IP in 5 minutes creates an alert.
2. A burst of 20 request-style OTEL events from the same IP in 5 minutes creates an alert.
3. Duplicate open alerts are not created.
4. Bank app failed-login detection still works.
5. Existing nginx, Azure, and OTEL ingestion still works.
6. Syntax check passes.

## Risks and Mitigations

- Risk: alert noise from legitimate traffic bursts
  - Mitigation: keep the first threshold conservative and narrowly scope counted sources to `web_log` and `telemetry`

- Risk: duplicate alert generation
  - Mitigation: reuse the existing duplicate-open-alert suppression pattern already used by other detectors

- Risk: accidentally counting bank app `normal_activity`
  - Mitigation: explicitly filter by `source_type IN ('web_log', 'telemetry')`

- Risk: performance impact from request-count queries
  - Mitigation: keep the query window narrow and reuse the existing threshold-detector query pattern

- Risk: confusion between detection and enforcement
  - Mitigation: keep this phase detection-only; alerting is separate from firewall blocking or active mitigation
