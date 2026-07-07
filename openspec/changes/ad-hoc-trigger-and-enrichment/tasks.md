This is a design-only child spec. Creating these OpenSpec artifacts does not implement code, modify application source files, commit, or push.

## 1. Verification (completed as part of writing this spec)

- [x] 1.1 Inspect `engines/playbook_engine.py` and confirm trigger matching is read-only and automatic-alert oriented.
- [x] 1.2 Inspect `engines/playbook_step_executor.py` and confirm pending executions already share one worker/step pipeline.
- [x] 1.3 Inspect `engines/playbook_registry.py` and confirm no enrichment action exists in the registry.
- [x] 1.4 Inspect `routes/playbook_routes.py` and confirm there is no first-run manual execution endpoint.
- [x] 1.5 Inspect `core/playbook_store.py` and confirm existing execution creation helpers can support normal pending rows.
- [x] 1.6 Inspect `PlaybooksPanel`, `ThreatHuntPanel`, and `SocCommandCenter` and confirm current UI lacks manual launch affordances.
- [x] 1.7 Inspect enrichment helpers, AbuseIPDB/reputation helpers, MITRE enrichment, source-IP context, and alert context.
- [x] 1.8 Document the smallest manual trigger and enrichment design in `design.md`.

## 2. Future implementation scope (not started)

- [ ] 2.1 Add one authenticated manual execution API endpoint that accepts an enabled playbook and exactly one existing alert or incident target.
- [ ] 2.2 Reuse existing execution store and canonical outcome linkage, adding manual trigger metadata and audit logging.
- [ ] 2.3 Add a read-only `enrich_context` action to registry validation and executor handling.
- [ ] 2.4 Reuse or extract existing source-IP context, MITRE, correlation, and reputation helpers for enrichment output.
- [ ] 2.5 Add minimal UI launch affordances only for concrete alert or incident targets.
- [ ] 2.6 Add focused backend and frontend tests listed in the validation plan.

## Safety Boundaries

- [x] This authoring step changes only OpenSpec files under `openspec/changes/ad-hoc-trigger-and-enrichment/`.
- [x] No files under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/` are modified.
- [x] No implementation, commit, or push is performed.
