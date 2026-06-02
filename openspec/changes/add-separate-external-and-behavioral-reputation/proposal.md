# Proposal: Separate External Threat Intelligence and Behavioral Reputation

## Problem

Alert creation stores reputation fields from `lookup_ip_reputation()`. Those fields are an external threat-intelligence snapshot: AbuseIPDB when configured, or mock/fallback values otherwise.

The `GET /alerts` API currently selects those stored alert fields, but then recomputes an internal SIEM behavioral score with `get_ip_reputation()` and returns that dynamic internal score in the same response fields:

- `reputation_score`
- `reputation_label`
- `reputation_source`
- `reputation_summary`

This causes the API to overwrite the meaning of the stored fields at read time. Analysts can see a dynamic internal reputation while believing they are seeing the persisted alert reputation. AbuseIPDB enrichment is therefore not clearly visible even though it is stored on the alert.

## Audit Summary

Backend locations involved:

- `core/ip_helpers.py`
  - `lookup_ip_reputation()` performs external/mock/fallback reputation lookup.
  - `get_ip_reputation()` computes internal behavioral reputation from existing SIEM alerts and active blocklist entries.
  - `determine_response_action()` uses the external lookup score during alert creation/backfill.
- `engines/detection_engine.py`
  - All detection alert creation paths call `lookup_ip_reputation()` and store `alerts.reputation_*`.
- `engines/correlation_engine.py`
  - Correlation alert creation calls `lookup_ip_reputation()` and stores `alerts.reputation_*`.
- `routes/alerts_events_routes.py`
  - `GET /alerts` currently recomputes behavioral reputation with `get_ip_reputation()` and returns it under `reputation_*`.
  - `POST /alerts/backfill-reputation` updates stored `alerts.reputation_*` using `lookup_ip_reputation()`.
  - `GET /events/search` returns internal behavioral reputation for events, which is correct because events do not store an external reputation snapshot.
- `engines/playbook_engine.py`
  - Playbook trigger evaluation reads stored alert `reputation_score` from the database.
- `helpers/query_helpers.py` and `helpers/reporting_helpers.py`
  - Report/export paths use stored alert reputation fields.

Frontend locations involved:

- `frontend/src/components/AlertTableRow.js`
  - Displays `alert.reputation_label` and `alert.reputation_score`; tooltip currently labels it behavioral reputation.
- `frontend/src/components/AlertReputationDetails.js`
  - Displays `alert.reputation_*` as behavioral reputation.
- `frontend/src/components/AlertDetailsPanel.js`
  - Displays `alert.reputation_*` as behavioral reputation.
- `frontend/src/components/AlertCorrelationSignals.js`
  - Displays `alert.contributing_signals`.
- `frontend/src/components/MapView.js`
  - Displays generic `Reputation` using `selectedAlert.reputation_*`.
- `frontend/src/utils/alertDisplay.js`
  - Provides shared reputation badge styling.
- `frontend/src/components/ThreatHuntPanel.js` and `frontend/src/components/ThreatHuntEventDetails.js`
  - Display event-search reputation as behavioral reputation. This path should remain internal behavioral scoring because events do not persist external reputation.

## Goals

- Preserve stored alert `reputation_*` fields as the canonical creation-time external threat-intelligence reputation.
- Make AbuseIPDB/mock/fallback source visible and unambiguous to analysts.
- Keep internal SIEM behavioral reputation available as a separate concept.
- Add a separate API object for dynamic internal behavioral reputation.
- Update frontend alert views to display both:
  - External Threat Intelligence Reputation
  - Behavioral Reputation
- Preserve backward compatibility where practical.
- Avoid fake or misleading reputation overwriting.

## Non-Goals

- Do not remove AbuseIPDB support.
- Do not remove mock/fallback external reputation behavior.
- Do not remove internal SIEM behavioral scoring.
- Do not redesign detection logic.
- Do not redesign threat-intelligence providers.
- Do not change playbook trigger semantics without explicit review.
- Do not change event search reputation semantics except for naming clarity if needed.
- Do not perform schema migration unless implementation proves it is needed.

## User-Visible Behavior

Analysts should see two distinct reputation concepts for alerts:

- External Threat Intelligence Reputation: the stored snapshot from alert creation/backfill, including provider/source.
- Behavioral Reputation: the current internal SIEM-derived score, summary, and contributing signals.

Existing top-level `reputation_*` fields should continue to represent the stored alert reputation where practical. New UI should not imply those fields are behavioral if they are external.

## Risks

- Frontend components currently assume `alert.reputation_*` is behavioral in several places.
- Existing API contract tests currently patch `get_ip_reputation()` and expect top-level `reputation_*` to reflect internal behavioral values.
- Existing consumers may rely on current overwritten top-level fields.
- Labels and badge styling may need to handle both AbuseIPDB-style labels and internal behavioral labels.
- Playbook triggers already use stored `reputation_score`; changing `/alerts` should not accidentally change playbook matching.

## Rollback Plan

This change should be additive at the API level. If frontend changes cause confusion, revert frontend rendering to the prior single reputation display while keeping the new backend object available.

If backend API changes cause compatibility issues, keep top-level `reputation_*` fields populated and add `behavioral_reputation` without removing any fields. Avoid schema changes so rollback is limited to route/frontend code.

