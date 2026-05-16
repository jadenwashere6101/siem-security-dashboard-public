# OpenSpec Traceability Index

Lightweight traceability for selected high-value SOAR OpenSpec changes. This index is intentionally partial and does not attempt to retrofit the whole repository.

| Spec ID | Title | Spec path | Code files |
| --- | --- | --- | --- |
| SPEC-INTEG-001 | Circuit Breaker Simulation | `openspec/changes/archive/2026-05-11-add-soar-integration-circuit-breaker-simulation/` | `integrations/base_integration.py`, `integrations/integration_registry.py` |
| SPEC-INTEG-002 | Protected Target Policy | `openspec/changes/archive/2026-05-11-add-soar-protected-target-policy/` | `core/soar_protected_targets.py`, `engines/playbook_step_executor.py` |
| SPEC-INTEG-003 | Real Slack Readiness | `openspec/changes/add-soar-real-slack-readiness/` | `integrations/slack_adapter.py` |
| SPEC-INTEG-004 | Real Teams Readiness | `openspec/changes/add-soar-real-teams-readiness/` | `integrations/teams_adapter.py` |
| SPEC-PLAYBOOK-001 | Playbook Step Executor Simulation | `openspec/changes/archive/2026-05-11-add-soar-playbook-step-executor-simulation/` | `engines/playbook_step_executor.py`, `engines/playbook_registry.py` |
| SPEC-PLAYBOOK-002 | Playbook Approval Gates | `openspec/changes/archive/2026-05-11-add-soar-playbook-approval-gates/` | `engines/playbook_step_executor.py`, `core/approval_store.py` |
| SPEC-PLAYBOOK-003 | Execution Reliability Safeguards | `openspec/changes/archive/2026-05-11-add-soar-simulation-execution-reliability-safeguards/` | `engines/playbook_step_executor.py`, `core/playbook_store.py` |
| SPEC-NOTIFY-001 | Notification Delivery Tracking | `openspec/changes/add-soar-real-notification-delivery-tracking/` | `core/notification_delivery_store.py`, `engines/playbook_step_executor.py`, `routes/notification_delivery_routes.py`, `routes/metrics_routes.py`, `frontend/src/components/PlaybooksPanel.js`, `frontend/src/components/PlaybookMetricsPanel.js` |
| SPEC-INGEST-001 | Ingest Transaction + Detection/Correlation Contract | `openspec/changes/archive/web-log-ingestion-phase2/`<br>`openspec/changes/archive/ingestion-normalization-phase1a/`<br>`openspec/changes/archive/ingestion-normalization-phase1b/`<br>`openspec/changes/archive/targeted-correlation-rules-phase1/`<br>`openspec/changes/archive/success-after-spray-detection/` | `routes/ingest_routes.py`, `engines/ingest_engine.py`, `engines/detection_engine.py`, `engines/correlation_engine.py`, `helpers/ingest_normalizers.py` |
| SPEC-AUTH-001 | RBAC + Session Identity Contract | `openspec/changes/archive/role-based-access-control/`<br>`openspec/changes/archive/rbac-viewer-support/`<br>`openspec/changes/archive/session-identity-clarity/`<br>`openspec/changes/archive/audit-logging-v1/` | `core/auth.py`, `core/audit_helpers.py`, `routes/auth_routes.py`, `routes/admin_routes.py` |
| SPEC-NORM-001 | Telemetry Normalization Contract | `openspec/changes/archive/azure-ingestion-hardening-phase1/`<br>`openspec/changes/archive/azure-plug-and-play-phase2/`<br>`openspec/changes/archive/opentelemetry-ingestion-phase4/`<br>`openspec/changes/archive/web-log-detection-phase2-5/` | `helpers/ingest_normalizers.py`, `routes/ingest_routes.py`, `adapters/azure_insights_adapter.py`, `adapters/otel_adapter.py`, `adapters/nginx_adapter.py`, `engines/ingest_engine.py` |
| SPEC-SCHEMA-001 | Schema Migration Versioning | `openspec/changes/add-schema-migration-versioning/` | `schema.sql`, `migrations/` (to be created), `scripts/migrate.py` (to be created) |
