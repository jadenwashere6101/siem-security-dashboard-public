## Why

The SIEM UI needs a visible Settings section that can coordinate future operator preferences without changing current dashboard behavior by default. Because the requested settings span navigation, timestamps, polling, Live Logs, tables, colors, and browser notification APIs, this parent roadmap keeps the suite scoped and sequenced before child implementation specs are created.

## What Changes

- Add a coordination-only parent roadmap for `siem-settings-roadmap`.
- Track the future child specs:
  - `siem-settings-foundation`
  - `siem-display-preferences`
  - `siem-alert-notification-preferences`
- Record scope boundaries:
  - The SIEM UI remains dark mode only.
  - No light/dark theme switch will be added.
  - Defaults must preserve the current UI look and behavior unless the user changes a setting.
  - v1 settings should use frontend localStorage.
  - Backend DB/user-scoped settings are out of scope for v1 unless a child spec explicitly adds them.
- Track audit findings, risks, unknowns, sequencing, validation, deployment/rebuild planning, and future backend/user-preference expansion.
- Do not implement code, create child specs, modify source files, modify tests, touch the VM, commit, or push.

## Capabilities

### New Capabilities
- `siem-settings-roadmap`: tracks the parent coordination plan, scope boundaries, child-spec sequencing, storage recommendations, validation gates, deployment/rebuild notes, and risks/unknowns for the SIEM Settings feature suite.

### Modified Capabilities
(none - this parent roadmap does not change existing runtime behavior)

## Impact

- **Affected code:** none. This change must not touch application source files under `frontend/`, `core/`, `routes/`, `engines/`, `helpers/`, `scripts/`, `migrations/`, or tests.
- **Affected artifacts:** adds `openspec/changes/siem-settings-roadmap/`.
- **Runtime behavior:** none. Current dark-mode UI behavior remains unchanged.
- **Downstream work:** child implementation specs will be created later and will own implementation details, testing, and any optional backend persistence scope.
