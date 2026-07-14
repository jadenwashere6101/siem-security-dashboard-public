## 1. Severity Contract

- [x] 1.1 Refine pfSense severity behavior in detector logic and defaults so port scan, repeated deny, suspicious allow, and noisy source follow the approved severity direction without changing historical rows.
- [x] 1.2 Preserve compatibility with the existing runtime-configurable threshold override system and verify incident auto-creation still derives only from resulting alert severity.

## 2. Operational Baseline Backend

- [x] 2.1 Add a shared tuning-baseline configuration contract and request filter semantics for `Since Tuning` and `All History`.
- [x] 2.2 Apply the shared baseline filter to alert summary APIs, recent alerts/list APIs, incident list/metrics APIs, SOC Command Center data dependencies, and pfSense Detection Health.
- [x] 2.3 Expose additive legacy/pre-tuning metadata for pfSense alerts and incidents without rewriting stored records.

## 3. Frontend Operational Views

- [x] 3.1 Add a consistent `Since Tuning` / `All History` control pattern to the approved operational surfaces only: Dashboard, Recent Alerts, Incidents, SOC Command Center, and Detection Health.
- [x] 3.2 Default those surfaces to `Since Tuning` and render clear legacy/pre-tuning indicators when older pfSense records are shown.
- [x] 3.3 Keep full historical investigation available and avoid changing unrelated workspaces or global search behavior.

## 4. Verification

- [x] 4.1 Add focused backend tests for pfSense severity normalization, alert-to-incident propagation, shared baseline filtering, detection health counts, and incident pressure metrics.
- [x] 4.2 Add focused frontend tests for baseline toggle behavior, default `Since Tuning` views, legacy/pre-tuning labeling, and count consistency across Dashboard, Incidents, SOC Command Center, and Detection Health.
- [x] 4.3 Run strict OpenSpec validation, focused affected suites, production build, and `git diff --check` before handoff.
