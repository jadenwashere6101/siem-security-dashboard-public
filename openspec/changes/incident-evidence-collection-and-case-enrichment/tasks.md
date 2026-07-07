This spec's authoring step (creating proposal.md/design.md/tasks.md/specs/) makes no code changes. Section 1 reflects the verification work completed to write this spec. Section 2 lists this same spec's own future implementation work — owned here, not deferred to another child spec — to be executed only in a separate, later, explicitly-requested implementation pass.

## 1. Verification (completed as part of writing this spec)

- [x] 1.1 Confirm the current `incidents`/`incident_alerts` schema has no evidence or enrichment-snapshot columns (`schema.sql`, `migrations/0004_soar_incidents.sql`).
- [x] 1.2 Confirm `core/incident_store.py`'s `create_incident`/`maybe_create_or_link_incident` write only scalar fields today, and trace the exact ingest call sites (`routes/ingest_routes.py:_create_incidents_for_alerts`) to confirm incident creation always runs after the triggering alert's row is committed and before any playbook execution is scheduled.
- [x] 1.3 Confirm `routes/incident_routes.py`'s `get_incident_detail` and `build_readonly_incident_timeline` are fully live/recomputed on every read, with no stored point-in-time view anywhere today.
- [x] 1.4 Confirm AbuseIPDB reputation (`core/ip_helpers.lookup_ip_reputation`) is already invoked at alert-generation time (`engines/detection_engine.py`, `engines/correlation_engine.py`) and already persisted immutably onto `alerts.reputation_*` columns — distinguishing it from the separate, live behavioral-reputation function `get_ip_reputation`.
- [x] 1.5 Confirm MITRE mapping (`helpers/enrichment_helpers.enrich_alert_with_mitre`) is a pure, deterministic function of `alert_type`, not persisted anywhere today.
- [x] 1.6 Confirm correlation context is already captured on `alerts.context` and already has an established whitelist/safe-projection helper (`_safe_correlation_context`, `CORRELATION_CONTEXT_RESPONSE_KEYS`).
- [x] 1.7 Confirm `engines/playbook_engine._fetch_alert` is the existing, already-reused canonical full-alert-row reader, suitable for reuse here.
- [x] 1.8 Confirm `core/soar_response_outcomes.redact_soar_outcome_metadata` is the established redaction convention in this codebase, and evaluate reusing it for evidence redaction.
- [x] 1.9 Confirm playbook execution history, response outcomes, and analyst notes are all durable but not yet populated at the moment incident creation normally runs — determining these must stay live/out-of-snapshot-scope rather than being captured.
- [x] 1.10 Document the evidence classification table, enrichment flow, data model choice, redaction approach, and non-goals in `design.md`.

## 2. Implementation (this spec's own future work — not started, not part of this authoring step)

- [ ] 2.1 Add a migration extending `incidents` with `evidence_snapshot JSONB`, `evidence_captured_at TIMESTAMPTZ`, `evidence_schema_version SMALLINT`, and update `schema.sql` to match.
- [ ] 2.2 Extend `core/incident_store.create_incident` (or a helper it calls) to fetch the triggering alert via `engines.playbook_engine._fetch_alert`, derive MITRE fields via `helpers.enrichment_helpers.enrich_alert_with_mitre`, extract the correlation-context subset when applicable, redact the assembled dict, and persist it in the same transaction as the incident insert.
- [ ] 2.3 Export a public equivalent of `helpers/enrichment_helpers.py`'s correlation-subset logic if needed for reuse outside that module.
- [ ] 2.4 Decide whether to import `core/soar_response_outcomes.py`'s redaction logic directly or extract it into a shared helper; apply it to the assembled evidence dict.
- [ ] 2.5 Extend `routes/incident_routes.py`'s `GET /incidents/:id` response to include the three new fields; add an `INCIDENT_EVIDENCE_CAPTURED` audit-log call at capture time using the existing `log_audit_event` pattern.
- [ ] 2.6 Add tests: snapshot field-for-field correctness, MITRE/correlation derivation, redaction applied, immutability across `update_incident_status` and `link_alert_to_incident`, and route-level response shape including graceful `null` handling for pre-existing incidents.
- [ ] 2.7 Run the full existing incident and ingest test suites and confirm zero regressions to incident creation/linking behavior for every field that existed before this change.

## Safety Boundaries (for this authoring step)

- [x] Creating this spec's proposal/design/tasks/spec files makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] No new engine capability, playbook content, UI redesign, or dependency is introduced by this spec.
- [x] Do not commit.
- [x] Do not push.
