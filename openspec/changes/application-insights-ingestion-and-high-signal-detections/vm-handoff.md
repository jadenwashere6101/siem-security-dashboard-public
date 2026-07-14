# Application Insights Ingestion and High-Signal Detections VM Handoff

## Scope

- Mac-side source changes completed for backend, migration, tests, docs, and Azure Function source.
- No commit, push, VM sync, Azure deployment, production mutation, or secret change was performed.

## Requested / Deployed Commit

- Requested commit: not applicable yet; no commit was created.
- Deployed commit: none.

## Clean-Tree Preflight Result

- VM preflight not run on Mac by design.
- Azure Function deployment not run.

## Migrations / Backfills

- New additive migration: `migrations/0022_ingestion_checkpoints.sql`
- No existing table was modified by migration.
- No backfill required.

## Backend / Schema Verification Completed on Mac

- `python3 -m py_compile adapters/azure_insights_adapter.py core/ingestion_checkpoint_store.py core/source_health.py core/core_playbook_pack_v1.py core/ip_helpers.py engines/correlation_engine.py engines/detection_applicability.py engines/detection_config.py engines/detection_engine.py engines/ingest_engine.py engines/playbook_engine.py routes/ingest_routes.py tests/test_azure_application_insights_ingestion.py tests/test_ingestion_checkpoints.py tests/test_source_aware_detection.py tests/test_targeted_correlation.py tests/test_source_health.py tests/test_severity_response_matrix_api.py tests/test_core_playbook_pack_v1.py tests/test_schema_migrations.py`
- `python3 -m py_compile siem-azure-function/function_app.py`
- `python3 -m pytest tests/test_ingestion_checkpoints.py tests/test_azure_application_insights_ingestion.py tests/test_ingest_api_contracts.py tests/test_ingest_normalized_event.py tests/test_source_aware_detection.py tests/test_targeted_correlation.py tests/test_source_health.py tests/test_detection_applicability.py tests/test_core_playbook_pack_v1.py tests/test_severity_response_matrix_api.py tests/test_schema_migrations.py -q`
- `python3 -m pytest tests/test_admin_api_contracts.py tests/test_playbook_engine.py tests/test_ip_reputation.py tests/test_alerts_api_contracts.py -q`
- `python3 scripts/validate_schema_snapshot.py`
- `openspec validate application-insights-ingestion-and-high-signal-detections --strict`
- `git diff --check`

## Backend Deployment Tasks for VM AI

1. Run VM clean-tree preflight from `docs/mac-vm-source-of-truth-policy.md`.
2. After explicit authorization and approved commit/push exist, sync the VM to that commit.
3. Run migration dry-run and apply using the standard deployment helper.
4. Restart affected backend services only after migration succeeds.
5. Verify backend health and authenticated Source Health / Azure ingest checkpoint behavior.

## Azure Function Deployment Tasks

Separate from VM work. Requires explicit authorization.

1. Redeploy `siem-azure-function/function_app.py`.
2. Ensure app settings are present:
   - `SIEM_AZURE_INGEST_URL`
   - `AZURE_INGEST_API_KEY`
   - `LOG_ANALYTICS_WORKSPACE_ID`
   - `PAGE_SIZE`
   - `MAX_POLL_PAGES`
   - `QUERY_RETRY_ATTEMPTS`
   - `FORWARD_RETRY_ATTEMPTS`
   - `RETRY_BACKOFF_SECONDS`
   - `HTTP_TIMEOUT_SECONDS`
3. Verify timer logs show checkpoint-driven polling and successful checkpoint updates.

## Sanitized Runtime Evidence To Capture After Deployment

- Requested and deployed commit SHA
- VM clean-tree result
- Migration dry-run/apply result
- Backend service restart/status and `/health`
- `ingestion_checkpoints` row for `azure_insights`
- Recent `events` rows for `source = 'azure_insights'`
- Source Health response showing poll status fields
- Azure Function timer logs showing page counts / retry outcomes

## Explicit Non-Actions

- No VM access
- No deployment
- No production mutation
- No secret change
- No commit / push
