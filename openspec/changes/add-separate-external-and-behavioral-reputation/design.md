# Design: Separate External and Behavioral Reputation

## Current Backend Flow

Alert creation calls `lookup_ip_reputation()` and stores the result in alert columns:

- `reputation_score`
- `reputation_label`
- `reputation_source`
- `reputation_summary`

This happens in detection alert creation and correlation alert creation. The stored values represent external threat intelligence or provider fallback:

- `abuseipdb`
- `mock`
- `fallback`
- test/provider-specific values in tests

`GET /alerts` selects stored reputation fields from `alerts`, then recomputes internal behavioral reputation with `get_ip_reputation(source_ip, cur=cur)`. The response currently writes the internal score into the top-level `reputation_*` keys and hardcodes `reputation_source` to `siem_internal`.

`GET /events/search` also uses `get_ip_reputation()`. That is appropriate because events do not have a persisted external reputation snapshot.

`POST /alerts/backfill-reputation` uses `lookup_ip_reputation()` to update stored alert reputation fields for missing/mock/fallback rows and missing response metadata.

Report/export helpers use stored alert reputation fields.

## Proposed API Shape

For `GET /alerts`, top-level `reputation_*` should represent the stored external threat-intelligence snapshot:

```json
{
  "reputation_score": 65,
  "reputation_label": "medium-risk",
  "reputation_source": "abuseipdb",
  "reputation_summary": "AbuseIPDB confidence score 65"
}
```

Add a separate object for current internal behavioral reputation:

```json
{
  "behavioral_reputation": {
    "score": 11,
    "label": "High Risk",
    "source": "siem_internal",
    "summary": "Password spraying activity and port scan activity",
    "contributing_signals": [
      {
        "signal": "password_spraying_threshold",
        "label": "Password Spraying",
        "count": 1,
        "weight": 5,
        "total": 5
      }
    ]
  }
}
```

Optionally include a second explicit external object for clarity:

```json
{
  "external_reputation": {
    "score": 65,
    "label": "medium-risk",
    "source": "abuseipdb",
    "summary": "AbuseIPDB confidence score 65"
  }
}
```

Implementation should prefer keeping existing top-level `reputation_*` fields as the stored external value for compatibility, while adding `behavioral_reputation` for the internal score.

## Backend Changes

### `GET /alerts`

Keep selecting stored alert reputation columns.

Return:

- top-level `reputation_*` from the selected row
- `behavioral_reputation` from `get_ip_reputation()`
- `contributing_signals` may remain temporarily for compatibility, but should be sourced from `behavioral_reputation.contributing_signals`

Do not hardcode top-level `reputation_source` to `siem_internal`.

### `GET /events/search`

Events do not store external reputation, so event search can keep returning internal behavioral reputation in its existing top-level fields.

If naming clarity is needed, implementation may add `behavioral_reputation` to event search too, but this is not required for the core alert fix.

### Alert Creation

No detection or correlation matching logic should change.

Alert creation should continue storing `lookup_ip_reputation()` results in existing `alerts.reputation_*` columns.

### Backfill

`POST /alerts/backfill-reputation` should remain an external threat-intelligence backfill route. It should keep using `lookup_ip_reputation()`.

Tests and documentation should make clear that it backfills stored external alert reputation, not behavioral reputation.

### Reports and Exports

Report helpers currently use stored alert reputation fields. They should label these fields as external threat intelligence. If behavioral reputation is needed in reports later, that should be additive and explicit.

## Frontend Changes

Alert views should display two separate sections or adjacent values:

- External Threat Intelligence Reputation
  - uses `alert.reputation_score`
  - uses `alert.reputation_label`
  - uses `alert.reputation_source`
  - uses `alert.reputation_summary`
- Behavioral Reputation
  - uses `alert.behavioral_reputation.score`
  - uses `alert.behavioral_reputation.label`
  - uses `alert.behavioral_reputation.source`
  - uses `alert.behavioral_reputation.summary`
  - uses `alert.behavioral_reputation.contributing_signals`

Frontend locations expected to change:

- `frontend/src/components/AlertTableRow.js`
- `frontend/src/components/AlertReputationDetails.js`
- `frontend/src/components/AlertDetailsPanel.js`
- `frontend/src/components/AlertCorrelationSignals.js`
- `frontend/src/components/MapView.js`
- `frontend/src/utils/alertDisplay.js` only if badge styling needs to support both label vocabularies.

Threat hunt event views can remain behavioral-only:

- `frontend/src/components/ThreatHuntPanel.js`
- `frontend/src/components/ThreatHuntEventDetails.js`

## Backward Compatibility

Keep top-level `reputation_*` fields in `/alerts`.

Keep `contributing_signals` temporarily if existing components rely on it, but align it with `behavioral_reputation.contributing_signals`. Future cleanup can remove or de-emphasize the top-level alias after the frontend uses the nested object.

Do not rename existing database columns.

Do not add schema unless implementation discovers a hard requirement. Existing columns already store the external snapshot.

## Schema Decision

No schema change is required for this change.

Existing `alerts.reputation_*` columns are sufficient for stored external threat-intelligence reputation. The internal behavioral score is dynamic and should not be persisted unless a future retention/history requirement is introduced.

## Test Strategy

Backend API tests should prove:

- Stored alert `reputation_*` values are returned unchanged by `GET /alerts`.
- `GET /alerts` includes a separate `behavioral_reputation` object.
- Behavioral reputation contains `score`, `label`, `source`, `summary`, and `contributing_signals`.
- Top-level `reputation_source` is not overwritten with `siem_internal`.
- `POST /alerts/backfill-reputation` still updates stored external reputation using `lookup_ip_reputation()`.
- `GET /events/search` remains behaviorally scored.

Frontend tests should prove:

- Alert table/detail views display external threat-intelligence reputation separately from behavioral reputation.
- Contributing signals render from behavioral reputation.
- Map alert details do not show a single ambiguous reputation value.
- Event search still labels its score as behavioral reputation.

