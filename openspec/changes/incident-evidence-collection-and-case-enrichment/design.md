## Executive Summary

Today, opening an incident (`core/incident_store.create_incident`) writes exactly five investigative fields: `title`, `severity`, `priority`, `source_ip`, `status`. Everything else an analyst needs — the triggering alert's reputation data, MITRE mapping, correlation context, and later playbook/response activity — is either not captured at all, or is recomputed live on every read (`build_readonly_incident_timeline`, SOC Command Center). That live-recompute model is correct and should stay for anything that changes *after* the incident opens. But nothing today freezes the state of the investigation *at the moment the incident was opened* — if the triggering alert's `status`, `response_action`, or `response_status` later change, there is no record of what was true when the analyst (or automation) first started investigating.

This spec defines a durable, immutable **evidence snapshot**, captured exactly once, synchronously, in the same transaction as incident creation. The audit below found that nearly all of the source data this needs — AbuseIPDB reputation, correlation context, MITRE mapping — is already computed and already immutable (or deterministic) elsewhere in the codebase. This spec's job is almost entirely "copy what already exists into one frozen record," not "build new enrichment." The one genuinely new judgment call is: don't try to freeze data (execution history, response outcomes, analyst notes) that provably doesn't exist yet at incident-creation time — that data correctly stays live, exactly as it is today.

## Current Incident Architecture Audit

Re-verified directly against the current code:

1. **Schema** (`schema.sql` lines 171–197, `migrations/0004_soar_incidents.sql`): `incidents` has `id, title, severity, priority, status, source_ip, assigned_to, created_at, resolved_at` — no JSONB column, no evidence concept, no MITRE/reputation fields. `incident_alerts` is a plain many-to-many join (`incident_id, alert_id, linked_at`) with `ON DELETE CASCADE` both ways.

2. **Creation flow** (`core/incident_store.py`):
   - `create_incident(conn, title, severity, source_ip)` — a single `INSERT ... RETURNING`; takes only three scalar inputs, no alert object.
   - `maybe_create_or_link_incident(conn, alert_id, severity, source_ip)` — the actual entry point. Only fires for `severity in {"HIGH", "CRITICAL"}`. First calls `find_open_incident_by_source_ip` (60-minute open-incident dedup window); if one exists, just `link_alert_to_incident` and returns it unchanged. Only when no open incident exists does it call `create_incident` (title synthesized as `f"[AUTO] {sev_upper} alert from {source_ip}"`) and then link the triggering alert.
   - **Call site**: `routes/ingest_routes.py`'s `_create_incidents_for_alerts(alerts_created, conn)`, invoked from every ingest code path (5 call sites: single event, honeypot event, Azure/OTel batch, etc.) — always *after* `conn.commit()` has already durably persisted the alert rows, and always *before* `_create_playbook_executions_for_alerts` schedules any playbook work. This ordering is load-bearing for this spec: by the time `create_incident` runs, the triggering alert row is fully committed and visible on the same connection, and no playbook execution or response action has been enqueued yet.

3. **Read/detail flow** (`routes/incident_routes.py`):
   - `get_incident_detail` joins `incident_alerts` → `alerts` live, returning current alert rows (current `status`, current everything) — not point-in-time.
   - `build_readonly_incident_timeline` is a fully live aggregation: queries `playbook_executions`, `approval_requests`, `approval_request_events`, and `audit_log` fresh on every call, unions with `serialize_incident_outcome_timeline_entries` (from `core/soar_response_outcomes.py`), sorts, and returns — nothing here is stored; it is recomputed end-to-end per request. This confirms the codebase already has a deliberate, working "read many, recompute live" path for anything that changes after incident creation; this spec does not touch or duplicate it.
   - `update_incident_status` is the only other incident mutator, and only ever touches `status`/`resolved_at`.

4. **Frontend** (`frontend/src/components/IncidentsPanel.js`, `SocCommandCenter.js`): both consume `loadIncidentDetail`/`loadIncidentTimeline`/`loadIncidents` — i.e., they render whatever `incident_routes.py` returns, live, on each load. No client-side caching of a "point in time" view exists either.

**Conclusion:** every existing incident code path is either a one-time scalar write (creation, status update) or a live recompute (detail, timeline, SOC Command Center). There is no precedent for, and nothing currently prevents, adding one additional write at creation time that never gets touched again.

## Current Enrichment Audit

Re-verified directly against the current code — this is the most consequential part of the audit, because it determines how much of this spec is "new enrichment" (none) versus "reuse":

1. **AbuseIPDB reputation is already snapshotted onto the alert row at alert-creation time.** `core/ip_helpers.py:lookup_ip_reputation(ip_address)` calls the real AbuseIPDB API (or a documented mock/fallback when `SIEM_ABUSEIPDB_API_KEY`/`ABUSEIPDB_API_KEY` is unset or the call fails), and is called from `engines/detection_engine.py` and `engines/correlation_engine.py` at the moment each alert is generated. The result (`reputation_score`, `reputation_label`, `reputation_source`, `reputation_summary`) is written directly onto the `alerts` row's own columns (`schema.sql` lines 31–34) — it is **already an immutable, point-in-time record**, never updated after alert insert. This spec must copy these existing columns, not re-call `lookup_ip_reputation`.

2. **A second, separate reputation function exists and must not be confused with the above.** `core/ip_helpers.py:get_ip_reputation(source_ip, cur=None)` computes a *behavioral* score live, by aggregating this IP's alert/blocklist history from the database at query time. It is used only by `routes/source_ip_context_routes.py` (a live "Source IP Context" view) and by the alerts-list serialization in `routes/alerts_events_routes.py` — it is explicitly a live/derived view, not stored anywhere, and is out of scope for a creation-time snapshot (it changes every time new alerts arrive for that IP).

3. **MITRE mapping is a pure, deterministic function of `alert_type`, not persisted anywhere.** `helpers/enrichment_helpers.py:enrich_alert_with_mitre(alert_dict)` looks up `alert_dict["alert_type"]` in the static `MITRE_ATTACK_MAPPINGS` dict and sets three fields; `INTENTIONALLY_UNMAPPED_MITRE_ALERT_TYPES` documents alert types that deliberately get `None` mappings. No `alerts` column stores this — it is computed on read wherever needed (confirmed call site: `routes/alerts_events_routes.py`). Because it is a pure function of a value (`alert_type`) that never changes, it is safe to compute once and freeze — but note that a future edit to `MITRE_ATTACK_MAPPINGS` (e.g., a corrected technique ID) would silently change what today's alerts "map to" if evidence relied on re-computing this later; freezing it into the snapshot preserves what was actually asserted when the case was opened.

4. **Correlation context is already captured on the alert row, filtered through an existing safe-projection helper.** `alerts.context` (JSONB) is populated at alert-generation time by the correlation engine for correlation-type alerts. `helpers/enrichment_helpers.py:_safe_correlation_context(context)` already defines the exact whitelist to expose (`CORRELATION_CONTEXT_RESPONSE_KEYS`: `correlation_type`, `matched_rule_id`, `matched_window_minutes`, `matched_alert_count`, `matched_groups`, `contributing_alert_ids`, `contributing_alert_types`, `contributing_sources`, `contributing_source_types`) and how to type-check/coerce each key. This spec reuses that exact whitelist rather than exposing the raw `context` blob.

5. **The canonical full-alert-row reader already exists and is already reused across modules.** `engines/playbook_engine.py:_fetch_alert(conn, alert_id)` selects the complete evidentiary column set (`id, alert_type, severity, source_ip, source, source_type, message, status, country, city, latitude, longitude, reputation_score, reputation_label, reputation_source, reputation_summary, response_action, response_status, created_at`) and is already imported by `engines/playbook_param_binding.py` for a different purpose (parameter binding). This is the natural, already-hardened function to reuse for evidence capture too, rather than writing a fourth alert-row-reading query.

6. **A redaction convention already exists and is reused across the SOAR outcome surface.** `core/soar_response_outcomes.py:redact_soar_outcome_metadata` (plus `_unsafe_metadata_key`, `_sanitize_scalar`) denylists sensitive/webhook-shaped keys and scrubs embedded URLs from string values recursively through nested dicts/lists. This is the established, working redaction primitive in this codebase — evidence redaction should reuse it (or its extracted logic), not invent a second denylist.

7. **Analyst notes (`alert_notes` table) and response outcomes (`soar_response_decisions`/`soar_response_outcome_events`) are both already durable, already keyed to `alert_id`/`incident_id`, and both already queried live** (`routes/alert_mutation_routes.py:get_alert_notes`; `core/soar_response_outcomes.py`'s bulk/latest-outcome functions). Both are out of scope for creation-time snapshotting — see Current Evidence Audit below for why.

**Conclusion:** this spec introduces zero new external calls and zero new derivation logic. Every enrichment ingredient it needs (AbuseIPDB result, MITRE mapping, correlation context, redaction) already exists as a hardened, reusable function or column. The implementation work is assembly and one new column, not new enrichment engines.

## Current Evidence Audit

Re-verified: no evidence concept, evidence table, or evidence terminology exists anywhere in the current schema, `core/`, `routes/`, or `engines/` modules. The word "evidence" appears only in frontend UI copy (`IncidentsPanel.js`, `ApprovalsPanel.js`, `PlaybookMetricsPanel.js`) as a disclaimer — *"It is operational evidence only; it does not prove a human saw the message"* — an unrelated usage (describing the limits of delivery-tracking proof), and in `core/soar_response_outcomes_legacy.py`/`engines/playbook_step_executor.py` internal variable names describing whether a *real* (non-simulated) execution occurred. None of this is an investigation-evidence data model; there is no naming collision to resolve, but it does mean this spec is introducing a genuinely new term into the codebase's vocabulary — `evidence_snapshot` is chosen deliberately to avoid colliding with the existing "operational evidence" (execution-proof) usage.

Determining what already exists for each item in the audit brief's evidence-model checklist, against what was found above:

| Item | Already exists today? | Where |
|---|---|---|
| Triggering alert core fields | Yes | `alerts` table, read via `playbook_engine._fetch_alert` |
| Source IP | Yes (on both `alerts` and already on `incidents.source_ip`) | `incidents.source_ip`, `alerts.source_ip` |
| Destination IP | **No** — no such column exists on `events` or `alerts` anywhere in `schema.sql` | n/a |
| Usernames | Only incidentally, embedded in free text (`alerts.message` for `credential_stuffing` honeypot events via `_build_honeypot_message`) | `routes/ingest_routes.py` | 
| MITRE ATT&CK mapping | Yes, as a pure function, not persisted | `helpers/enrichment_helpers.enrich_alert_with_mitre` |
| Severity | Yes | `alerts.severity`, `incidents.severity` |
| Reputation score/label/source/summary | Yes, already immutable on the alert row | `alerts.reputation_*` |
| AbuseIPDB lookup | Yes — same as reputation columns above; do not re-call | `core/ip_helpers.lookup_ip_reputation`, already invoked at alert-creation time |
| Related alerts | Yes, as a live, growing join | `incident_alerts` |
| Correlation matches | Yes, whitelisted subset already defined | `alerts.context` + `enrichment_helpers._safe_correlation_context` |
| Detection rule | Yes, implicitly (`alert_type`, and `matched_rule_id` for correlation alerts) | `alerts.alert_type`, `alerts.context->>'matched_rule_id'` |
| Timestamps | Yes | `alerts.created_at`, `incidents.created_at` |
| Execution history | Exists, but **not yet populated at incident-creation time** in the normal flow (see below) | `playbook_executions.steps_log`, live via `build_readonly_incident_timeline` |
| Playbook execution summary | Same as above | same |
| Analyst notes | Exists per-alert, but **not yet populated at incident-creation time** (no analyst has looked at a brand-new incident yet) | `alert_notes`, `routes/alert_mutation_routes.get_alert_notes` |
| Response outcomes | Exists, but **not yet populated at incident-creation time** in the normal flow | `soar_response_decisions`/`soar_response_outcome_events`, live via `core/soar_response_outcomes.py` |

The load-bearing fact for the last three rows: per the Current Incident Architecture Audit, `_create_incidents_for_alerts` runs immediately after alert commit and strictly before `_create_playbook_executions_for_alerts` schedules any execution. In the overwhelming normal case, at the exact instant `create_incident` runs, no playbook execution, no response decision/outcome event, and no analyst note yet exists for that alert. Attempting to snapshot them would capture nothing useful and would tempt a later re-sync mechanism — exactly the "continuous synchronization" this spec's design philosophy is told to avoid. They correctly remain live-queried, exactly as they are today.

## Proposed Evidence Model

Classifying every item from the audit brief's checklist:

| Field | Classification | Disposition |
|---|---|---|
| Triggering alert (id, alert_type, severity, source_ip, source, source_type, message, status, country, city, lat/long, reputation_*, created_at) | **Required, snapshot** | Copied verbatim via `playbook_engine._fetch_alert`, frozen at creation |
| Source IP | **Required, derived** | Already on `incidents.source_ip`; also present inside the alert snapshot for redundancy-free cross-reference |
| Destination IP | **Not modeled upstream** | Excluded — no source data exists; inventing one is an ingestion change, out of scope |
| Usernames | **Optional, derived (inherited, not new)** | Only whatever is already embedded in the snapshotted `message`/`context` text; no new username-specific field or collection point is added |
| MITRE ATT&CK mapping | **Required, derived-then-frozen** | Computed once via `enrich_alert_with_mitre`, then stored as part of the snapshot (not re-derived on read) |
| Severity | **Required, snapshot** | Part of the alert snapshot; also already on `incidents.severity` |
| Reputation score/label/source/summary | **Required, snapshot (copy, not re-lookup)** | Copied from the alert row's existing immutable columns |
| AbuseIPDB lookup | **Reference only, via the reputation fields above** | No second/independent AbuseIPDB record is stored; the alert row's own snapshot-at-alert-time value is the single source of truth |
| Related alerts | **Reference only (live) + one small snapshot fact** | The *current, growing* set stays live via `incident_alerts`; the snapshot additionally records `linked_alert_ids_at_creation` (almost always just the one triggering alert) as an immutable fact about what was known at open time |
| Correlation matches | **Optional (only for correlation alert types), snapshot** | Whitelisted subset of `alerts.context` via `_safe_correlation_context`, omitted (not null-padded) for non-correlation alert types |
| Detection rule | **Required, derived** | `alert_type` (and `matched_rule_id` when present) — already inside the alert snapshot / correlation subset |
| Timestamps | **Required, snapshot** | Triggering alert's `created_at`, plus the snapshot's own `captured_at` |
| Execution history | **Out of scope — reference only, live** | Doesn't exist yet at creation time; continues to be served by `build_readonly_incident_timeline` |
| Playbook execution summary | **Out of scope — reference only, live** | Same reasoning |
| Analyst notes | **Out of scope — reference only, live** | Same reasoning |
| Response outcomes | **Out of scope — reference only, live** | Same reasoning |

The resulting snapshot is deliberately compact: one alert's worth of already-computed fields, one derived-then-frozen MITRE lookup, one whitelisted correlation subset, and one small linkage fact — not an attempt to freeze the entire incident's eventual history.

## Automatic Case Enrichment Flow

Triggered synchronously, inside the same database transaction as incident creation — no background job, no polling, no second write pass:

1. `maybe_create_or_link_incident` reaches the "no open incident exists" branch and is about to call `create_incident`.
2. `create_incident` (extended) fetches the full triggering-alert row via the existing `engines.playbook_engine._fetch_alert(conn, alert_id)` — the same function `dynamic-playbook-parameter-binding` already reuses for a different purpose. No new query shape is introduced.
3. `helpers.enrichment_helpers.enrich_alert_with_mitre` is called once against the fetched alert's `alert_type`, exactly as already happens for alert-list serialization — reused, not duplicated.
4. If the alert's `alert_type` is a correlation type (`helpers.enrichment_helpers.CORRELATION_ALERT_TYPES`), the whitelisted subset of `alerts.context` is extracted using the same logic as `_safe_correlation_context`; otherwise this section is omitted from the snapshot entirely.
5. The assembled dict (triggering-alert fields + MITRE fields + optional correlation subset + `linked_alert_ids_at_creation: [alert_id]` + `captured_at` + `schema_version`) is passed through the shared redaction pass (reusing `core.soar_response_outcomes.redact_soar_outcome_metadata`'s logic) to strip denylisted keys and scrub embedded URLs, exactly as SOAR outcome metadata already is.
6. The redacted dict is written to the new `incidents.evidence_snapshot` column (via `psycopg2.extras.Json`, the same serialization convention already used in `core/playbook_store.py`) as part of the same `INSERT` that creates the incident row — one transaction, one write, no follow-up update.
7. When `maybe_create_or_link_incident` instead takes the "link to existing open incident" branch, no evidence capture happens at all — `link_alert_to_incident` is unchanged, and the existing incident's `evidence_snapshot` is left exactly as it was when that incident was first opened.

No polling, no background refresh, no second enrichment engine, and no new outbound calls (AbuseIPDB, geo lookup, or otherwise) are introduced anywhere in this flow.

## Data Model

**Chosen approach: extend the existing `incidents` table with three columns**, not a new table:

```sql
ALTER TABLE incidents
    ADD COLUMN evidence_snapshot JSONB,
    ADD COLUMN evidence_captured_at TIMESTAMPTZ,
    ADD COLUMN evidence_schema_version SMALLINT;
```

- `evidence_snapshot` — the redacted JSON document described above; `NULL` for incidents created before this capability existed (no backfill attempted or required) and for any future incident where capture is intentionally skipped.
- `evidence_captured_at` — set once, alongside the snapshot; lets an analyst or query filter on "when was this evidence produced" without unpacking JSONB, and doubles as the immutability tell (if it's set, the snapshot has never been touched since).
- `evidence_schema_version` — a small integer (starts at `1`), so a future change to the snapshot's shape doesn't require rewriting historical rows or guessing which shape an old row uses — mirrors this codebase's existing versioning instinct (`schema.sql`'s own top-of-file `-- Schema snapshot version: 0012` comment, and `playbook_param_binding`'s namespace-based extensibility).

This mirrors the codebase's existing precedent for exactly this kind of data: `alerts.context JSONB`, `playbook_definitions.steps JSONB`, `playbook_executions.steps_log JSONB`, `soar_response_decisions.safe_metadata JSONB` — every other durable, structured, evolving-shape record in this schema is a JSONB column on its natural owning row, not a satellite table. A dedicated `incident_evidence` table was considered and rejected (see Alternatives Considered) because this is genuinely 1:1 and write-once — the two things that would justify a separate table (a 1:many relationship, or an independent lifecycle/retention schedule) don't apply in v1.

## Security / Redaction

- **Redaction mechanism**: reuse `core/soar_response_outcomes.py`'s `redact_soar_outcome_metadata` logic (denylisted key substrings, webhook-URL detection, recursive URL-scrub of string values) rather than inventing a second denylist. Whether the implementation pass imports it directly or extracts the shared logic into a common helper module is an implementation detail, not a spec decision — either preserves single-source-of-truth redaction rules.
- **Sensitive fields**: the snapshot introduces no field that is not already visible on the alert record today to any analyst with existing alert-read access (IPs, severity, message, reputation scores/summary). The incremental risk is purely "this content now also lives in a second place" — mitigated by applying the same redaction pass a second time at the point of copying.
- **Usernames / free text**: any username embedded in `alerts.message` (e.g., honeypot `credential_stuffing` events) is inherited as-is into the snapshot's copy of that message — this spec does not add new username-specific redaction, because doing so would change what the *existing* `alerts.message` already discloses today; that is a separate, pre-existing concern outside this spec's boundary.
- **Retention**: no independent TTL or purge scheduler is introduced in v1 (explicit non-goal). The three-column design makes a future purge trivial and cheap (`UPDATE incidents SET evidence_snapshot = NULL, evidence_captured_at = NULL WHERE ...`) without needing a second table's lifecycle to manage.
- **Immutability**: enforced structurally, not by a database trigger — `evidence_snapshot`/`evidence_captured_at`/`evidence_schema_version` are written exactly once, inside `create_incident`'s `INSERT`, and no other store function (`update_incident_status`, `link_alert_to_incident`) references these columns at all. The acceptance criteria below require a test proving this.
- **Audit logging**: reuse the existing `log_audit_event` call pattern already used by `update_incident_status_route` to record an `INCIDENT_EVIDENCE_CAPTURED` audit event at the moment of capture — for traceability of when/how evidence was produced, additive to (not a replacement for) existing RBAC.
- **Analyst permissions**: no new role or permission tier. Evidence is exposed only through the existing `GET /incidents/:id` response, already gated by `@analyst_or_super_admin_required` exactly like every other incident field — the existing incident-read boundary is the correct and sufficient boundary for evidence too.

## Auditability

- Every snapshot self-describes its provenance and shape via `captured_at` and `schema_version`, so any future viewer (UI or analyst) can immediately tell this is a point-in-time record, not live data — this is a hard invariant of the design, not an incidental detail.
- An `INCIDENT_EVIDENCE_CAPTURED` audit-log entry (reusing existing `log_audit_event` machinery) records exactly when evidence was produced for a given incident, tying the snapshot to the same audit trail every other sensitive incident action already uses.
- Because the snapshot is frozen and the live alert/incident data continues to change, comparing "evidence as captured" against "current live state" (already retrievable via the existing `get_incident_detail`) becomes a meaningful, free diff for an analyst reviewing how an investigation's understanding evolved — a natural side benefit of the immutability design, not new machinery.

## Alternatives Considered

- **A dedicated `incident_evidence` table (1:1 or 1:many).** Rejected for v1: nothing in the current design needs multiple snapshots per incident or an independent lifecycle from the incident row; the codebase's existing convention for exactly this shape of data (`alerts.context`, `playbook_executions.steps_log`, `soar_response_decisions.safe_metadata`) is a same-row JSONB column, and that is smaller.
- **Continuous synchronization — keep the snapshot updated as the alert/incident evolves.** Rejected outright per the audit brief's explicit design philosophy; it would also duplicate work `build_readonly_incident_timeline` and the SOC Command Center already do correctly, live.
- **Re-running AbuseIPDB / behavioral reputation / MITRE mapping fresh at incident-creation time instead of copying existing values.** Rejected: the alert row's reputation columns are already an immutable point-in-time record from the moment that mattered (alert generation); re-querying is a duplicate external call, could disagree with what actually drove the alert's severity, and is exactly the "duplicate enrichment logic" the brief warns against.
- **Snapshotting execution history, response outcomes, or analyst notes at creation time.** Rejected: confirmed by audit that none of this data exists yet at the moment `create_incident` runs in the normal flow; capturing it would produce empty/misleading snapshots or tempt a re-sync mechanism, contradicting "snapshot once, read many."
- **Re-capturing evidence on incident reopen (`resolved → open`).** Considered and rejected for v1 (see Risks) — the original snapshot remains valid provenance of what was known when the case was first opened; a future spec could add reopen-triggered re-snapshotting if this proves insufficient in practice.
- **Capturing destination IP or dedicated username fields.** Rejected: no such data is collected anywhere upstream today; adding it would be an ingestion/schema change for those fields specifically, not an evidence-capture change, and is explicitly out of this spec's scope.

## Implementation Scope

(For a later, separately-scoped and explicitly-requested implementation pass — not part of this spec-authoring step.)

- New migration (e.g. `migrations/00xx_incident_evidence_snapshot.sql`): `ALTER TABLE incidents ADD COLUMN evidence_snapshot JSONB, ADD COLUMN evidence_captured_at TIMESTAMPTZ, ADD COLUMN evidence_schema_version SMALLINT;` plus the corresponding `schema.sql` update.
- `core/incident_store.py`: extend `create_incident` (or add a small internal helper it calls, e.g. `_build_incident_evidence_snapshot(conn, alert_id)`) to fetch the alert via `engines.playbook_engine._fetch_alert`, derive MITRE fields via `helpers.enrichment_helpers.enrich_alert_with_mitre`, extract the correlation subset when applicable, redact, and persist alongside the existing `INSERT`.
- Possibly export a public equivalent of `helpers/enrichment_helpers.py`'s `_safe_correlation_context` for reuse outside that module (a small, non-behavior-changing visibility change).
- Possibly extract `core/soar_response_outcomes.py`'s redaction logic into a small shared helper importable by `core/incident_store.py`, to avoid `incident_store` depending on SOAR-outcome-specific internals — an implementation-detail decision, not a spec requirement either way.
- `routes/incident_routes.py`: include `evidence_snapshot`, `evidence_captured_at`, `evidence_schema_version` in the existing `GET /incidents/:id` response; optionally in `GET /incidents` list responses if useful, though the detail endpoint is the primary consumer. Add the `INCIDENT_EVIDENCE_CAPTURED` audit-log call at capture time.
- Tests: `tests/test_incident_store.py` (snapshot shape and field-for-field correctness against a known alert row, MITRE derivation, correlation-subset presence/absence, redaction applied, immutability across `update_incident_status` and re-linking), `tests/test_incident_routes.py` (response shape, `null` handling for pre-existing incidents).
- No new engine, adapter, scheduler, or UI component is required for this capability to be functionally complete and readable; a dedicated evidence-panel UI is explicitly deferred to a separate, later, UI-focused change.

## Non-goals

- Destination IP capture or any new ingestion/schema field beyond the three `incidents` columns described above.
- Username-specific redaction beyond what `alerts.message` already discloses today.
- Playbook chaining, branching, scheduler work, or manual playbook execution changes.
- UI redesign or a new evidence-viewing component (a later, separate pass may add one).
- Workflow builders, deployment changes, notification redesign, or new playbooks.
- New engine capabilities unrelated to evidence capture.
- New dependencies (no new libraries, no new external services).
- Continuous/live evidence synchronization or background refresh of any kind.
- Multiple evidence snapshots per incident (e.g., re-capture on reopen).
- A dedicated evidence table, or any retention/purge scheduling automation.

## Risks

- **[Risk]** Extending `core/incident_store.create_incident` to import `engines.playbook_engine`, `helpers.enrichment_helpers`, and a redaction helper increases that module's dependency surface, where today it has none beyond its own SQL.
  **[Mitigation]** Every function reused is already a pure/read-only, already-hardened function reused elsewhere in the codebase (`playbook_param_binding` already imports `_fetch_alert`; `alerts_events_routes` already imports both enrichment functions); no new external calls are introduced anywhere.
- **[Risk]** If incident creation is ever moved earlier in the ingest flow (before the alert-insert commit), the evidence fetch could see a not-yet-committed or missing alert row.
  **[Mitigation]** Confirmed via this audit that all five current ingest call sites already run `_create_incidents_for_alerts` strictly after `conn.commit()`; this spec's acceptance criteria pin that ordering as a requirement, not an assumption.
- **[Risk]** Copying the full `alerts.context` blob instead of the whitelisted subset could bloat `incidents` rows or leak unvetted correlation-engine internals.
  **[Mitigation]** v1 explicitly uses only the existing `CORRELATION_CONTEXT_RESPONSE_KEYS` whitelist, never the raw `context` value.
- **[Risk]** Analysts or a future UI could mistake the frozen snapshot for live data (e.g., assume `evidence_snapshot.status` reflects the alert's current status).
  **[Mitigation]** `evidence_captured_at`/`evidence_schema_version` are always returned alongside the snapshot specifically so any consumer can label it as point-in-time; documented as a hard design invariant here for any future UI work to respect.
- **[Risk]** Reopening a long-resolved incident means its evidence can become quite stale relative to the reopen date.
  **[Mitigation]** Accepted trade-off for v1 (see Alternatives Considered); the original snapshot still correctly documents what was known when the case was first opened, which remains valid investigative provenance even after reopening.

## Acceptance Criteria

- Creating a brand-new incident (the "no open incident exists" branch of `maybe_create_or_link_incident`) always populates `evidence_snapshot`, `evidence_captured_at`, and `evidence_schema_version` in the same transaction as the incident row, using only the triggering alert already committed on that connection.
- Linking an additional alert to an already-open incident (the "existing incident" branch) never creates, modifies, or clears that incident's `evidence_snapshot`.
- The snapshot's alert fields exactly match what `engines.playbook_engine._fetch_alert` returns for the triggering alert at the moment of capture.
- The snapshot's MITRE fields exactly match what `helpers.enrichment_helpers.enrich_alert_with_mitre` would derive for that alert's `alert_type`.
- The snapshot includes a correlation-context subset, matching the existing whitelist, if and only if the triggering alert's `alert_type` is a correlation type; it is omitted (not present with null values) otherwise.
- The snapshot never contains a reputation value that differs from what is already stored on the triggering alert's own row — no second AbuseIPDB or behavioral-reputation call is made.
- The snapshot has passed through the shared redaction pass before being persisted (denylisted keys absent, embedded URLs scrubbed).
- No store function other than the creation path ever writes to `evidence_snapshot`/`evidence_captured_at`/`evidence_schema_version` — verified directly by a test that calls `update_incident_status` and `link_alert_to_incident` and asserts these three columns are unchanged.
- `GET /incidents/:id` returns `evidence_snapshot`, `evidence_captured_at`, and `evidence_schema_version` for incidents that have them, and returns `null`/absent gracefully (no error, no backfill attempted) for incidents created before this capability existed.

## Validation Plan

- `openspec validate incident-evidence-collection-and-case-enrichment --strict` must pass as part of this spec-authoring step (no code involved).
- For the later implementation pass: unit tests in `tests/test_incident_store.py` covering every acceptance-criteria bullet above (snapshot correctness, MITRE/correlation derivation, redaction, immutability across both `update_incident_status` and re-linking); route-level tests in `tests/test_incident_routes.py` for response shape and graceful `null` handling; a migration smoke test applying the new columns to a database already containing incident rows; and a full run of the existing incident and ingest test suites (`test_incident_store.py`, `test_incident_routes.py`, `test_ingest_routes.py` or equivalent) to confirm zero regression to incident creation/linking behavior for every field that existed before this change.

## Overall Assessment

This audit found that the platform already computes and already durably stores almost everything a useful investigation snapshot needs — AbuseIPDB reputation on the alert row, correlation context on the alert row, a canonical alert-row reader, a working redaction primitive — and already has a correct, working live-recompute path (`build_readonly_incident_timeline`, SOC Command Center) for everything that legitimately changes after an incident opens. The right-sized capability is therefore small: one JSONB column plus two scalar columns on `incidents`, one synchronous read-and-freeze step wired into `create_incident`, and zero new enrichment engines or external calls. The harder and more valuable part of this design was determining what *not* to snapshot — execution history, response outcomes, and analyst notes all correctly stay live, because they provably don't exist yet at the moment an incident is created, and freezing them would either be empty or invite exactly the continuous-synchronization anti-pattern this capability is meant to avoid. This spec is ready for implementation once explicitly requested as a separate pass.
