## Context

The `events` table is the authoritative record of successfully retained normalized events and already has `source` and `created_at` indexes. `/events/search` exposes recent rows but is capped at 100 and performs per-event enrichment, so it cannot provide authoritative counts. Dashboard calculations are alert-oriented and must remain unchanged. The frontend already has source-specific Live Logs destinations and an authenticated polling setting.

This change crosses Flask query/API code, canonical source metadata, React navigation, polling, and browser verification. It must remain read-only and must not imply parser, listener, collector, or end-to-end delivery health.

## Goals / Non-Goals

**Goals:**

- Return one uncapped database aggregation for Honeypot, Bank App, pfSense, NGINX, Azure Application Insights, and OpenTelemetry.
- Use consistent canonical source IDs, source types, and friendly labels across backend validation and frontend source workspaces.
- Define deterministic UTC last-hour and current-day windows.
- Represent never-seen sources explicitly while always returning all six inventory entries.
- Add an authenticated Source Health workspace beneath Dashboard with existing polling and destination-aware navigation patterns.

**Non-Goals:**

- Parser failures, listener/collector health, ingest rejection/failure counts, or last attempted ingest.
- Healthy, stale, offline, or other classifications and freshness thresholds.
- Changes to ingestion, parsing, detection, correlation, SOAR, pfSense behavior, Dashboard calculations, or database schema.

## Decisions

### Use one canonical source inventory per runtime, with contract alignment

The backend will define reusable source metadata containing canonical `source`, canonical `source_type`, friendly `display_label`, and Live Logs destination identity for the six recognized sources. Existing backend source allowlists and the new aggregation will consume this inventory instead of adding another list. The frontend will centralize equivalent display/navigation metadata and existing Dashboard/Detection Rules/Live Logs consumers will reuse it where applicable without changing their behavior. Focused contract tests will assert exact alignment because Python and JavaScript cannot import one runtime object directly.

Alternative considered: define the inventory only in the new route. Rejected because it would create another conflicting source list.

Canonical entries are:

| source | source_type | display_label | Live Logs destination |
|---|---|---|---|
| `honeypot` | `honeypot` | `Honeypot` | `live-logs-honeypot` |
| `bank_app` | `custom` | `Bank App` | `live-logs-bank-app` |
| `pfsense` | `firewall` | `pfSense` | `live-logs-pfsense` |
| `nginx` | `web_log` | `NGINX` | `live-logs-nginx` |
| `azure_insights` | `cloud_api` | `Azure Application Insights` | `live-logs-azure` |
| `opentelemetry` | `telemetry` | `OpenTelemetry` | `live-logs-otel` |

### Add a dedicated database aggregation endpoint

Add `GET /source-health`, protected by `login_required` and `analyst_or_super_admin_required`, matching the existing event-read and Live Logs workspace boundary. The endpoint will execute a grouped aggregate over `events`, then left-join/merge results onto the six-entry inventory so zero-event sources are present. It will not call `/events/search`, load raw payloads, or perform IP reputation enrichment.

Alternative considered: call `/events/search` six times and count client-side. Rejected because the 100-row cap makes counts incorrect and causes duplicated polling/enrichment work.

### Define one UTC observation instant and half-open windows

The backend will capture one timezone-aware UTC `generated_at` for the response. Counts will use persisted `events.created_at`, which represents successful database ingestion, rather than sender-controlled `event_timestamp`.

- `last_hour_start = generated_at - 1 hour`
- `today_start = 00:00:00 UTC on generated_at's UTC date`
- Last-hour interval: `[last_hour_start, generated_at]`
- Today interval: `[today_start, generated_at]`
- Total and `last_event_at` exclude rows later than `generated_at`, ensuring one internally consistent snapshot.

The API will use database aggregation with conditional counts and no row limit. Existing `events.source` and `events.created_at` indexes are expected to support the query; implementation must inspect the query plan before proposing a migration.

### Keep the API factual and classification-free

Approximate response:

```json
{
  "generated_at": "2026-07-12T15:00:00+00:00",
  "windows": {
    "last_hour_start": "2026-07-12T14:00:00+00:00",
    "today_start": "2026-07-12T00:00:00+00:00",
    "timezone": "UTC"
  },
  "sources": [
    {
      "source": "pfsense",
      "source_type": "firewall",
      "display_label": "pfSense",
      "last_event_at": "2026-07-12T14:59:10+00:00",
      "events_last_hour": 418,
      "events_today": 7321,
      "total_events": 105432,
      "ever_seen": true
    }
  ]
}
```

For a never-seen source, `last_event_at` is `null`, all counts are `0`, and `ever_seen` is `false`. The API will not return a health classification.

### Reuse established workspace polling and navigation

Source Health will be registered directly after Dashboard in the Overview group. It will load through a focused service, use the existing configured automatic refresh interval, preserve focus/scroll during background refresh, and route Live Logs links through the existing destination-aware workspace navigation contract. Dashboard state and alert-derived utilities remain untouched.

## Risks / Trade-offs

- [Large `events` history makes aggregation expensive] → Use one grouped query, existing indexes, focused query-plan evidence, and avoid raw-row hydration; add a migration only if a proven plan blocker exists.
- [Source metadata diverges between Python and JavaScript] → Centralize within each runtime and enforce an exact API/frontend contract test for all six entries.
- [Users interpret activity as service health] → Use factual activity labels and never-seen state only; exclude Healthy/Stale/Offline terminology.
- [UTC day counts surprise users in other timezones] → Return explicit window boundaries and `timezone: UTC` in the contract.
- [Polling causes navigation or focus churn] → Reuse background-refresh behavior that does not trigger workspace navigation effects.
- [A source emits an unexpected `source_type`] → The response reports the canonical inventory type while counts group by canonical `source`; tests preserve the ingestion contracts that assign source types.

## Migration Plan

1. Mac AI implements and verifies the shared source inventory and backend aggregation contract.
2. Mac AI adds the API and focused backend tests, then implements and verifies the frontend workspace.
3. Mac AI runs focused regression tests, production build, accessibility/dark-theme/browser checks, `git diff --check`, and strict OpenSpec validation.
4. After explicit authorization, commit and push the approved Mac revision.
5. VM AI performs clean-tree preflight, syncs only the approved commit, deploys backend then frontend, and verifies the API and UI with production data.

Rollback is code-only: restore the prior backend/frontend revision and remove the navigation entry by deploying the prior approved artifact. No data or schema rollback is expected.

## Open Questions

- Confirm during implementation whether existing `(source)` and `(created_at)` indexes produce an acceptable plan at production-like volume; this is an evidence gate, not pre-authorization for a migration.
- Confirm whether viewer-role users should remain excluded with Live Logs or whether product policy separately expands both workspaces; this change defaults to the existing analyst/super-admin event-read boundary.
