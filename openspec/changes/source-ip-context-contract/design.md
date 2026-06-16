## Context

The SIEM/SOAR UI currently exposes source-IP context through separate views: Alerts, Incidents, SOAR Queue, Blocklist, Playbook Executions, SOC Command Center, and Map. Each view is useful in isolation, but operators need a single backend contract for the investigation question: "What do we know about this source IP?"

Current data semantics are intentionally separate. Alert status is alert lifecycle, incident status is case lifecycle, queue status is response-action execution state, blocklist status is tracking state, external reputation is a historical alert snapshot, and behavioral reputation is current IP-derived scoring. The new contract must preserve those meanings and avoid creating a synthetic all-purpose status.

## Goals / Non-Goals

**Goals:**
- Define one read-only backend endpoint for normalized source-IP context.
- Use existing records only: alerts, incidents, queue rows, blocklist entries, behavioral reputation, external reputation snapshots, and playbook executions.
- Validate `source_ip` input and return predictable error responses.
- Bound recent collections so the endpoint is safe for dashboard use.
- Define permission behavior before implementation.
- Give frontend code one authoritative contract to consume in future Alert Details and Map integrations.

**Non-Goals:**
- No mutation endpoint.
- No alert, incident, queue, approval, playbook, or SOAR lifecycle changes.
- No fake unified status field.
- No frontend-side data joins as the authoritative source of source-IP context.
- No schema changes unless implementation proves an existing query cannot meet the contract safely.
- No SOC Command Center redesign in the initial frontend phase.

## Decisions

### Endpoint

Use `GET /source-ip-context?source_ip=<ip>` for the initial contract.

Rationale: a query parameter avoids path encoding edge cases for IPv6 addresses, keeps validation explicit, and matches existing filter-style endpoints such as event search.

Alternative considered: `GET /source-ips/{source_ip}/context`. This is readable for IPv4 but less ergonomic for IPv6 and URL encoding, so it should not be the first choice.

### Permission Model

Require authenticated analyst or super-admin access for the full contract.

Rationale: the response includes operational SOAR context, queue activity, blocklist state, and playbook execution context. Those are already restricted beyond viewer access in several UI paths. A partial viewer response would create a second contract shape and weaken the goal of a normalized source of truth.

### Response Shape

Return a single object with top-level sections:
- `source_ip`
- `generated_at`
- `limits`
- `alerts`
- `incidents`
- `queue`
- `blocklist`
- `reputation`
- `playbook_executions`

Do not include `status` at the top level. Each section owns its own status semantics.

### Bounds

Default and maximum caps:
- recent alerts: default 10, max 25
- recent incidents: default 10, max 25
- recent queue rows: default 10, max 25
- recent playbook executions: default 10, max 25
- external reputation snapshots: default 5, max 10

Initial implementation may expose a single optional `limit` parameter applied to recent sections, or fixed defaults only. Any per-section limit parameters must be validated and capped.

### Query Strategy

The backend should query existing tables by normalized `source_ip` and by linked IDs:
- Alerts: filter by `alerts.source_ip`.
- Incidents: include incidents whose `source_ip` matches and incidents linked to matching alerts through `incident_alerts`.
- Queue: filter `response_actions_queue.source_ip`; include `alert_id` reference when present.
- Blocklist: filter `blocked_ips.ip_address`; normalize effective status using `status = 'active' AND (expires_at IS NULL OR expires_at > NOW())`.
- Behavioral reputation: call the existing `get_ip_reputation()` logic so scoring stays consistent with `/alerts`.
- External reputation: return recent non-null alert reputation snapshots from matching alerts.
- Playbook executions: include executions linked to matching alert IDs or matching incident IDs.

Implementation should prefer helper functions with clear SQL over duplicating route logic in React.

### Frontend Consumption Model

Future frontend integration should add a shared source-IP context display component that consumes this endpoint. Alert Details and Map popup should use the shared component or hook. The frontend must not recompute linked incidents, queue context, blocklist status, or reputation from unrelated service responses.

## Risks / Trade-offs

- Broad response becomes expensive -> cap every recent collection, index-backed queries by `source_ip`, `alert_id`, and `incident_id`, and include returned limits in the payload.
- Operators misread separate statuses as one status -> no top-level unified status, and frontend labels must include "Alert status", "Incident status", "Queue execution status", and "Blocklist status".
- Permission mismatch with existing viewer dashboard -> start with analyst/super-admin only; revisit a reduced viewer-safe contract later only if needed.
- External reputation snapshots vary across alerts -> expose them as historical snapshots and identify the latest snapshot rather than pretending there is one current external reputation.
- IPv6 path handling ambiguity -> use query parameter endpoint and standard IP validation.
- Contract grows too quickly -> initial frontend integration should target Alert Details and Map only; SOC Command Center enhancements should be justified later.
