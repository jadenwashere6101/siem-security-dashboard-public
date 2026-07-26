## Context

Recon enrollment currently happens from pfSense alert ingest through `enroll_alert_in_recon_activity()`. Activities are grouped by protected range, service signature, and a 30-minute overlap window, then summarized into `recon_activities.summary`. The SOC Command Center calls `loadReconActivities({ limit: SOURCE_LIMIT })`, displays only `slice(0, 8)`, and loads a single detail payload with all linked alerts currently returned inline.

The current intelligence model treats campaign linkage too loosely. `build_campaign_intelligence()` can mark campaign evidence present from limited activity membership, and display code can surface "Campaign-linked recon" even when the activity has one alert, one source, a short duration, and no incident relationship.

## Goals / Non-Goals

**Goals:**

- Give analysts complete recon history access through a dedicated, bounded Recon workspace.
- Keep SOC Command Center recon content as a curated operational summary, not a full history browser.
- Replace boolean campaign presentation with evidence-gated recon intelligence tiers.
- Preserve existing ingest, detection, alert creation, SOAR, notification, and AI behavior.
- Reuse existing `recon_activities`, `recon_activity_alerts`, `summary`, and `membership_evidence` fields unless implementation proves a schema/index is required.
- Add focused backend, frontend, and browser verification for list pagination, filtering, detail paging, and confidence labels.

**Non-Goals:**

- No detection-rule redesign.
- No changes to pfSense ingest semantics.
- No SOAR, AI, notification, incident, or response workflow redesign.
- No database redesign or migration unless performance testing shows existing indexes are insufficient.
- No infinite-scroll command-center dashboard.

## Decisions

1. **Add a dedicated Recon workspace for complete history.**
   - The Command Center remains a compact summary of recent/high-priority recon and includes an obvious pivot to the Recon workspace.
   - The Recon workspace owns pagination, filters, search, time ranges, and investigation pivots.
   - Alternative rejected: increasing the Command Center limit or adding infinite scroll. That would turn an operational summary into a history dump and make repeated triage slower.

2. **Extend `/recon-activities` into a paginated history API.**
   - Add `limit`, `offset`, `status`, `severity`, `confidence`, `classification`, `search`, `time_range`, `start_time`, `end_time`, and `sort` query support.
   - Return `items`, `total`, `limit`, `offset`, `sort`, and applied filter metadata.
   - Preserve default behavior for existing callers by keeping a bounded default result set ordered by `last_seen DESC`.

3. **Paginate linked alerts separately from recon detail.**
   - Keep `/recon-activities/<id>` as a compact detail summary.
   - Add or extend a linked-alert endpoint such as `/recon-activities/<id>/alerts` with `limit`, `offset`, and sort.
   - This avoids oversized detail payloads and lets analysts inspect complete linked alert history incrementally.

4. **Introduce evidence-gated recon classification.**
   - Compute a projection with `classification`, `confidence`, `score`, `reasons`, `missing_evidence`, and `recommended_action`.
   - Use tiers: `recon_cluster`, `possible_campaign`, `campaign_recon`.
   - Campaign-grade recon requires multiple evidence categories, not only activity membership. Required contributors should include combinations of source diversity, linked alert count, duration, target/service consistency, alert-type diversity, incident correlation, and attack progression.
   - Weak one-alert/one-source/short-duration activities remain visible as low-confidence clusters but must not be labeled as campaign recon.

5. **Store or compute intelligence in the recon store boundary.**
   - Implement scoring in `core/recon_activity_store.py` or a small helper imported by it.
   - Persist the projection into `summary` if it is useful for list performance; otherwise compute it from existing summary fields for responses.
   - Existing notification and AI paths can consume the new projection labels without changing their execution behavior.

6. **Documentation updates are implementation-scoped.**
   - No AGENTS or source-of-truth policy changes are expected.
   - Add a short behavior note if implementation introduces new recon terminology or analyst-facing confidence tiers.

## Risks / Trade-offs

- [Risk] Over-strict thresholds could hide useful early recon. -> Keep weak activity visible as `recon_cluster` while suppressing campaign wording.
- [Risk] Full history queries could become slow. -> Use bounded pagination and existing `idx_recon_activities_activity_status` / `idx_recon_activities_range_status`; add an index only if query-plan tests justify it.
- [Risk] Changing labels may affect notifications or AI prompts. -> Keep payload fields backward-compatible and add new classification fields instead of removing existing summary fields.
- [Risk] Analysts may miss the full history entry point. -> Add an explicit Command Center action to open the Recon workspace with current filters.

## Migration Plan

- Implement backend changes first behind backward-compatible API defaults.
- Add frontend Recon workspace and Command Center pivot.
- If no schema/index is needed, rollback is code-only: revert the API/UI changes and old bounded behavior remains.
- If an index is justified during implementation, create an additive migration and update `schema.sql`; rollback should leave the additive index harmless or document a VM-only drop plan.

## Open Questions

- Exact confidence threshold constants should be finalized during implementation using current tests and representative local data.
- Whether the new Recon workspace should be a new sidebar section or a subview launched from the SOC Command Center depends on existing section configuration ergonomics; the preferred default is a dedicated section if navigation supports it cleanly.
