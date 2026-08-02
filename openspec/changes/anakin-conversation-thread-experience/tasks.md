## 1. Audit And Architecture

- [x] 1.1 Read source-of-truth, production acceptance, verification, foundation, and orchestration materials.
- [x] 1.2 Audit every mounted Anakin entry point, response surface, thread API, overlay owner, and async recovery path.
- [x] 1.3 Reproduce and capture the dashboard control ambiguity, duplicate Anakin dialogs, measured overlap, and alert-drawer stacking cause in a local browser.
- [x] 1.4 Strictly validate the OpenSpec architecture, failure matrix, and workflow boundaries before implementation.

## 2. Canonical Surface And Foreground Ownership

- [x] 2.1 Make App the visibility and foreground owner for one canonical SIEM Anakin conversation surface.
- [x] 2.2 Route all contextual controls and command-palette actions into that surface with preserved workflow and entity intent.
- [x] 2.3 Implement deterministic alert drawer, investigation drawer, command palette, and Anakin handoff, Escape, focus return, and scroll behavior.
- [x] 2.4 Remove independent response mounting and replace legacy workflow labels with consistent analyst-task labels and descriptions.

## 3. Thread Experience

- [x] 3.1 Add narrow frontend service support for thread reset and turn submission where needed by existing APIs.
- [x] 3.2 Load and render ordered authoritative turns, active entity, remembered state, clarification, and artifact safety labels.
- [x] 3.3 Implement freeform follow-up, optional task shortcuts, per-turn async progress, failure and retry, reset, New Thread, expiry, and unavailable-context recovery.
- [x] 3.4 Restore thread and active request after refresh using safe owner-scoped browser pointers and clear them on logout/session change.
- [x] 3.5 Guard visible async updates by request ID, thread ID, and selection epoch; prevent duplicate local submissions.

## 4. Focused Verification

- [x] 4.1 Add focused service, control, canonical-surface, App integration, overlay, lifecycle, boundary, and responsive tests.
- [x] 4.2 Run affected frontend suites and any focused backend conversation tests required by API plumbing.
- [x] 4.3 Run the frontend production build and verify desktop and narrow browser layouts against the reproduced defects.

## 5. Final Gates

- [x] 5.1 Run the complete frontend suite once after focused tests pass.
- [x] 5.2 Run `git diff --check` and strict OpenSpec validation.
- [x] 5.3 Record that local implementation is not production verification and require deployment plus real `/siem/` browser-path acceptance before using working, done, fully verified, or production-ready language.
