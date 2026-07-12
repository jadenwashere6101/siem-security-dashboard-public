## Why

Analysts and detection engineers currently have no safe way to test how a pasted log line or JSON event would move through the real SIEM pipeline — parsing, normalization, detection thresholds, alert generation, MITRE mapping, and SOAR/playbook selection — without sending it through the live `/ingest` path and creating real events, alerts, incidents, playbook executions, and queued response actions. This blocks detection tuning, analyst training, and pre-production validation of rule behavior, and it discourages experimentation because any test event pollutes production data and can trigger real downstream actions (Slack/Teams/email/webhook/firewall) once picked up by the SOAR/playbook workers. A completed architecture audit of this repository (see prior conversation) confirmed the production pipeline's engine layer (`engines/*.py`, `core/*.py`) contains zero `commit`/`rollback` calls — all commits live in the route layer (`routes/ingest_routes.py`) — which makes a transaction-rollback-based simulator both feasible and low-risk to build without forking or duplicating detection logic.

## What Changes

- Add a new authenticated simulation endpoint that runs pasted events through the real production pipeline (parser → normalizer → detection applicability → detection evaluation/threshold-window logic → alert generation → MITRE mapping → SOAR/playbook preview) inside a single database transaction that is **always rolled back**, guaranteeing zero durable writes.
- Reuse existing production code paths verbatim for every pipeline stage: source adapters/parsers, `engines/ingest_engine.ingest_normalized_event`, the detection-engine and correlation-engine detector functions, `engines/detection_applicability.py`, `engines/detection_config.py`, `helpers/enrichment_helpers.py` MITRE mapping, `engines/playbook_engine.match_playbooks`, and `core/ip_helpers.determine_response_action`. No parallel/forked evaluation logic is introduced for existing rules.
- Version 1 supports existing production SIEM detection rules only. Custom rule authoring, Python rule execution, and SQL rule execution are explicitly out of scope and documented as future roadmap items only.
- Add a new "Detection Simulator" sidebar workspace (frontend) with a source selector, raw log/JSON paste input, production rule selector, a pipeline-stage visualization (Raw Input → Parser → Normalized Event → Detection Applicability → Detection Evaluation → Threshold/Window Evaluation → Alert Preview → MITRE Mapping → SOAR Preview), and explainability output describing why a detection did or did not fire.
- Add narrowly-scoped, additive instrumentation to expose near-miss/failed-condition detail (e.g., "3 of 5 required attempts") in simulation responses, without changing production alerting behavior on the real `/ingest` path.

## Capabilities

### New Capabilities
- `detection-simulator-workspace`: end-to-end dry-run simulation of the production detection/SOAR pipeline for analyst-pasted events, covering the backend simulation endpoint, transaction-rollback safety guarantees, and the frontend workspace and pipeline visualization.

### Modified Capabilities
- None. This change reuses existing engine/core functions as read-only callers inside a rollback-only transaction and adds new, additive return fields to expose near-miss reasoning; it does not change any existing spec's documented behavior on the production `/ingest` path.

## Impact

- **New backend code**: a new route module/blueprint for the simulation endpoint; a new orchestration function mirroring the existing ingest route's call sequence but with commits replaced by a guaranteed rollback.
- **Touched but unmodified**: `adapters/*.py`, `engines/ingest_engine.py`, `engines/detection_engine.py`, `engines/correlation_engine.py`, `engines/detection_applicability.py`, `engines/detection_config.py`, `engines/playbook_engine.py`, `core/ip_helpers.py`, `helpers/enrichment_helpers.py` — called, not changed, except for the additive near-miss instrumentation noted above.
- **New frontend code**: a new sidebar workspace, following the existing sidebar-workspace pattern (see `add-source-health-workspace`, `build-sidebar-shell-components`).
- **Out of scope / explicitly excluded**: custom/temporary rule builder, Python rule authoring/execution, SQL rule authoring/execution, persistent user-created rules, rule editor, rule versioning — documented as future roadmap only.
- **No production data impact**: no new tables, no schema changes, no changes to production alerting/response behavior.
