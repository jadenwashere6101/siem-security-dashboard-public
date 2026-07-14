## Context

The current pfSense severity path starts in `engines/detection_engine.py`, where the four pfSense rules assign alert severity from threshold, breadth, direction, and reputation logic. That severity then propagates into automatic incident creation through `routes/ingest_routes.py` and `core/incident_store.py`, where `HIGH` and `CRITICAL` alerts create or link incidents and map to `P2` / `P1`. Frontend operational views consume aggregate counts from `/alerts/summary`, `/metrics/incidents`, `/admin/detection-rules/pfsense-health`, and recent alert/incident list routes, all of which currently mix older pfSense noise with current detections unless already bounded by time.

This change is intentionally narrow. It does not add new pfSense rules, delete or rewrite historical data, redesign analytics, or change notification policy. Its job is to make current pfSense operational state understandable after tuning while keeping full history available.

## Goals / Non-Goals

**Goals:**
- Lower routine pfSense alert urgency by normalizing severity behavior for the four existing pfSense alert families.
- Introduce one shared tuning-baseline concept that backend filters and frontend surfaces can reuse.
- Default operational pfSense views to `Since Tuning` and provide an explicit `All History` switch.
- Mark pre-baseline pfSense alerts and incidents as legacy/pre-tuning without changing stored records.
- Keep runtime-configurable thresholds in place and compatible with the new logic.

**Non-Goals:**
- No deletion, archival, bulk closure, or severity rewrite of historical alerts or incidents.
- No new analytics dashboard, trend redesign, or broad non-pfSense filtering overhaul.
- No notification-playbook policy changes, asset mapping, or new detection families.
- No mandatory migration unless implementation proves a configuration-only baseline cannot be applied cleanly.

## Decisions

### Use one implementation for severity normalization and baseline filtering

Keep both concerns in one change.

Rationale: pfSense operational urgency is currently a combination of detector severity plus mixed historical counts. Splitting them would leave analysts with normalized new alerts still competing against pre-tuning noise in the same dashboards and incident-pressure views.

### Prefer a lightweight configurable baseline timestamp

The tuning baseline should be represented as a configurable timestamp rather than a new persisted flag on every alert or incident.

Rationale: all required legacy/current distinctions can be computed from existing `created_at` timestamps. This preserves history, avoids data rewrites, and keeps migration risk low.

Alternative considered: backfilling a legacy flag on alerts and incidents. Rejected because it creates avoidable migration and data-maintenance work for a distinction that is derivable.

### Add one shared backend baseline filter contract

Use a common request-level filter pattern for `Since Tuning` vs `All History` across alert summary APIs, incident metrics, pfSense detection health, alert lists, incident lists, and SOC Command Center’s derived metrics.

Rationale: if each route invents its own semantics, operational counts will drift. One backend contract gives frontend surfaces a consistent definition of “current tuned operations.”

### Limit the baseline default to operational surfaces, not global history

Default only the approved operational workspaces to `Since Tuning`; preserve full-history access with an explicit toggle and keep direct record fetches/search behavior available.

Rationale: the objective is operational clarity, not hiding history.

### Keep legacy labeling additive and read-only

Legacy/pre-tuning indicators should be computed and exposed additively in API payloads or frontend view-model logic.

Rationale: analysts need visible context, but the underlying alert and incident records must remain intact and unmodified.

## Risks / Trade-offs

- Baseline semantics drift across routes -> Mitigation: define one shared backend filter/serialization contract and reuse it across alert, incident, and detection-health routes.
- Severity normalization lowers incident volume but misses some meaningful scans -> Mitigation: keep runtime threshold overrides intact and scope `high` to corroborated breadth, persistence, reputation, or outbound/internal-host significance.
- Defaulting to `Since Tuning` could obscure older still-open incidents -> Mitigation: expose an obvious `All History` switch and show legacy/pre-tuning badges on older pfSense records when they are included.
- Applying the baseline too broadly could affect unrelated sources -> Mitigation: scope the baseline contract to pfSense operational filtering behavior even where mixed-source pages are involved.

## Migration Plan

Preferred path: no migration. Represent the baseline as lightweight configuration and derive legacy/current status from existing `created_at` fields.

Fallback only if needed: introduce a minimal configuration persistence mechanism, but still avoid backfilling or mutating alert/incident history.

## Open Questions

- Whether the baseline timestamp should live in existing settings/config storage or as a narrowly scoped new configuration source.
- Whether mixed-source Dashboard widgets should apply the baseline only to pfSense-derived counts or expose a clearer “pfSense operational baseline active” indicator when totals are partially filtered.
