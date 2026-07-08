## Why

The Settings UI needs local browser notification and alert sound preferences before any future live-alert notification integration is designed. This phase gives operators preference controls and safe test buttons while keeping existing SIEM alert behavior unchanged.

## What Changes

- Add Settings controls for alert sound preferences.
- Add Settings controls for browser notification preferences.
- Persist notification and audio preferences through the existing localStorage-backed UI settings model.
- Add browser Notification API permission handling for granted, denied, default, unavailable, and error states.
- Add browser notification and alert sound test buttons that do not require or modify real alerts.
- Add deterministic frontend tests with mocked Notification API behavior and mocked audio playback.
- Explicitly defer live alert-triggered notification/audio behavior to a future phase.

## Capabilities

### New Capabilities
- `siem-alert-notification-preferences`: provides frontend-only notification and alert sound preference controls, localStorage persistence, browser permission handling, test buttons, and mocked frontend validation without live alert integration.

### Modified Capabilities
(none - this change does not alter backend notification delivery, alert creation, detections, SOAR, ingestion, or existing runtime alert behavior)

## Impact

- **Affected frontend:** UI settings storage, SettingsPanel controls, browser API helper logic, and frontend tests.
- **Affected backend:** none.
- **Affected database/migrations:** none.
- **Affected auth/session:** none.
- **Runtime alert behavior:** unchanged. Preferences and test buttons do not trigger from live alerts in this phase.
