# Design: Structured Correlation Alert Context

## Current Flow

The `events` table stores raw telemetry in `events.raw_payload JSONB`.

The `alerts` table currently stores scalar alert fields only. Correlation alert creation writes standard alert columns such as `alert_type`, `severity`, `source_ip`, `source`, `source_type`, `message`, status, geo, reputation, and response fields.

For `correlated_activity`, the engine builds a message like:

```text
Multi-source suspicious activity detected from <source_ip> involving: <type>, <type>
```

`enrich_alert_with_correlation_context()` currently parses that message text to derive:

- `is_correlation_alert`
- `correlated_alert_types`
- `correlated_alert_count`

Targeted correlation alerts are created with fixed messages and do not persist their matched groups, contributing alert IDs, or matched window in structured form.

## Proposed Schema

Add an additive migration for:

```sql
ALTER TABLE alerts
ADD COLUMN IF NOT EXISTS context JSONB NOT NULL DEFAULT '{}'::jsonb;
```

Update `schema.sql` so fresh schemas include:

```sql
context JSONB NOT NULL DEFAULT '{}'::jsonb
```

The column name `context` is preferred because it describes analyst-facing structured explanation data. If implementation discovers a naming conflict or stronger local convention, `metadata` is acceptable only if reviewed before implementation.

## Proposed Context JSON Shape

Use a compact JSON object. Do not store full raw event payloads.

For `correlated_activity`:

```json
{
  "correlation_type": "correlated_activity",
  "matched_rule_id": "correlated_activity",
  "matched_window_minutes": 15,
  "matched_alert_count": 2,
  "contributing_alert_ids": [101, 102],
  "contributing_alert_types": ["port_scan_threshold", "failed_login_threshold"],
  "contributing_sources": ["nginx", "bank_app"],
  "contributing_source_types": ["web_log", "custom"]
}
```

For targeted correlation alerts:

```json
{
  "correlation_type": "targeted_correlation",
  "matched_rule_id": "web_to_app_attack_pattern",
  "matched_window_minutes": 10,
  "matched_alert_count": 2,
  "matched_groups": ["nginx_web", "bank_app_custom"],
  "contributing_alert_ids": [201, 202],
  "contributing_alert_types": ["http_error_threshold", "failed_login_threshold"],
  "contributing_sources": ["nginx", "bank_app"],
  "contributing_source_types": ["web_log", "custom"]
}
```

Use deterministic ordering based on the same rows already selected by correlation logic, unless implementation finds a safer local ordering convention. Deduplicate list fields while preserving useful order.

## Correlation Insert Behavior

Correlation matching logic must remain unchanged.

When `generate_correlated_activity_alerts()` creates an alert, it should build a context object from the already selected qualifying alert rows and persist it into `alerts.context`.

When `generate_targeted_correlation_alerts()` creates one of the targeted alert types, it should build a context object from the already selected qualifying rows and matched groups and persist it into `alerts.context`.

The existing alert message should remain human-readable and should not become the source of truth for structured context.

Non-correlation alert creation does not need to pass an explicit context value because the database default should provide `{}`. If explicit values are easier for some insert helpers, they must be `{}` for non-correlation alerts.

## API Enrichment Behavior

The `/alerts` query should include `alerts.context`.

`enrich_alert_with_correlation_context()` should prefer structured context when present and valid. For correlation alert types, it should derive API response fields from `context`, such as:

- `is_correlation_alert`
- `correlated_alert_types`
- `correlated_alert_count`
- optionally `correlation_context`, containing safe structured fields from `alerts.context`

The helper should not expose raw event payloads because none should be stored in context.

The helper should keep safe fallback parsing for older `correlated_activity` alerts whose context is `{}` or missing but whose message still contains the `involving:` marker.

## Backward Compatibility

The migration is additive and defaults to `{}`, so existing alert inserts should continue to work.

Existing API consumers should keep receiving the current top-level correlation fields. New structured context can be additive.

Historical alerts:

- `correlated_activity` with old message format can still use fallback parsing.
- Targeted correlation alerts created before this change will have empty context. The API should mark them as correlation alerts if that is existing or desired behavior, but it must not invent missing contributing IDs or matched groups.

## Test Strategy

Schema and migration tests should verify:

- The migration adds `alerts.context JSONB NOT NULL DEFAULT '{}'::jsonb`.
- The schema snapshot includes the same column.
- Existing inserts that omit `context` still succeed and store `{}`.

Correlation tests should verify:

- `correlated_activity` persists contributing alert IDs, types, sources, source types, matched window, count, and rule identity.
- `web_to_app_attack_pattern` persists targeted context, including matched groups.
- `spray_then_success_pattern` persists targeted context.
- `cloud_app_error_pattern` persists targeted context.
- Duplicate suppression remains unchanged.
- Correlation matching logic remains unchanged.

API/enrichment tests should verify:

- `/alerts` prefers `alerts.context` over message parsing when context exists.
- Old `correlated_activity` alerts with empty context still parse message text safely.
- Old targeted correlation alerts with empty context do not get fabricated contributing details.
- Unknown or malformed context does not break alert serialization.
- Non-correlation alerts expose no misleading correlation context.

