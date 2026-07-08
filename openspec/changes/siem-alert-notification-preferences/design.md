## Overview

This change implements Phase 1 notification preferences as frontend-only Settings functionality. It extends the existing UI settings architecture and Settings panel, but does not connect preferences to real alert creation, alert polling, SOAR, detections, ingestion, backend notification delivery, or any VM/runtime service.

## Existing Architecture

- `frontend/src/utils/uiSettings.js` owns the localStorage-backed settings shape and validation.
- `frontend/src/context/UiSettingsContext.js` exposes current settings and `updateSettings`.
- `frontend/src/components/SettingsPanel.js` renders Settings controls.
- Current settings are localStorage-only and already include foundation/display preferences.

## Settings Shape

Add a `notifications` object to UI settings:

- `alertSoundsEnabled`: boolean, default `false`.
- `alertSoundVolume`: number from `0` to `1`, default `0.5`.
- `browserNotificationsEnabled`: boolean, default `false`.

Defaults must keep behavior unchanged: no real sounds and no real browser notifications unless a user explicitly tests them from Settings.

## Browser Notification Handling

Settings UI should inspect `window.Notification` safely:

- If unavailable, show a bounded unavailable message and disable or guard notification test behavior.
- If permission is `granted`, the test button may create a synthetic browser notification.
- If permission is `denied`, show a blocked message and prevent repeated failing calls.
- If permission is `default`, enabling browser notifications or pressing the test button should request permission once in a controlled way and handle the resulting state.
- Errors from constructor or permission requests should be caught and displayed near notification controls.

Test notification content must be clearly synthetic and must not reference a real alert, incident, or playbook execution.

## Alert Sound Handling

Settings UI should expose a sound enable control, volume control, and sound test button. The test button should use a browser audio primitive that can be mocked in tests, set the configured volume, and catch playback failures.

The test sound must not create, modify, resolve, or re-fire alerts.

## Persistence

Notification settings persist through the existing localStorage settings architecture. Malformed or missing notification settings fall back to defaults while preserving valid settings elsewhere.

## Out Of Scope

- Backend notification delivery.
- Backend APIs, database tables, migrations, or auth changes.
- Live alert-triggered browser notifications.
- Live alert-triggered sounds.
- WebSockets, polling changes, throttling/rate limiting, severity rules, or user profiles.
- VM, Azure, pfSense, SOAR, detections, or ingestion changes.

## Testing Direction

Add tests for:

- Default notification settings.
- Persistence and malformed fallback.
- Browser Notification `granted`, `denied`, `default`, unavailable, and error handling.
- Synthetic notification test behavior.
- Audio test playback success and failure using mocks.
- Existing SIEM behavior remaining unchanged by default.
