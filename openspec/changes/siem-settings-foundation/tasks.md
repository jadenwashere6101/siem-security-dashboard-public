## 1. Scope Confirmation

- [ ] 1.1 Confirm this child spec belongs under the parent roadmap `openspec/changes/siem-settings-roadmap`.
- [ ] 1.2 Confirm implementation scope is frontend-only.
- [ ] 1.3 Confirm no backend APIs are added.
- [ ] 1.4 Confirm no database tables or migrations are added.
- [ ] 1.5 Confirm no authentication/session changes are added.
- [ ] 1.6 Confirm no light/dark theme setting is added.
- [ ] 1.7 Confirm default behavior stays Dashboard landing plus 5 second auto-refresh unless the user changes settings.

## 2. Settings Storage Foundation

- [ ] 2.1 Add a dedicated frontend settings module.
- [ ] 2.2 Define a stable localStorage key for SIEM UI settings.
- [ ] 2.3 Define a versioned settings object shape.
- [ ] 2.4 Define default settings:
  - `defaultLandingPage: "dashboard"`
  - `autoRefreshIntervalMs: 5000`
- [ ] 2.5 Define allowed auto-refresh values: `0`, `5000`, `10000`, `30000`, `60000`.
- [ ] 2.6 Add settings read helper that returns defaults when localStorage is missing.
- [ ] 2.7 Add settings read helper behavior for malformed JSON.
- [ ] 2.8 Add settings validation for invalid setting values.
- [ ] 2.9 Add partial merge behavior so valid stored settings survive while invalid/missing keys fall back to defaults.
- [ ] 2.10 Add write helper that persists only supported settings.
- [ ] 2.11 Ensure localStorage read/write exceptions do not crash the app.
- [ ] 2.12 Keep the storage shape extensible for later child specs.

## 3. Settings Initialization Flow

- [ ] 3.1 Load settings during authenticated app initialization.
- [ ] 3.2 Apply default settings automatically when localStorage is empty.
- [ ] 3.3 Reset to safe defaults when localStorage is corrupted.
- [ ] 3.4 Use `defaultLandingPage` only when the target section exists and is visible for the current role.
- [ ] 3.5 Fall back to Dashboard when the stored landing page is invalid, hidden, or unavailable.
- [ ] 3.6 Ensure settings initialization does not block or alter authentication checks.
- [ ] 3.7 Ensure logout does not need to clear settings because v1 settings are browser-local preferences.

## 4. Sidebar And Settings UI

- [ ] 4.1 Add a Settings entry/category to the existing sidebar navigation config.
- [ ] 4.2 Make Settings visible to authenticated users.
- [ ] 4.3 Render a Settings section when selected.
- [ ] 4.4 Add a default landing page control.
- [ ] 4.5 Add an auto-refresh interval control with Off, 5 sec, 10 sec, 30 sec, and 60 sec.
- [ ] 4.6 Persist setting changes through the settings storage module.
- [ ] 4.7 Use the existing dark UI style.
- [ ] 4.8 Do not add theme controls.
- [ ] 4.9 Keep non-settings UI behavior unchanged.

## 5. Auto-Refresh Integration

- [ ] 5.1 Replace the main hard-coded 5 second polling interval with the settings-driven interval.
- [ ] 5.2 Preserve the default 5 second behavior when settings are absent.
- [ ] 5.3 Support Off by disabling automatic polling controlled by this setting.
- [ ] 5.4 Clear and recreate timers when the setting changes.
- [ ] 5.5 Avoid duplicate or stale timers.
- [ ] 5.6 Decide whether this foundation applies to both main alerts and Live Logs pollers during implementation; if only one poller is included, document the reason before implementation.

## 6. Tests To Add During Implementation

- [ ] 6.1 Unit test settings defaults when localStorage is missing.
- [ ] 6.2 Unit test malformed JSON fallback.
- [ ] 6.3 Unit test invalid values fallback.
- [ ] 6.4 Unit test partial valid settings merge with defaults.
- [ ] 6.5 Unit test localStorage read/write exception handling.
- [ ] 6.6 Component test Settings sidebar visibility.
- [ ] 6.7 Component test default landing page persistence and invalid/hidden fallback to Dashboard.
- [ ] 6.8 Component test auto-refresh interval options.
- [ ] 6.9 Component test Off disables automatic polling.
- [ ] 6.10 Regression test default behavior remains Dashboard landing plus 5 second refresh.
- [ ] 6.11 Regression test no light/dark theme setting appears.

## 7. Validation To Run During Implementation

- [ ] 7.1 Run focused frontend tests for the new settings storage module.
- [ ] 7.2 Run focused frontend tests for sidebar/settings rendering.
- [ ] 7.3 Run focused frontend tests for refresh interval behavior with fake timers.
- [ ] 7.4 Run existing sidebar preference tests.
- [ ] 7.5 Run existing Live Logs tests if Live Logs polling is wired to the global interval.
- [ ] 7.6 Run `npm test -- --watchAll=false` from `frontend/` if practical for the implementation change.
- [ ] 7.7 Run `git diff --check`.

## 8. Out Of Scope

- [ ] 8.1 Do not add backend settings APIs.
- [ ] 8.2 Do not add database persistence.
- [ ] 8.3 Do not add migrations.
- [ ] 8.4 Do not change authentication or RBAC.
- [ ] 8.5 Do not add theme switching.
- [ ] 8.6 Do not implement display preferences from `siem-display-preferences`.
- [ ] 8.7 Do not implement alert sound or browser notification preferences from `siem-alert-notification-preferences`.
- [ ] 8.8 Do not touch the VM.
