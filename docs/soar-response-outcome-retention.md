# SOAR Response Outcome Retention and Archive Policy

Canonical SOAR response outcomes are stored in:

- `soar_response_decisions` — one row per selected response
- `soar_response_outcome_events` — append-only lifecycle transitions

## Default live retention window

**Indefinite by default** until an operator sets `SIEM_OUTCOME_RETENTION_DAYS`.

- Live APIs, reporting helpers, and `canonical_outcome_counts` metrics read from the live tables only.
- No automatic deletion runs in this phase.
- `SIEM_OUTCOME_RETENTION_DAYS` is parsed as a positive integer day count; blank, zero, negative, or non-numeric values are ignored and keep the default indefinite live window.

When a retention window is configured (recommended production starting point: **365 days**), events with `occurred_at` older than the threshold become eligible for archival.

## Archive criteria

Eligible for archive after the live window:

- Outcome events with `occurred_at` older than the retention threshold.
- Decision rows where all related events are archived and no live foreign-key dependencies remain.

Never deleted during routine archival:

- The terminal/latest outcome event per decision (archive a summary row first).
- Any event with `external_executed = true` (real execution audit evidence).

Archive action:

1. Write a summary row containing the preserved fields below.
2. Move or copy raw append-only events to cold storage.
3. Remove live rows only after the summary row is verified.

## Archive preservation contract

Each archived decision summary must preserve:

| Field | Purpose |
| --- | --- |
| `decision_id` | Stable decision identity |
| `soar_correlation_id` | Cross-surface lifecycle correlation |
| `selected_action` | What response was selected |
| `decision_source` | How the response was chosen |
| `execution_mode` / `execution_state` | Final canonical mode/state |
| `external_executed` | Whether anything was actually executed externally |
| `tracking_recorded` | Whether a tracking-only record was created |
| `simulated` | Whether the path completed in simulation |
| `outcome_summary` | Human-readable final summary |
| `alert_id`, `incident_id`, `queue_id` | Related workflow ids |
| `playbook_execution_id`, `approval_request_id` | Playbook and approval linkage |

These fields answer the primary analyst question:

> What happened, what response was selected, what playbook ran, and was anything actually executed?

## Reporting

Use `get_response_outcome_traceability_report(conn, alert_id=...)` (or `incident_id` / `soar_correlation_id`) to answer the analyst question from live canonical tables. Migration/backfill rows with `decision_source = migration` are included.

## Metrics boundary

`/metrics/playbooks`, `/metrics/notifications`, `/metrics/incidents`, and `/metrics/approvals` return `canonical_outcome_retention` metadata documenting that `canonical_outcome_counts` reflect live stored events only. Archived summaries are not aggregated until a dedicated archive aggregation job is deployed.
