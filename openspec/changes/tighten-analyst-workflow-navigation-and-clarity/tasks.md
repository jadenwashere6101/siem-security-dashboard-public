## 1. Alert Navigation Contract

- [x] 1.1 Add additive exact analyst-investigation filters to the alert list and summary contract for source-IP and target-IP pivots without changing existing broad `search` behavior.
- [x] 1.2 Add focused backend tests covering exact source/target filtering, coexistence with broad search, and summary consistency under the new filters.
- [x] 1.3 Refactor dashboard alert-list state in `App.js` so deep links and filter changes reset pagination before requesting rows and preserve exact-pivot context during quiet refresh.

## 2. Analyst Workflow UI

- [x] 2.1 Rework `Recent Alerts` expanded detail into grouped investigation sections that preserve current evidence while reducing repeated wording and improving ordering.
- [x] 2.2 Update analyst-facing investigation wording so severity, investigation value, and recommended action are clearly distinct in touched alert and recon surfaces.
- [x] 2.3 Make the shared workspace loading spinner visibly animate through the existing shared async-state path.

## 3. Recon and Registry Pivots

- [x] 3.1 Update Recon Activity list/detail behavior to support bounded scrolling, clearer “why this matters” evidence, and `Open Primary Target` when the current backend projection supports it.
- [x] 3.2 Update Dashboard recon and related-alert pivots to use the new exact investigation filters instead of broad free-text search for analyst handoffs.
- [x] 3.3 Update `ResponseRegistryPanel` navigation handling so contextual opens reset pagination/selection and clear incompatible registry-local filters that would hide the intended record.

## 4. Verification

- [x] 4.1 Add or update focused frontend tests for dashboard pagination-reset behavior, exact related-alert/recon pivots, Response Registry contextual opens, Recon Activity scrolling/pivots, and grouped investigation wording.
- [x] 4.2 Run the affected backend and frontend test suites plus a frontend production build for the touched analyst workflows.
- [x] 4.3 Run `git diff --check` and `openspec validate tighten-analyst-workflow-navigation-and-clarity --strict` before handoff.
