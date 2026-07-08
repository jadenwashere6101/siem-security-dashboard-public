## 1. Overall Goal

Track the full SIEM Settings feature suite from audit through future child implementation specs without implementing code, creating child specs, modifying application source files, modifying tests, touching the VM, committing, or pushing.

## 2. Hard Guardrails

- [x] 2.1 Confirm this is parent roadmap creation only.
- [x] 2.2 Confirm no application source files are modified.
- [x] 2.3 Confirm no tests are modified.
- [x] 2.4 Confirm no child implementation specs are created.
- [x] 2.5 Confirm no VM access or VM source edits are performed.
- [x] 2.6 Confirm no commits or pushes are performed.
- [x] 2.7 Confirm the current dark UI remains the default.
- [x] 2.8 Confirm no light/dark theme switch is included or planned.

## 3. Phase 0 - Audit

- [x] 3.1 Audit sidebar/category/navigation patterns.
  - Finding: navigation is centralized in `sectionsConfig` and rendered by grouped sidebar components.
- [x] 3.2 Audit existing user/auth/session storage.
  - Finding: session identity uses sessionStorage; sidebar collapsed state uses localStorage; backend auth exposes username/role but no settings API.
- [x] 3.3 Audit settings storage options.
  - Finding: v1 should use localStorage; backend DB/user-scoped settings should be future expansion only.
- [x] 3.4 Audit timestamp rendering helpers.
  - Finding: timestamp rendering is fragmented across raw strings, UTC formatters, and browser-local formatting.
- [x] 3.5 Audit polling/refresh logic.
  - Finding: main alerts and Live Logs have separate hard-coded 5 second pollers.
- [x] 3.6 Audit Live Logs components.
  - Finding: Live Logs already has Event Feed, Raw Log, and JSON modes with a separate poller and raw text rendering.
- [x] 3.7 Audit Alerts/Dashboard/Incidents tables.
  - Finding: tables are component-specific; column visibility must start with a practical v1 subset.
- [x] 3.8 Audit notification/audio support.
  - Finding: no browser Notification API or alert audio support was found.
- [x] 3.9 Audit existing frontend tests.
  - Finding: reusable tests exist for sidebar, localStorage preference handling, Live Logs, Alerts, Incidents, and service behavior.
- [x] 3.10 Record risks and unknowns in the roadmap.

## 4. Phase 1 - Child Spec Creation

- [x] 4.1 Create `siem-settings-foundation`.
  - Scope: Settings sidebar/section, localStorage settings model, default values, malformed localStorage handling, default landing page, auto-refresh interval.
- [x] 4.2 Create `siem-display-preferences`.
  - Scope: timezone display, timestamp format, rows per page/event limit, Live Logs font size, default Live Logs view, severity color presets, column visibility, Live Log highlighting rules.
- [x] 4.3 Create `siem-alert-notification-preferences`.
  - Scope: alert sound preference, browser notification preference, mocked Notification/audio tests, future alert-trigger integration.
- [x] 4.4 Confirm each child spec repeats the dark-mode-only boundary and excludes a light/dark theme switch.
- [x] 4.5 Confirm each child spec states which settings are frontend-only and which require backend support.

## 5. Phase 2 - Implementation Sequencing

- [x] 5.1 Implement `siem-settings-foundation` first.
  - Reason: later specs should reuse the settings store, defaults, and Settings section.
- [x] 5.2 Implement `siem-display-preferences` second.
  - Reason: display preferences depend on shared settings access and default preservation.
- [x] 5.3 Implement `siem-alert-notification-preferences` third.
  - Reason: notification/audio preferences require careful browser API mocking and future trigger definition.
- [x] 5.4 Defer backend/user-scoped settings until localStorage v1 behavior is validated.
- [x] 5.5 Keep each child implementation separately validated before starting the next child implementation.

### V1 Settings Implementation Status

- [x] `siem-settings-foundation` complete.
- [x] `siem-display-preferences` complete.
- [x] `siem-alert-notification-preferences` complete.
- [x] Backend/user-scoped expansion deferred.

## 6. Phase 3 - Validation Plan

- [x] 6.1 Validate settings storage defaults and malformed localStorage fallback.
  - Validated by settings storage tests for defaults, malformed JSON, invalid values, partial merge, and notification preference fallback.
- [x] 6.2 Validate Settings sidebar visibility and navigation behavior.
  - Validated by Settings nav/App tests for viewer access and Settings panel rendering.
- [x] 6.3 Validate default landing page behavior for visible and hidden/role-gated sections.
  - Validated by App tests for visible stored landing pages and hidden-role fallback to Dashboard.
- [x] 6.4 Validate auto-refresh intervals, including Off, across main alerts and Live Logs.
  - Validated by frontend tests for Off behavior and settings-driven refresh behavior.
- [x] 6.5 Validate timestamp formatting for UTC/local and relative/absolute behavior.
  - Validated by display formatting tests from the display preferences implementation.
- [x] 6.6 Validate Live Logs default view, font size, event limit, and highlighting behavior.
  - Validated by Live Logs display preference tests from the display preferences implementation.
- [x] 6.7 Validate severity color presets after style centralization.
  - Validated by severity/display preference tests after centralizing severity styles.
- [x] 6.8 Validate practical column visibility settings for selected tables.
  - Validated by frontend table visibility tests for selected Settings-managed tables.
- [x] 6.9 Validate mocked browser `Notification` permission states and audio playback behavior.
  - Validated by SettingsPanel tests with mocked Notification granted, denied, default, unavailable/error states, and mocked audio playback.
- [x] 6.10 Run child-specific frontend tests.
  - Completed across foundation, display preferences, and alert notification preferences.
- [x] 6.11 Run backend tests only if a child spec adds backend APIs, schema, or query limits.
  - Not required for v1. Implemented settings specs were frontend/localStorage only and added no backend APIs, schema, or query limits.

## 7. Phase 4 - Deployment / Rebuild

- [ ] 7.1 Confirm parent roadmap/spec-only work requires no VM sync.
- [ ] 7.2 For future frontend-only implementation, build on the Mac and deploy only the frontend build output when deployment is requested.
- [ ] 7.3 For future backend changes, run backend validation, migration checks if applicable, and follow the Mac/VM source-of-truth policy.
- [ ] 7.4 Before any future VM deployment sync, verify the VM working tree is clean.
- [ ] 7.5 Do not edit source code on the VM.

## 8. Phase 5 - Future Backend / User-Preference Expansion

- [x] 8.1 Decide whether settings need to follow users across browsers/devices.
  - Status: Not required for v1. V1 settings remain localStorage/browser-local.
- [ ] 8.2 If yes, create a separate backend child spec for user-scoped settings.
  - Deferred/not applicable for v1. No backend child spec is required now.
- [ ] 8.3 Scope any settings table, migration, settings API, RBAC, audit behavior, and fallback/merge behavior.
  - Deferred/not applicable for v1. These belong to a future backend settings spec only if cross-device/user-scoped settings become required.
- [ ] 8.4 Scope backend-supported event limits or alert pagination separately from frontend-only visible-row limits.
  - Deferred/future. V1 uses frontend-visible row limits only.
- [ ] 8.5 Scope durable alert-trigger behavior for real sound/browser notifications before enabling repeated notifications.
  - Deferred/future. V1 only includes preferences and test buttons, not real alert-triggered notification delivery.

## Safety Boundaries

- [x] This parent change contains no implementation steps that authorize source edits.
- [x] Do not modify application source files.
- [x] Do not modify tests.
- [x] Do not create child implementation specs as part of this parent roadmap.
- [x] Do not touch the VM.
- [x] Do not commit.
- [x] Do not push.
