## Why

pfSense detections are now technically richer than the operational surfaces that present them. Routine blocked traffic can still surface as high-urgency work through alert severity, automatic incident creation, and aggregate dashboards, while older pre-tuning pfSense noise remains mixed into current counts and recent-work views.

## What Changes

- Normalize pfSense severity defaults so routine commodity firewall noise is not presented as `high` or `critical`.
- Keep the existing runtime threshold override system and scope this change to severity logic, severity-to-incident propagation, and operational filtering behavior.
- Introduce a configurable tuning baseline timestamp that operational pfSense views use by default as `Since Tuning`, with an explicit `All History` option.
- Add clear legacy/pre-tuning indicators for pfSense alerts and incidents created before the baseline without mutating historical data.
- Apply the baseline consistently across Dashboard, Recent Alerts, Incidents, SOC Command Center, Detection Health, alert summary APIs, and incident pressure metrics.
- Preserve all historical alerts and incidents for search and investigation without deletion, rewriting, bulk closure, or archival.

## Capabilities

### New Capabilities
- `pfsense-severity-and-operational-baseline`: normalized pfSense severity behavior and a shared operational baseline contract for current-vs-historical pfSense alerting surfaces.

### Modified Capabilities
- (none)

## Impact

- Backend detection logic: `engines/detection_engine.py` and existing pfSense rule defaults in `engines/detection_config.py`.
- Incident mapping: `routes/ingest_routes.py` and `core/incident_store.py` where alert severity becomes incident creation and priority.
- Read APIs and metrics: `routes/alerts_events_routes.py`, `routes/metrics_routes.py`, and `routes/admin_routes.py`.
- Frontend operational surfaces: Dashboard/Recent Alerts, Incidents, SOC Command Center, and Detection Health consumers.
- Migration expectation: no schema change preferred; baseline should be driven by lightweight configuration or another non-destructive mechanism.
