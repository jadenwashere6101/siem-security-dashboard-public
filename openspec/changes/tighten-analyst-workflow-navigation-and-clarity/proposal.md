## Why

Analyst workflow is currently being undermined by a small set of connected UI issues rather than by missing detections or missing backend platforms. The current implementation shows evidence of stale local filters surviving deep links, `Recent Alerts` pagination resetting after an initial stale request, recon pivots routing through broad free-text search instead of an exact analyst target, and expanded investigation surfaces that preserve evidence but present it in a noisy order.

This change is needed now because these issues affect the core analyst loop: move from Recon Activity or an alert to the right filtered workspace, understand why the item matters, and continue the investigation without losing context or confidence. The scope stays intentionally narrow and avoids new detections, dashboard expansion, or backend architecture work.

## What Changes

- Tighten `Recent Alerts` navigation so filter changes and deep links reset pagination deterministically before requesting data, and so analyst pivots can use exact investigation targets instead of only broad text search.
- Clarify the `Recent Alerts` investigation surface by regrouping expanded detail content, reducing repeated wording, and preserving all investigation-critical evidence.
- Improve analyst-facing investigation wording so severity, investigation value, and recommended action are distinguishable instead of sounding contradictory.
- Repair deep-link behavior into `Response Registry` so analyst pivots from alerts and related workspaces do not inherit stale registry-local filters that hide the intended record.
- Refine the Recon Activity investigation flow without redesigning the workspace: keep the compact card/detail model, restore missing supported pivots such as `Open Primary Target` when existing data supports them, improve the explanation of why the activity matters, and make the bounded list reliably scrollable.
- Capture small, low-risk workflow polish discovered in this audit when it directly affects analyst perception of state, such as the non-animating loading spinner.

## Capabilities

### New Capabilities
- `analyst-investigation-workflow`: Analyst-facing investigation readability for Recent Alerts and Recon Activity, including clearer grouping, wording, pivots, and low-risk workflow polish.

### Modified Capabilities
- `workspace-navigation-detail-ux`: Deep links into Dashboard and related analyst workspaces must reset and preserve state intentionally, including exact-target pivots and deterministic pagination behavior.
- `response-registry-workspace`: Opening Response Registry from alert-driven workflows must override stale local filters and reliably surface the intended indicator and relationship context.

## Impact

- Frontend: `frontend/src/App.js`, Dashboard/Recent Alerts components, SOC Command Center, Response Registry, shared navigation utilities, and focused tests.
- Backend/API contract: alert-list filtering may need a narrow exact-investigation filter contract in addition to the current broad `search` semantics; no architecture rewrite, new dashboard family, or detection-rule tuning is included.
- OpenSpec: new analyst investigation capability spec plus scoped deltas for existing navigation and Response Registry capabilities.
