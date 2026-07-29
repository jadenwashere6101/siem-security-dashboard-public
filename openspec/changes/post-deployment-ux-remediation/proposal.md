## Why

Post-deployment review confirmed several visible analyst-experience defects in the new Threat Brief, Investigation Drawer, sidebar, login, action feedback, and Analyst Workspace quick workflows. This change remediates those defects without reopening the broader Analyst Workspace redesign or changing production deployment/runtime behavior.

## What Changes

- Show Threat Brief only at the top of the Dashboard page and remove it from other sections.
- Fix Threat Brief card/text overflow for long alert types, source IPs, recommendations, and responsive widths.
- Ensure opening the Investigation Drawer from Alert Details closes or replaces Alert Details so only one modal surface is active.
- Preserve selected alert context, focus return, Escape/backdrop behavior, scroll containment, and responsive drawer behavior.
- Reorder sidebar groups so SOAR and Administration appear above Live Logs, with Live Logs directly above Settings.
- Remove visible application version labels from the login page and sidebar without changing package/application version metadata.
- Fix Analyst Workspace text overflow and add delete controls for notes, hypotheses, and tasks using existing APIs.
- Improve Save Investigation with loading state, success/error feedback, saved-investigation discoverability, and duplicate prevention or clear duplicate handling.
- Add consistent feedback for pin alert, save evidence, save investigation, and related workspace actions using existing notification patterns or a shared reusable pattern.
- Confirm Settings needs no new configuration entries for these remediation items.
- Keep full Analyst Workspace redesign, source-IP watch workflows, deeper associations, collaboration, advanced evidence organization, and portfolio polish out of scope.

## Capabilities

### New Capabilities

- `post-deployment-ux-remediation`: Covers targeted UX remediation for Threat Brief placement/overflow, single-overlay investigation flow, sidebar/version presentation, Analyst Workspace quick defects, Save Investigation behavior, and consistent action feedback.

### Modified Capabilities

- None.

## Impact

- Frontend: `App`, Dashboard/Threat Brief, Alert Details, Investigation Drawer, sidebar configuration/layout, login rendering, Analyst Workspace, workspace services wiring, shared action feedback, and focused tests.
- Backend/API: expected to reuse existing investigation/workspace APIs. Add a minimal backend adjustment only if reliable Save Investigation idempotency cannot be achieved safely in frontend state.
- Database/migrations: no migration expected.
- Settings: no new settings/configuration entries expected.
- Verification: focused frontend tests, accessibility/focus review, responsive/dark-theme visual review when practical, production build, `git diff --check`, and strict OpenSpec validation.
