## Why

The Response Registry already stores canonical response history, dispositions, and related identifiers, but the current workspace does not behave like a polished analyst investigation surface. Several controls are misleading or incomplete: related alerts and incidents render as plain text IDs, there is no dedicated investigation handoff, command failures are generic, some registry actions appear unreliable when opened from alert-driven workflows, and detail recovery is weaker than the list view.

This change is needed now because the workspace is close to useful but still costs analysts time at exactly the moment they need fast context: why the response exists, what actually happened, whether it executed, and where to investigate next. The goal is to fix that workflow gap without redesigning the broader application.

## What Changes

- Add one narrow Response Registry analyst-workflow capability covering investigation handoff, compact relationship rendering, response summary, recommended-next-step guidance, and clearer analyst-facing outcome wording.
- Define a single canonical `Investigate` action that deterministically opens the best next workspace target instead of forcing analysts to interpret multiple IDs or choose among several buttons.
- Define a compact clickable relationship summary for alerts, incidents, playbooks, and approvals instead of rendering raw related IDs as text.
- Define required command-context behavior so registry actions receive sufficient alert, incident, and indicator provenance regardless of entry surface.
- Define actionable analyst error messaging, detail-pane retry behavior, and list retry pagination preservation.
- Clarify misleading command wording and field behavior, including separate tracking vs escalation reason inputs and a clearer incident-creation label.

## Capabilities

### New Capabilities
- `response-registry-analyst-workflow`: Analyst-facing Response Registry behavior for investigation routing, relationship navigation, command reliability, response summaries, next-step guidance, and scoped usability fixes.

### Modified Capabilities
- None.

## Impact

- Frontend workspace behavior in [frontend/src/components/ResponseRegistryPanel.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/components/ResponseRegistryPanel.js:1) and related navigation helpers will gain a clearer analyst workflow contract.
- Related frontend service behavior in [frontend/src/services/responseRegistryService.js](/Users/jadengomez/Projects/siem-security-dashboard-public/frontend/src/services/responseRegistryService.js:1) will need a stricter command-context contract.
- Backend registry read models and command entrypoints in [routes/response_registry_routes.py](/Users/jadengomez/Projects/siem-security-dashboard-public/routes/response_registry_routes.py:1), [core/response_command_service.py](/Users/jadengomez/Projects/siem-security-dashboard-public/core/response_command_service.py:1), and [core/indicator_response_registry.py](/Users/jadengomez/Projects/siem-security-dashboard-public/core/indicator_response_registry.py:1) will need additive behavior changes, not a redesign.
- Test impact is limited to focused Response Registry frontend coverage, response-registry API contracts, and command reliability or navigation regressions.
- No migration, VM work, deployment, or production mutation is expected from this spec.
