## Why

Current base detectors are selected by event type, but most historical aggregation queries do not constrain `source` and `source_type`; supported sources can therefore contribute to one another's thresholds and alerts can inherit the triggering event's source rather than the evidence source. The existing database-backed `active` flag is also returned by configuration APIs but is not enforced during detector execution.

## What Changes

- Define the authoritative `(source, source_type)` identities for Honeypot, Bank App, pfSense, NGINX, Azure Application Insights, and OpenTelemetry.
- Define explicit source applicability for every current base detector and expose that static coverage alongside effective runtime configuration.
- Require both dispatch-time applicability and matching historical-event source predicates so unsupported or unknown sources neither execute nor contribute to a detector.
- Keep each supported source pair's threshold/window aggregation isolated and make created alerts retain truthful source evidence.
- Enforce `detection_config.active`; an inactive base detector performs no historical query and creates no alert.
- Preserve existing global threshold/window overrides and the intentionally cross-source alert correlation rules.
- Extend the super-admin Detection Rules API and UI minimally to show effective active state and applicable sources, and permit audited active-state updates.
- Add focused backend, API, frontend, regression, build, accessibility, dark-theme, and deployment-verification coverage.
- Exclude per-source tuning, new rules, distributed detection, noise tuning, MITRE changes, playbook redesign, plugin discovery, and pfSense tuning.

## Capabilities

### New Capabilities

- `source-aware-detection-evaluation`: Defines canonical telemetry identities, complete base-rule applicability, isolated historical aggregation, truthful alert attribution, active-state enforcement, and Detection Rules visibility.

### Modified Capabilities

None. No current top-level capability spec owns base detection applicability or Detection Rules administration.

## Impact

- Backend: normalized-source constants, ingest dispatch, detector query predicates, detection configuration, admin API, and alert attribution.
- Frontend: Detection Rules service/panel and focused tests.
- Data: existing `events`, `alerts`, and `detection_config` schemas remain sufficient; no data rewrite is expected.
- Correlation/SOAR: correlation matching and playbook contracts remain behaviorally unchanged, but receive more accurately attributed base alerts.
- Operations: Mac AI owns implementation and verification; VM AI owns only explicitly authorized deployment and production verification after an approved commit.
