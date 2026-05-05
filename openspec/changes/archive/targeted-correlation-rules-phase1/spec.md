# Targeted Correlation Rules Phase 1 Spec

## Feature Overview

This change adds targeted multi-source correlation rules on top of the existing generic `correlated_activity` engine.

The goal is to detect specific, higher-confidence attack patterns using existing alerts that already represent suspicious behavior across different systems.

## Current State

- Generic multi-source correlation already works.
- `correlated_activity` alerts are created when the same IP has:
  - 2 or more qualifying alerts
  - 2 or more distinct `alert_type` values
  - 2 or more distinct known `source` values
- Correlation UI polish already exists.
- Correlation debug logging already exists.
- Current correlation is generic and does not distinguish named attack patterns.

## Requirements

Targeted rules must use existing alerts only.

1. `web_to_app_attack_pattern`
   - `alert_type = web_to_app_attack_pattern`
   - same `source_ip`
   - within 10 minutes
   - requires:
     - nginx / `web_log` alert:
       - `http_error_threshold`
       - or `high_request_rate_threshold`
     - bank app / `custom` alert:
       - `failed_login_threshold`
       - or `password_spraying_threshold`
   - severity = `critical`
   - message:
     - `Web-to-app attack pattern detected from <source_ip>`

2. `spray_then_success_pattern`
   - `alert_type = spray_then_success_pattern`
   - same `source_ip`
   - within 15 minutes
   - requires:
     - `password_spraying_threshold`
     - `successful_login_after_spray`
   - severity = `critical`
   - message:
     - `Password spray followed by successful login from <source_ip>`

3. `cloud_app_error_pattern`
   - `alert_type = cloud_app_error_pattern`
   - same `source_ip`
   - within 10 minutes
   - requires:
     - Azure / `cloud_api` alert:
       - `http_error_threshold`
       - or `application_exception`
     - nginx / `web_log` alert:
       - `http_error_threshold`
       - or `high_request_rate_threshold`
   - severity = `high`
   - message:
     - `Cloud and web application errors correlated from <source_ip>`

4. Duplicate suppression
   - do not create a new alert if an open alert of the same `alert_type` already exists for that `source_ip`

5. Rule constraints
   - use the `alerts` table, not raw events
   - preserve duplicate suppression per `alert_type + source_ip`
   - do not change generic `correlated_activity` behavior
   - do not change ingestion
   - do not change schema
   - do not change frontend
   - do not change existing detectors

6. Evaluation order
   - targeted rules are evaluated after generic `correlated_activity` evaluation
   - targeted rules do not depend on `correlated_activity` alerts
   - both alert types can coexist

7. Testing requirement
   - each rule must include a documented manual test scenario using a fresh IP
   - tests must confirm:
     - the targeted alert triggers
     - generic `correlated_activity` still triggers independently

## Non-Goals

- No raw event correlation
- No ML scoring
- No frontend changes
- No schema changes
- No automatic blocking
- No new ingestion sources
- No detector threshold changes
- No replacement of generic correlation

## Acceptance Criteria

1. `web_to_app_attack_pattern` triggers only when qualifying nginx/web and bank app alerts exist for the same IP within the rule window.
2. `spray_then_success_pattern` triggers only when `password_spraying_threshold` and `successful_login_after_spray` exist for the same IP within the rule window.
3. `cloud_app_error_pattern` triggers only when qualifying Azure and nginx/web alerts exist for the same IP within the rule window.
4. Duplicate open targeted alerts are suppressed.
5. Generic `correlated_activity` still works unchanged.
6. Syntax check passes.

## Risks and Mitigations

- Risk: targeted rules may create alert noise
  - Mitigation: keep each rule narrow, source-aware, and based only on existing high-signal alerts

- Risk: targeted pattern names may overlap semantically with generic correlation
  - Mitigation: treat targeted rules as explicit named patterns layered on top of, not replacing, generic `correlated_activity`

- Risk: `cloud_app_error_pattern` may be hard to test without real Azure-backed alerts
  - Mitigation: document a repeatable manual test path and keep the Azure-side requirements narrow

- Risk: accidental behavior changes to existing detectors
  - Mitigation: evaluate targeted rules only from the `alerts` table after detector alerts already exist, without modifying detector logic

- Risk: overlapping rules triggering multiple alerts for the same behavior
  - Mitigation: accept overlap in v1 and refine later with prioritization or additional suppression if needed
