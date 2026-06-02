# Proposal: Add Structured Correlation Alert Context

## Problem

Events preserve original telemetry in `events.raw_payload JSONB`, but alerts currently do not have `raw_payload`, `metadata`, `context`, or any other JSONB field.

Correlation alert context is therefore limited to normal alert columns and generated message text. The current `/alerts` enrichment helper derives `correlated_alert_types` for `correlated_activity` by parsing the alert message for the `involving:` marker. Targeted correlation alert types do not have equivalent durable structured context.

This makes correlation explanations brittle, hard to query, and dependent on message wording. If alert messages change, the derived context can break. If analysts need contributing alert IDs, sources, source types, matched window, or matched rule identity, that information is not durably available on the correlation alert.

## Goals

- Add a durable structured context field to alerts, using `alerts.context JSONB NOT NULL DEFAULT '{}'::jsonb` or an equivalent reviewed name.
- Preserve existing behavior for non-correlation alerts by storing an empty JSON object by default.
- Store structured correlation context when creating correlation alerts.
- Include, where available:
  - `contributing_alert_ids`
  - `contributing_alert_types`
  - `contributing_sources`
  - `contributing_source_types`
  - `matched_rule_id` or `correlation_type`
  - `matched_window_minutes`
  - `matched_alert_count`
- Store structured context for all current correlation alert types:
  - `correlated_activity`
  - `web_to_app_attack_pattern`
  - `spray_then_success_pattern`
  - `cloud_app_error_pattern`
- Update `/alerts` enrichment to prefer structured alert context.
- Preserve safe fallback parsing for old alerts with empty context.
- Keep API compatibility for existing consumers.

## Non-Goals

- Do not store full raw event payloads inside `alerts.context`.
- Do not change `events.raw_payload` behavior.
- Do not change correlation matching logic.
- Do not change detection rule logic.
- Do not change alert schemas beyond the reviewed additive context column.
- Do not change SOAR queue, playbook scheduling, idempotency, approvals, retries, leases, dead letters, or integration adapter behavior.
- Do not change frontend code unless backend API compatibility proves insufficient.
- Do not backfill full historical correlation context that cannot be reconstructed accurately.

## User-Visible Behavior

Analysts and API consumers should continue seeing the same alert fields they see today. For correlation alerts, `/alerts` should provide more reliable context fields derived from `alerts.context` instead of message parsing when structured context exists.

Old correlation alerts with empty context should still degrade safely. For `correlated_activity`, the existing message parser should remain as a fallback so historical alerts can still expose `correlated_alert_types` when the message has the old `involving:` format.

Non-correlation alerts should continue to work with an empty context object and should not gain misleading correlation fields.

## Risks

- Adding an `alerts.context` column requires an additive schema migration and a `schema.sql` snapshot update.
- API responses could accidentally change shape if enrichment is not carefully layered.
- Structured context could expose too much data if it stores raw event payloads or sensitive fields.
- Historical alerts cannot be fully backfilled without re-deriving from prior alert state, which may be inaccurate after alert status changes.
- Tests that rely on exact alert insert column lists may need updates.

## Rollback Plan

If implementation causes issues before deployment, revert code changes and the migration before applying it.

If the migration has already been applied, leave the additive `alerts.context` column in place and revert runtime use of it. Because the column is additive and defaults to `{}`, existing insert/read paths can continue to operate. A later cleanup migration can drop the column only after confirming no deployed code depends on it.

