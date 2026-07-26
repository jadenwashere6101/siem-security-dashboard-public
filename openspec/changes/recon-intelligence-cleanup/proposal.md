## Why

The SOC Command Center currently shows only a small, bounded slice of distributed recon activity and can label weak one-alert clusters as campaign-linked reconnaissance. Analysts need complete recon history access and higher-confidence recon intelligence without turning the command center into an investigative data dump.

## What Changes

- Add a dedicated Recon workspace/history flow for browsing complete distributed recon activity with pagination, filters, search, and investigation pivots.
- Keep the SOC Command Center recon section as an operational summary of the highest-priority recent recon, with a clear path to the full Recon workspace.
- Replace boolean campaign labeling with an evidence-gated recon intelligence model that distinguishes weak recon clusters from campaign-grade recon.
- Introduce confidence levels and evidence thresholds based on linked alert count, source diversity, duration, incident correlation, target/service consistency, progression, and alert-type diversity.
- Suppress or downgrade weak one-alert/one-source/short-duration clusters from campaign presentation while preserving their underlying alerts and activity records.
- Add paginated linked-alert browsing for recon detail so analysts can inspect complete activity without oversized payloads.
- Preserve existing ingest, detection, alerting, SOAR, notification, AI, and alert workflows.
- Avoid schema changes unless implementation proves the current `summary` and `membership_evidence` JSONB fields cannot safely hold the new intelligence projection.

## Capabilities

### New Capabilities

- `recon-intelligence-workspace`: Covers full recon history browsing, recon detail investigation, evidence-gated recon intelligence, and command-center recon summary behavior.

### Modified Capabilities

- None.

## Impact

- Backend: `core/recon_activity_store.py`, recon routes in `routes/alerts_events_routes.py`, recon-related notification/read models if projection labels change.
- Frontend: `frontend/src/components/SocCommandCenter.js`, `frontend/src/services/reconActivityService.js`, new or extracted Recon workspace components, navigation/section config if a new workspace section is added.
- Tests: backend API contract tests for recon list/detail/linked-alert pagination and frontend tests for command-center summary plus full history workflow.
- Documentation: OpenSpec artifacts for this change; implementation handoff should mention VM sync/runtime visual verification because backend and frontend source will change.
