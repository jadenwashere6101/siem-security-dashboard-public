## Context

The loading/list-bounds audit found two separate but related UI issues in the current codebase.

First, load state handling is inconsistent. `SourceHealthPanel` already models the desired behavior by showing a true initial load, preserving the last successful response during refresh, and warning on refresh failure. In contrast, `App.js` fetches dashboard alerts with no explicit `alertsLoading` or `alertsError` state, and `SocCommandCenter` renders with zero-like empty structures before its first batch of requests resolves.

Second, only two proven large-list risks exist today. `GET /alerts` is currently unbounded and the dashboard derives totals, severity counts, top IPs, timeline buckets, the attack map, and the Recent Alerts table from that same full result set. `LiveLogsPanel` already polls a bounded API result, but it keeps appending rows in memory and can grow indefinitely during long sessions.

This change stays intentionally narrow. It improves only the approved loading surfaces and bounds only the two audited list risks.

## Goals / Non-Goals

**Goals:**
- Establish one small reusable loading-state pattern for scoped data workspaces.
- Ensure initial load never looks like a real empty or zero state for Dashboard / Recent Alerts or SOC Command Center.
- Preserve visible data during background refresh and refresh failure where stale data exists.
- Paginate Recent Alerts through a bounded API contract without making dashboard metrics or visuals page-local.
- Add a deterministic Live Logs retention cap that preserves newest events and bounded polling behavior.
- Keep accessibility, narrow layouts, focus, scroll, and current navigation semantics intact.

**Non-Goals:**
- No system-wide loader redesign.
- No virtualization rollout across the app.
- No scope expansion into Incidents, Playbooks, Approvals, SOAR Queue, Response Registry, or Dead Letters unless a shared primitive is reused without behavior change.
- No database migration, schema change, or new analytics program.
- No VM access, deployment, or production mutation in this spec step.

## Decisions

### Shared loading primitive

Use one small shared frontend primitive for workspace async state rather than bespoke inline text in each scoped workspace. The primitive should support four states:
- initial loading with a small accessible loader or skeleton
- loaded with no loading chrome
- background refresh with existing data preserved and only a subtle `Refreshing…` indicator
- error split into initial-load failure vs refresh failure with stale data preserved when available

Rationale: this matches the clearest existing pattern in `SourceHealthPanel` while avoiding a broad component-library redesign.

Alternative considered: leave each workspace to hand-roll its own loading copy. Rejected because the audit already found inconsistent semantics and the approved scope is small enough to normalize safely.

### Alerts row vs summary split

Split dashboard alert consumption into two contracts:
- `GET /alerts` becomes a bounded paginated row-list endpoint using the repository's list response pattern with validated `limit` and `offset`
- a new authoritative alert summary endpoint provides the aggregate inputs currently derived from the full client-side alerts array

The summary contract must cover every dashboard aggregate currently dependent on the full unbounded list: total alerts, severity counts, unique source IP count, top-IP chart data, timeline bucket data, and map/source summary data used by the dashboard visuals.

Rationale: paginating `/alerts` alone would silently corrupt dashboard metrics and visuals by making them page-local. A dedicated summary contract keeps the list bounded while preserving authoritative aggregates.

Alternative considered: return paginated rows plus summary from `GET /alerts`. Rejected because it overloads one route with two concerns, complicates list-only consumers, and makes refresh behavior less explicit in the frontend.

### Alerts pagination bounds

Use the existing backend pagination style already present in incidents, approvals, and playbook routes: validated `limit` and `offset`, a safe maximum page size of 100, and a response object that includes `items`, `total`, `limit`, and `offset`.

Rationale: this keeps the change aligned with current repository patterns and avoids inventing a new pagination model.

### Live Logs retention

Keep the existing bounded polling contract to `/events/search` and add a deterministic client-side retention cap of 500 rows per panel instance after merge and deduplication. When new rows push the collection over the cap, the oldest retained rows are trimmed and the newest rows remain visible.

Rationale: the API is already bounded per poll, so the real risk is unbounded accumulation over time. A 500-row ceiling is large enough for current raw/json/event-feed workflows while remaining predictable for memory and rendering cost.

Alternative considered: remove `rowsPerPage="all"` globally. Rejected because the retention cap already bounds the maximum rendered set for Live Logs and avoids unrelated settings churn.

### SOC Command Center initial loading

Treat the command center's first composite request as a true initial-loading state. Summary cards and workspace panels must not render placeholder zeros that resemble valid data before the first request settles. Once data has loaded once, refreshes keep the last successful data visible and only surface a subtle refreshing state plus partial-source warnings when needed.

Rationale: this fixes the audited UX issue without changing any command-center metrics semantics.

## Risks / Trade-offs

- [Dashboard aggregate scope is broader than the Recent Alerts table] -> Mitigation: define the summary endpoint as authoritative for all current dashboard aggregate inputs, not just totals.
- [Changing `/alerts` to a paginated list shape can break existing consumers] -> Mitigation: update all known frontend callers in the same change and cover the route contract with focused backend and frontend tests.
- [Attack Map may implicitly depend on full alert rows] -> Mitigation: require the new summary contract to include the map/source summary inputs needed by the current dashboard visual; if that cannot be preserved without broader redesign, stop implementation and report a blocker rather than shipping page-local map semantics.
- [Retention trimming could disrupt Live Logs usability] -> Mitigation: trim oldest rows only after dedupe, preserve newest events, and verify focus/scroll behavior under polling.
- [Shared loading primitive could cause regressions in untouched workspaces] -> Mitigation: scope adoption to Dashboard / Recent Alerts and SOC Command Center only unless reused without behavior change.

## Migration Plan

No schema or data migration is expected.

Implementation handoff after approval should:
1. add the shared loading primitive and apply it to the scoped workspaces
2. add alerts pagination plus the authoritative alert-summary API contract
3. integrate the paginated Recent Alerts table and aggregate dashboard data
4. add Live Logs retention trimming
5. add focused backend/frontend tests, run production build, validate OpenSpec, and prepare a standard VM handoff only if implementation later occurs

## Open Questions

None. The design explicitly resolves the critical contract concern by requiring a separate authoritative alert summary contract instead of allowing dashboard aggregates to become page-local.
