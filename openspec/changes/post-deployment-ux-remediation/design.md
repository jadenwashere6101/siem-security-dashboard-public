## Context

`analyst-experience-foundation` established the responsive shell, shared primitives, sidebar behavior, and visual verification expectations. `anakin-analyst-experience` added Threat Brief as a reusable attention surface. `investigation-workflow` added Investigation Drawer, Threat Story, private Analyst Workspace persistence, and workspace/investigation APIs.

The post-deployment UX audit confirmed that the new surfaces are generally in the right architectural areas but have focused user-facing defects: Threat Brief is mounted globally, text can overflow in new cards, Alert Details and Investigation Drawer can compete as overlapping modal dialogs, workspace delete APIs are not fully wired into UI controls, and pin/save/evidence actions lack consistent visible feedback.

This change is a remediation pass only. It should not re-audit or redesign the application.

## Goals / Non-Goals

**Goals:**

- Make the requested improvements immediately visible in normal analyst use.
- Keep Threat Brief scoped to Dashboard while preserving the deterministic model from the Anakin phase.
- Ensure Alert Details -> Investigation Drawer is a single-overlay flow with preserved selected alert context.
- Add consistent loading, success, duplicate/idempotent, and failure feedback for workspace/investigation actions.
- Make saved investigations discoverable without turning Analyst Workspace into a redesigned case-management surface.
- Wire delete controls for notes, hypotheses, and tasks through existing service/API functions.
- Preserve existing RBAC, ownership, audit logging, workspace privacy, and no-system-mutation boundaries.
- Confirm Settings remains unchanged because these are workflow/display fixes, not new user preferences.

**Non-Goals:**

- No full Analyst Workspace redesign.
- No source-IP watch workflow.
- No deeper note/task/hypothesis association model beyond existing workspace/investigation parent links.
- No major visual redesign, advanced evidence organization, collaboration, case management, shared workspaces, report export, or portfolio polish.
- No package/application version metadata change.
- No VM access, production deployment, production mutation, or runtime data cleanup.
- No schema migration unless implementation proves an authoritative backend idempotency constraint is genuinely required.

## Decisions

### Decision: Threat Brief is dashboard-scoped, not global shell chrome

Threat Brief should render only inside the Dashboard content flow and above the Dashboard body. It should not sit at the `SidebarLayout` child root above every active section. This preserves the Anakin contract for a reusable Threat Brief while matching the reported UX expectation that “What requires attention right now?” belongs at the top of Dashboard.

Alternative considered: leave it global and hide via CSS. Rejected because the DOM would still expose a section-level briefing outside Dashboard and could confuse keyboard/screen-reader users.

### Decision: Overflow fixes use shared resilient text behavior

Threat Brief and Analyst Workspace cards should support long alert types, source IPs, labels, notes, hypotheses, tasks, evidence labels, and generated recommendations. Card/grid children should use `minWidth: 0`, wrapping/word-break behavior for long tokens, and flex layouts that prevent chips/buttons from forcing text out of bounds.

Alternative considered: truncate all long values. Rejected because analysts often need to inspect exact alert types, IPs, object IDs, and note text. Truncation may still be used for compact secondary metadata only when full content remains accessible through title/expanded text.

### Decision: Alert Details and Investigation Drawer must not be simultaneous modal surfaces

When the drawer opens from Alert Details, Alert Details should close or be replaced while selected alert context remains active for the drawer. The implementation should avoid solving the bug by z-index alone because two `aria-modal` dialogs, two Escape handlers, and nested fixed panels create accessibility and mobile behavior problems.

On close, focus should return to the initiating control when it still exists, or to the selected alert row/recent-alerts region as a sensible fallback. Escape/backdrop should close the active modal surface only. Mobile/tablet should continue using full-width or viewport-safe drawer behavior.

Alternative considered: raise the drawer z-index above Alert Details and keep both open. Rejected because it preserves a confusing modal stack and makes focus management fragile.

### Decision: Action feedback should use one reusable pattern

The app already has toast/status patterns for alert actions. This change should either promote the existing toast into a reusable shared notification/status component or reuse an equivalent app-level pattern for pin alert, save evidence, save investigation, workspace create/delete, and duplicate/idempotent outcomes.

Feedback states must distinguish:

- loading/in-progress: disable or mark the initiating action busy;
- success: show what changed and where to find it;
- already exists/idempotent: explain that the object was already saved/pinned and avoid implying a new record was created;
- failure: show an accessible error without hiding existing workspace content.

### Decision: Save Investigation is primarily frontend-idempotent

Implementation should first attempt reliable frontend duplicate prevention by checking the loaded workspace investigation bundle for the selected alert/incident/source IP and by disabling repeated clicks while a save is pending. On success, saved investigations should be visible in Analyst Workspace with enough metadata to identify the linked alert/source.

If loaded state is stale or missing, frontend-only prevention may not be authoritative. A minimal backend adjustment may be added only if needed to return an existing owned investigation for the same selected object instead of creating another one. No migration should be introduced unless a validated design requires a new database constraint, which is not expected for this remediation.

### Decision: Settings remains unchanged

No new configuration belongs in Settings for these fixes. Threat Brief placement, single-overlay behavior, sidebar order, version-label visibility, wrapping, delete controls, and feedback states are product behavior corrections, not analyst preferences.

## Risks / Trade-offs

- **Risk: Duplicate prevention misses stale loaded state** -> disable repeated clicks during the request, refresh workspace state after save, and use backend idempotency only if frontend state is insufficient.
- **Risk: Closing Alert Details loses analyst context** -> preserve selected alert ID/context in App state and make the drawer title/body confirm the selected alert.
- **Risk: Toasts are missed by screen-reader users** -> use `role="status"` for success/idempotent/loading and `role="alert"` for failure, with stable accessible text.
- **Risk: Text wrapping makes cards taller** -> prefer readable wrapping over clipping; use responsive grids and min-width constraints to avoid layout breakage.
- **Risk: Sidebar order affects landing/history tests** -> preserve section IDs and navigation targets; only reorder config/group presentation.
- **Risk: Workspace delete controls imply system deletion** -> copy and tests must preserve that deletion removes private workspace records only and does not mutate alerts, incidents, SOAR, detections, or evidence sources.

## Regression Strategy

- Focused frontend tests for Dashboard-only Threat Brief rendering and non-dashboard absence.
- Threat Brief tests for long values and responsive wrapping behavior.
- Alert Details -> Investigation Drawer tests asserting one active modal, selected alert preserved, Escape/backdrop behavior, and focus return/fallback.
- Sidebar tests for group order: SOAR and Administration above Live Logs; Live Logs directly above Settings.
- Login/sidebar tests confirming visible version label is absent while package metadata remains unchanged.
- Analyst Workspace tests for long text wrapping, note/hypothesis/task delete controls, delete service calls, refresh behavior, and private-state messaging.
- Save Investigation tests for loading, success, failure, duplicate/idempotent handling, and saved-investigation discoverability.
- Shared feedback tests for pin alert, save evidence, save investigation, and workspace delete outcomes.
- Production frontend build, dark-theme/accessibility review, visual verification when practical, `git diff --check`, and strict OpenSpec validation.
