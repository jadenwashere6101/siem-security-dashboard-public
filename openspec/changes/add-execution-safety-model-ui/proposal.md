## Why

The SIEM/SOAR platform is now operationally mature, but some UI wording can
still make the system sound globally simulated or "fake." That is not accurate:
ingestion, orchestration, approvals, worker execution, dead letters, metrics,
audit logging, rate limiting, and deduplication are real platform behavior.
Outbound integrations are guard-controlled, with some adapters real-capable and
firewall intentionally dry-run only.

The project also needs a focused traceability pass on the highest-value
orchestration and safety files so future contributors can quickly identify
which specs own key safety boundaries.

## What Changes

- Add a compact read-only execution safety model explanation in high-value UI
  surfaces, preferably SOC Command Center, SOAR Integrations, and Playbook
  execution detail.
- Add a concise capability matrix that distinguishes real platform operations,
  guarded real-capable adapters, simulation-safe defaults, approval gates, and
  firewall dry-run behavior.
- Replace broad wording that implies a single global simulation/real toggle with
  operational labels such as "Simulation-Safe Execution," "Guarded Real
  Integration," "Real Integration Disabled," "Dry-Run Active,"
  "Approval-Gated," and "Real-Capable Adapter."
- Add lightweight `SPEC-*` traceability comments to selected orchestration,
  integration-safety, metrics, dead-letter, worker, and UI files.
- Keep all changes informational: no backend execution changes, schema changes,
  new integrations, runtime changes, VM actions, or new mutation controls.

## Capabilities

### New Capabilities

- `execution-safety-model-ui`: A compact UI explanation and capability matrix
  that clarifies real orchestration vs guard-controlled integrations.
- `soar-traceability-tags`: Concise spec ownership comments on selected
  high-value SOAR orchestration and safety files.

### Modified Capabilities

- `soc-command-center-ui`: May show the compact safety model panel and matrix.
- `playbook-execution-visualization`: May include a compact safety explanation
  near execution detail.
- `soar-integration-status`: May clarify adapter capability/status labels and
  avoid broad binary real/simulation language.

## Impact

- Frontend React code: likely `frontend/src/components/SocCommandCenter.js`,
  `frontend/src/components/IntegrationStatusPanel.js`,
  `frontend/src/components/PlaybookExecutionTimeline.js`,
  `frontend/src/components/SoarMetricsDashboard.js`,
  `frontend/src/components/DeadLettersPanel.js`, and focused tests.
- Backend/source comments only: likely `integrations/base_integration.py`,
  `integrations/*_adapter.py`, `integrations/adapter_rate_limiter.py`,
  `core/integration_audit.py`, `core/dead_letter_store.py`,
  `engines/playbook_step_executor.py`, `engines/soar_playbook_worker.py`, and
  `routes/metrics_routes.py`.
- No behavior changes, no schema/migration changes, no real outbound calls, no
  VM/runtime actions, and no new execution controls.

