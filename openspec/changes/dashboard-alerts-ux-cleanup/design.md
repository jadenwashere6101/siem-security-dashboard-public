## Context

The dashboard currently loads `frontend/src/index.css` globally, but the `workspace-spin` keyframes live in `frontend/src/App.css`, which is not imported by the app entrypoint. Several loading states duplicate inline spinner styles and reference that missing keyframe. The reliable path is therefore not to abandon animation; it is to make the animation definition global and remove duplicated spinner implementations.

Recent Alerts and dashboard summary data already share most filter state through `App.js`, `frontend/src/services/alertsService.js`, and `routes/alerts_events_routes.py`. Exports are the exception: `routes/reporting_routes.py` uses `helpers/query_helpers.py`, which currently accepts only search, severity, and status. Top Source IPs are produced by `/alerts/summary`; synthetic/demo exclusions are loaded in that route but applied after `_fetch_top_source_ips()` has already grouped and limited rows.

## Goals / Non-Goals

**Goals:**

- Make dashboard and alert loading states use one shared loading indicator implementation with one globally loaded animation definition.
- Move synthetic/demo IP exclusion before dashboard summary aggregation and `LIMIT`.
- Keep dashboard summary widgets consistent when synthetic/demo filtering is applied.
- Add detection-rule filtering to Recent Alerts, dashboard summary, pagination, and exports by reusing the existing filter pipeline.
- Require focused tests, production build, local visual review where practical, and VM/runtime visual verification after implementation deployment.

**Non-Goals:**

- No recon, browser history/navigation, monitor workflow, SOAR, AI, cache, security hardening, deployment-script, schema migration, or database redesign work.
- No changes to how alerts are generated, how detection rules are evaluated, or how RBAC works.
- No deletion or mutation of historical production alert rows.

## Decisions

1. **Keep the animated loading indicator, but centralize it.**
   - Implement one shared loading component or shared spinner style helper used by `WorkspaceAsyncState`, timeline refresh status, and Recent Alerts pending status.
   - Move `workspace-spin` to `index.css`, or another stylesheet imported by `index.js`, so the keyframe is guaranteed to load.
   - Preserve `prefers-reduced-motion` behavior by disabling animation for users who request reduced motion.
   - Alternative considered: replace all spinners with static loading text. This remains a fallback only if implementation-time visual verification proves the shared animation cannot be made reliable.

2. **Make synthetic/demo filtering a backend query policy, not a chart patch.**
   - Introduce a deterministic dashboard synthetic/demo exclusion predicate used by summary queries before aggregation.
   - Use explicit demo/documentation networks and configured exclusions only as exclusion inputs; do not infer “fake” from arbitrary private/reserved ranges that may represent legitimate internal production telemetry.
   - Apply the exclusion policy to source-IP-derived dashboard summary widgets: Top Source IPs, Unique Source IPs, Attack Map markers, and source-IP map aggregation.
   - Preserve Total Alerts, severity counts, and Alerts Over Time as alert-volume widgets unless product copy is changed to state they are source-IP-cleaned. This keeps analysts aware of total alert volume while removing demo IPs from source-IP visuals.

3. **Add `rule_id` as the explicit alert-rule filter contract.**
   - Accept `rule_id` on `/alerts` and `/alerts/summary`; map it to `alerts.alert_type`.
   - Validate against known detection rule IDs from the catalog/defaults where practical, while preserving compatibility with legacy alert types by returning a clear 400 only for malformed or unsupported requested values.
   - Add `rule_id` to `alertsService` query construction, `App.js` alert view state, `DashboardSection`, `AlertsTable`, and `AlertsToolbar`.
   - Populate the UX from existing detection-rule metadata. If the admin endpoint remains super-admin-only, the implementation should use a viewer-safe catalog/list source or derive options from current alert data rather than exposing privileged configuration controls.

4. **Align exports with dashboard filters.**
   - Update report/CSV/PDF export routes and query helpers to honor `rule_id`, source, operational scope, exact source IP, exact target IP, and alert ID where applicable.
   - Avoid maintaining two divergent filter builders. Prefer extracting/reusing the alert filter builder or creating a shared helper that both `/alerts` and export routes can call.

## Risks / Trade-offs

- [Risk] Overbroad synthetic filtering could hide legitimate production IPs. → Use explicit demo/test documentation networks and configured exclusions; do not blanket-filter private/reserved ranges unless product policy explicitly expands later.
- [Risk] Metrics may appear inconsistent if some widgets filter synthetic IPs and others do not. → Document and expose the policy in code/tests: source-IP-derived dashboard widgets filter synthetic/demo IPs; alert-volume widgets continue reflecting filtered alert volume.
- [Risk] Detection-rule options may require privileged admin configuration data. → Use non-sensitive catalog metadata or current alert-type values for the dashboard filter; do not weaken RBAC on admin rule mutation endpoints.
- [Risk] Export filters can drift from dashboard filters. → Add backend contract tests that compare `/alerts` and each export route for the same filter set.
- [Risk] Animation can still fail through CSS build changes. → Add frontend tests for shared loading usage and perform production-build visual verification.
