## 1. Audit

- [x] 1.1 Audit SOC Command Center copy, integration safety labels, activity/status cards, and tests.
- [x] 1.2 Audit `IntegrationStatusPanel` and integration status data assumptions.
- [x] 1.3 Audit Playbook execution detail/timeline simulation/real labels.
- [x] 1.4 Audit SOAR Metrics and SOAR Operations wording that may imply the whole platform is simulated.
- [x] 1.5 Audit candidate Python and frontend files for existing `# spec:` / `// spec:` comments to avoid duplicate/noisy tagging.

## 2. Execution Safety Model UI

- [x] 2.1 Add a compact read-only execution safety model panel/helper component if reuse is justified.
- [x] 2.2 Add or place the panel in SOC Command Center.
- [x] 2.3 Add or place compact safety-model context in the integration status area.
- [x] 2.4 Add or place compact safety-model context in Playbook execution detail/timeline if it fits without clutter.
- [x] 2.5 Ensure wording says orchestration/workflows are real, integrations are guard-controlled, simulation-safe execution is default, some adapters are real-capable, approvals/rate limits/dead letters are real, and firewall is dry-run only.
- [x] 2.6 Remove or revise broad wording that implies the full platform is fake or controlled by one global simulation/real toggle.

## 3. Capability Matrix

- [x] 3.1 Add a concise read-only capability matrix/card.
- [x] 3.2 Include alert ingestion as real.
- [x] 3.3 Include orchestration/workflows as real.
- [x] 3.4 Include approvals as real.
- [x] 3.5 Include Slack/Teams/email/webhook as guarded real-capable.
- [x] 3.6 Include firewall as simulation-safe/dry-run only.
- [x] 3.7 Keep the matrix compact and operational, with loading/empty-safe rendering.

## 4. Traceability Tagging

- [x] 4.1 Add concise traceability comments to `integrations/base_integration.py` near the real-mode guard model.
- [x] 4.2 Add concise traceability comments to Slack, Teams, email, webhook, and firewall adapters near real-capable or dry-run boundaries.
- [x] 4.3 Add concise traceability comments to `integrations/adapter_rate_limiter.py`.
- [x] 4.4 Add concise traceability comments to `core/integration_audit.py`.
- [x] 4.5 Add concise traceability comments to `core/dead_letter_store.py`.
- [x] 4.6 Add concise traceability comments to `engines/playbook_step_executor.py`.
- [x] 4.7 Add concise traceability comments to the active worker/orchestration file, using `engines/soar_playbook_worker.py` if present or the current daemon/worker module otherwise.
- [x] 4.8 Add concise traceability comments to `routes/metrics_routes.py`.
- [x] 4.9 Add concise traceability comments to touched frontend safety-model surfaces.
- [x] 4.10 Confirm comments are not spammy and do not tag unrelated low-value files.

## 5. Tests

- [x] 5.1 Add/update SOC Command Center tests for safety model panel and capability matrix.
- [x] 5.2 Add/update IntegrationStatusPanel tests for guard-controlled and dry-run language.
- [x] 5.3 Add/update PlaybookExecutionTimeline or PlaybooksPanel tests if execution-detail wording changes.
- [x] 5.4 Add/update SOAR Metrics / SOAR Operations tests only if wording changes affect assertions.
- [x] 5.5 Add a test/assertion that confusing "fake mode" wording is not rendered in the new panel.
- [x] 5.6 Confirm no tests trigger real integrations or new mutation behavior.

## 6. Verification

- [x] 6.1 Run focused frontend tests for touched components.
- [x] 6.2 Run `npm run build` from `frontend/`.
- [x] 6.3 Run `python3 -m py_compile` for touched Python files if traceability comments are added there.
- [x] 6.4 Run `git diff --check`.
- [x] 6.5 Run `git status --short`.
- [x] 6.6 Confirm no backend execution semantics, schema/migrations, integrations, VM/runtime actions, env vars, or mutation controls changed.
