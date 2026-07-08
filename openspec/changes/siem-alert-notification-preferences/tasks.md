## 1. Storage

- [x] 1.1 Add notification preference defaults to `DEFAULT_UI_SETTINGS`.
- [x] 1.2 Validate boolean sound/browser notification preference values.
- [x] 1.3 Validate bounded alert sound volume.
- [x] 1.4 Merge valid notification settings with defaults when storage is partial.
- [x] 1.5 Fall back safely when notification settings are malformed.

## 2. Settings UI

- [x] 2.1 Add alert sound enable/disable control.
- [x] 2.2 Add alert sound volume control.
- [x] 2.3 Add alert sound test button.
- [x] 2.4 Add browser notification enable/disable control.
- [x] 2.5 Add browser notification test button.
- [x] 2.6 Add bounded status/error messages for notification and audio tests.
- [x] 2.7 Keep controls in the existing dark Settings UI.

## 3. Browser API Handling

- [x] 3.1 Handle Notification API unavailable state.
- [x] 3.2 Handle `granted` permission state.
- [x] 3.3 Handle `denied` permission state.
- [x] 3.4 Handle `default` permission state by requesting permission in a controlled flow.
- [x] 3.5 Catch Notification constructor and permission request errors.
- [x] 3.6 Use synthetic test notification content only.

## 4. Audio Test Handling

- [x] 4.1 Add a mockable audio playback helper.
- [x] 4.2 Apply configured volume to the test sound.
- [x] 4.3 Catch playback failures without crashing.
- [x] 4.4 Ensure sound test does not depend on or mutate real alerts.

## 5. Tests

- [x] 5.1 Add storage tests for notification defaults and validation.
- [x] 5.2 Add Settings UI tests for notification controls.
- [x] 5.3 Add mocked Notification API tests for granted, denied, default, unavailable, and error states.
- [x] 5.4 Add mocked audio playback tests for success and failure.
- [x] 5.5 Update existing Settings assertions to reflect the new approved controls.

## 6. Validation

- [x] 6.1 Run relevant frontend tests.
- [x] 6.2 Run `openspec validate siem-alert-notification-preferences --strict`.
- [x] 6.3 Run `git diff --check`.

## 7. Scope Boundaries

- [x] 7.1 Confirm no backend APIs were added.
- [x] 7.2 Confirm no database tables or migrations were added.
- [x] 7.3 Confirm no live alert-triggered notification integration was added.
- [x] 7.4 Confirm VM, Azure, pfSense, SOAR, detections, and ingestion were not touched.
