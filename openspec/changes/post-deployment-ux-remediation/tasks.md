## 1. Threat Brief Remediation

- [x] 1.1 Move Threat Brief rendering so it appears only at the top of the Dashboard section.
- [x] 1.2 Add resilient wrapping/min-width behavior for Threat Brief card values, metadata, chips, and long recommendations.
- [x] 1.3 Add focused tests proving Threat Brief renders on Dashboard and not on non-Dashboard sections.
- [x] 1.4 Add focused tests or assertions covering long Threat Brief values without horizontal/card overflow.

## 2. Investigation Overlay Flow

- [x] 2.1 Change Alert Details -> Open Investigation Drawer flow so Alert Details closes or is replaced before the drawer becomes active.
- [x] 2.2 Preserve selected alert context when the drawer opens from Alert Details.
- [x] 2.3 Preserve drawer focus entry, Escape/backdrop close behavior, focus return or fallback, and responsive drawer behavior.
- [x] 2.4 Add focused tests proving only one modal/dialog surface is active during Alert Details -> Investigation Drawer flow.
- [x] 2.5 Add focused tests for selected alert preservation and drawer close/focus behavior.

## 3. Sidebar, Login, and Settings Presentation

- [x] 3.1 Reorder sidebar configuration so SOAR and Administration appear above Live Logs and Live Logs appears directly above Settings.
- [x] 3.2 Confirm Live Logs section IDs, navigation targets, and workspace history behavior remain unchanged.
- [x] 3.3 Remove visible version labels from login and sidebar without changing package/application version metadata.
- [x] 3.4 Add focused tests for sidebar group order and preserved Live Logs navigation IDs.
- [x] 3.5 Add focused tests confirming login/sidebar no longer render visible package version labels.
- [x] 3.6 Confirm Settings requires no new entries and document that no Settings UI/configuration changes are needed.

## 4. Analyst Workspace Quick Fixes

- [x] 4.1 Add wrapping/min-width behavior for Analyst Workspace pins, notes, hypotheses, tasks, evidence references, and saved investigations.
- [x] 4.2 Render saved investigations in Analyst Workspace with linked alert, incident, source IP, status, and private-state context where available.
- [x] 4.3 Wire delete controls for notes using the existing note delete service/API.
- [x] 4.4 Wire delete controls for hypotheses using the existing hypothesis delete service/API.
- [x] 4.5 Wire delete controls for tasks using the existing task delete service/API.
- [x] 4.6 Refresh or update workspace state after note, hypothesis, and task deletion without mutating underlying system objects.
- [x] 4.7 Add focused workspace tests for long text containment and delete controls for notes, hypotheses, and tasks.

## 5. Save and Action Feedback

- [x] 5.1 Introduce or reuse a shared accessible feedback pattern for workspace/investigation action loading, success, idempotent/already-exists, and failure states.
- [x] 5.2 Apply consistent feedback to Pin alert, Save evidence, Save investigation, note/hypothesis/task create, and note/hypothesis/task delete actions.
- [x] 5.3 Add loading/busy state and repeated-click protection for Save Investigation and related mutation controls.
- [x] 5.4 Implement reliable frontend duplicate prevention for Save Investigation using loaded workspace investigation state when available.
- [x] 5.5 Add a minimal backend idempotency adjustment only if frontend duplicate prevention is not reliable enough; do not add a migration unless a validated design proves it is required.
- [x] 5.6 Add focused tests for Save Investigation loading, success, failure, already-saved handling, and saved-investigation discoverability.
- [x] 5.7 Add focused tests for pin/save/evidence action feedback states.

## 6. Scope Boundaries and Verification

- [x] 6.1 Verify no full Analyst Workspace redesign, source-IP watch workflow, deeper association model, collaboration, case management, advanced evidence organization, or portfolio polish is introduced.
- [x] 6.2 Verify no package/application version metadata change is introduced.
- [x] 6.3 Verify no migration is introduced unless explicitly required by validated backend idempotency design.
- [x] 6.4 Run focused frontend tests covering the remediation scope.
- [x] 6.5 Run frontend production build.
- [x] 6.6 Perform dark-theme/accessibility review and practical visual verification for Dashboard, drawer flow, sidebar, login, and Analyst Workspace.
- [x] 6.7 Run `git diff --check`.
- [x] 6.8 Run `openspec validate post-deployment-ux-remediation --strict`.
- [x] 6.9 Run `openspec status --change post-deployment-ux-remediation`.
