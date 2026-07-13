## Executive Summary

This spec turns two audit findings (a detection-noise audit and an operational-reliability audit, both conducted after the SIEM's first sustained real pfSense event stream) into a scoped, incremental improvement plan. It deliberately does **not** redesign SOAR, does not touch the frozen response-action queue, does not add a large new detection surface, and does not assume any schema migration. Its job is narrower: make the four already-implemented pfSense rules (`pfsense_firewall_repeated_deny`, `pfsense_firewall_port_scan`, `pfsense_firewall_suspicious_allow`, `pfsense_firewall_noisy_source`) behave like production detections instead of demo fixtures, and give one analyst enough in-UI context to operate the SIEM unattended for hours between check-ins.

## Current State Audit (re-verified directly against code)

1. **Threshold values are already live-editable, out of band from this spec.** `engines/detection_config.py:get_effective_detection_rule` merges module-level defaults (`PFSENSE_PORT_SCAN_THRESHOLD = 2`, `PFSENSE_SUSPICIOUS_ALLOW_THRESHOLD = 1`, `PFSENSE_REPEATED_DENY_THRESHOLD = 5`, `PFSENSE_NOISY_SOURCE_THRESHOLD = 20`, all in `detection_config.py:45-55`) with a per-`rule_id` override row in the `detection_config` table, and `routes/admin_routes.py:473` (`PATCH /admin/detection-rules/<rule_id>`) already lets a super_admin change `parameters`/`active` live, no deploy, no migration. **This spec does not need to add a mechanism for changing numbers** — an operator can retune raw thresholds today. This spec's job is the *aggregation logic* the override mechanism cannot express (what gets counted, how breadth is measured, what direction means, what happens after close).
2. **Port scan measures port breadth only.** `engines/detection_engine.py:_generate_pfsense_port_scan_alerts_core` (~line 1827) counts `COUNT(DISTINCT destination_port)` with no distinct-destination-host dimension. Two ports on one host and two ports across fifty hosts score identically.
3. **Suspicious allow is single-event and severity-hardcoded.** `_generate_pfsense_suspicious_allow_alerts_core` (~line 1991) uses `threshold=1` and hardcodes `severity = "high"` unconditionally (line ~2079, explicit comment citing the original spec's "contextual allow" guidance) — reputation and repetition are not inputs to severity at all for this rule, unlike the other three.
4. **Repeated deny is direction-agnostic.** The query (~line 1674) groups by `(source_ip, destination_ip, destination_port, protocol, interface, direction)` and includes `direction` as a grouping key already, but severity/escalation logic and the alert message treat every direction identically — there is no separate, higher-urgency handling for LAN→WAN denies (a plausible compromised-internal-host signal) versus WAN→LAN denies (routine internet noise).
5. **Dedup is open-alert-only.** All four detectors gate on `SELECT 1 FROM alerts WHERE source_ip = %s AND alert_type = %s AND status = 'open'` before inserting. There is no check against a *recently closed* alert for the same source/type — closing an alert for a still-active offender immediately re-arms it.
6. **`alerts` has no closure timestamp.** `migrations/0002_base_siem_core.sql` defines `alerts` with `status` (`open`/`resolved`, mutated by `routes/alert_mutation_routes.py:update_alert_status`) but no `resolved_at`/`closed_at` column. However, `audit_log` (from `migrations/0003_auth_rbac_and_metadata.sql`) already records every status change as an `UPDATE_ALERT_STATUS` event with `target_alert_id` (indexed: `idx_audit_log_target_alert_id`) and `created_at` (indexed: `idx_audit_log_created_at`), and `details` JSONB carrying the new status. **A cooldown window can be computed by querying the most recent matching `audit_log` row — no migration required for the primary approach.**
7. **Notification routing is uniform across investigation and containment playbooks.** `core/core_playbook_pack_v1.py`'s four pfSense playbooks all end in a `notify_slack` step; the two investigation-only playbooks (`core-v1-pfsense-repeated-deny-investigation`, the medium-severity `core-v1-pfsense-port-scan-investigation`) have identical Slack urgency to the two containment playbooks that gate `block_ip` behind `require_approval`.
8. **No "why this fired" or detection-health surface exists.** Alert `context` (JSONB, populated per-detector with fields like `event_count`, `distinct_port_count`, `first_seen`/`last_seen`) is already stored but not surfaced in a dedicated investigation view. No endpoint aggregates alert counts by `alert_type`/time to show "top firing rules" or "recently noisy."

## Detection Improvements (per rule)

- **Port scan:** add a distinct-destination-host dimension alongside distinct-port count so breadth is measured on both axes; a source hitting many ports on one host and a source sweeping many hosts on one port are different signals and should be distinguishable in the alert, not collapsed into one metric.
- **Suspicious allow:** require the aggregation window/threshold the rule already has (`window_minutes`, currently unused meaningfully at `threshold=1`) to actually gate on repetition or corroborating context (reputation, distinct sensitive ports touched) before defaulting to `high`; a single allowed connection to an intentionally-forwarded port should not always be indistinguishable from a first-time unexpected exposure.
- **Repeated deny:** make direction a first-class severity input, not just a grouping key — LAN→WAN denies get distinct handling/messaging from WAN→LAN denies given their different investigative meaning.
- **Noisy source:** unaffected in mechanism; its guard-against-masking-a-specific-alert logic is confirmed sound and is preserved as-is.
- **Cross-cutting — cooldown/suppression after close:** extend the existing open-alert dedup check with a bounded "recently closed" lookback (querying `audit_log` per finding 6) so a closed alert for a still-active source does not regenerate on the very next detection pass.
- **Cross-cutting — severity/notification split:** decouple "should this alert exist" from "should this page Slack" — investigation-only (`monitor`) playbook outcomes move to a lower-urgency/no-Slack path; containment playbook behavior (approval-gated `block_ip` + post-decision Slack) is unchanged.

## Analyst Workflow Improvements

- Alert detail gains a "why this fired" section built entirely from each alert's already-stored `context` JSON (event count, breadth counts, first/last seen, direction) — a read-only projection, not new data collection.
- Detection Health answers exactly one question — "how often has each of the four pfSense rules fired in the last 24 hours, and what's its most recent/most severe hit" — as a fixed-shape ranked list, not an open-ended analytics surface. It is intentionally the smallest useful thing: a triage starting point ("which rule needs attention first"), not a rule-effectiveness or false-positive analysis tool.

## UI Improvements (only where they directly support the above)

- "Why this fired" panel on alert detail (from `context`, no new backend concept).
- Suppression/cooldown indicator on an alert when the new cooldown logic suppressed a would-be duplicate (surfacing an existing decision, not adding one).
- Detection Health: a ranked list, one row per pfSense rule — rule name (linking to the existing `/admin/detection-rules/<rule_id>` override workspace), 24-hour fired count, highest severity observed in that window, last-fired timestamp, and — only using the fixed, non-configurable cutoffs specified in `spec.md` — an optional Noisy/Needs Review/Normal badge. Explicitly not a dashboard: no charts, no trend lines, no false-positive scoring, no AI-derived judgment, no second threshold-editing surface. Building a second way to edit thresholds here would duplicate `/admin/detection-rules/<rule_id>`, which already exists and already works — the link is the entire integration, not a reimplementation.
- No dashboard redesign, no new navigation model, no changes to unrelated panels.

## Migration Assessment

**No migration is assumed as part of this spec.** The cooldown/suppression check is designed to read `audit_log` (already indexed on `target_alert_id` and `created_at`) rather than add a column. This is explicitly flagged, not decided, because it carries a real trade-off:

- **No-migration approach (default):** query `audit_log` for the latest `UPDATE_ALERT_STATUS` row per `(target_alert_id)` at detection time. Simpler, no schema change, reuses an existing audited trail. Risk: an extra join per detection pass; audit_log is not currently pruned or partitioned, so this should be checked for query-plan cost under sustained real traffic during implementation.
- **Flagged fallback (not assumed):** add `alerts.resolved_at TIMESTAMPTZ NULL`, set on the existing `update_alert_status` transition to `resolved`. Only pursued if the audit_log join proves too slow or unreliable at implementation time — a decision for Phase 1 implementation, not this spec.

No other item in this spec (threshold logic changes, notification routing, "why fired" panel, detection health panel) requires a schema change; all read from data already persisted (`alerts.context`, `alerts.alert_type`/`created_at`, the existing `detection_config` override table).

## Non-Goals / Preserved Architecture

- Does not modify `pfsense-firewall-detections-soar`, the SOAR playbook engine, the approval-gate model, the frozen response-action queue, or ingest-time filtering (`engines/pfsense_ingest_filter.py`).
- Does not add new pfSense alert types beyond the direction-split context on `repeated_deny` (no new `alert_type` value — direction becomes richer context/severity input on the existing type).
- Does not change containment-playbook Slack timing (already post-approval-decision, already reasonable).
- Does not touch the operational-reliability findings from the separate audit (approval-expiration terminal handling, dead-letter classification) — those belong to a distinct, already-scoped reliability spec, not this one.

## Alternatives Considered

- **Only change numeric thresholds via the existing admin override, no spec at all:** rejected as insufficient — the override mechanism cannot express "count distinct hosts too," "require repetition before high severity," "suppress for N minutes after close," or "don't Slack investigation-only outcomes." Those are logic changes, not parameter changes.
- **Add a dedicated `rule_metrics`/counters table for detection health:** rejected for now — existing `alerts` rows already carry everything needed for a first-cut top-firing/noise view via aggregation queries; a dedicated rollup table is deferred unless implementation finds query cost unacceptable, in which case it would be its own explicitly-flagged migration decision, not assumed here.
- **Bundle the operational-reliability fixes (approval-expiration terminal behavior, dead-letter classification) into this spec:** rejected — different root cause (SOAR lifecycle vs. detection quality), different owner-file set, and the user-facing audit already recommended they stay a separate OpenSpec.

## Risks

- Direction-aware repeated-deny and host-breadth-aware port-scan both touch hot-path detector queries; must be validated against the existing regression suite for non-pfSense sources' unaffected behavior (shared helper functions, if any, must not regress other rules).
- Notification-severity split changes analyst-visible behavior (fewer Slack pings) — must be paired with the detection-health/"why fired" UI so reduced paging doesn't become reduced visibility.
- Cooldown-after-close, if tuned too long, could mask a genuine re-escalation (e.g., a source resumes attack shortly after an analyst closes the alert believing it resolved) — window bounds and escalation-breakout conditions (mirroring the existing noisy-source "suppression breaks on escalation" pattern) must be explicit in implementation, not implicit.
