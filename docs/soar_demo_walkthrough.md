# SOAR Demo Walkthrough

Last updated: 2026-05-18

This guide is the safe click-through path for demoing the SIEM/SOAR platform in
portfolio reviews, interviews, and local validation sessions.

## Demo Safety Defaults

- Keep the demo in simulation mode unless a separate staging smoke-test runbook
  is being followed.
- Do not enable real outbound adapters during a general demo.
- Do not paste webhook URLs, tokens, SMTP passwords, API keys, or raw customer
  payloads into the browser or terminal.
- Do not run VM commands during a local demo unless that deployment action was
  explicitly requested and approved.
- Stop the demo if the UI or logs suggest an unexpected outbound Slack, Teams,
  email, webhook, or firewall action.

## Startup Flow

1. Confirm the working tree state before the demo:

   ```bash
   git status --short
   ```

2. Start the backend using the normal local development process for this repo.
   Keep integration env vars simulation-safe. The default demo posture is no
   real adapter execution.

3. Start the frontend:

   ```bash
   cd frontend
   npm start
   ```

4. Optional validation before presenting:

   ```bash
   cd frontend
   CI=true npm test -- --runInBand App
   npm run build
   ```

5. If a worker is needed for the scenario, use
   [SOAR Playbook Worker Daemon Runbook](soar_playbook_worker_daemon_runbook.md)
   as the operator reference. For a portfolio demo, keep worker/integration
   settings simulation-safe.

## Click-Through Order

1. **Dashboard**
   - Show the SIEM foundation: alerts, incidents, map, reports, and analyst
     workflow entry points.
   - Explain that SOAR starts after alerts/incidents exist; detection and
     correlation remain separate from response execution.

2. **SOC Command Center**
   - Show high-level SOC pressure, active automation pressure, pending
     approvals, dead-letter pressure, notification health, worker health, and
     integration safety status.
   - Use this as the first executive-level screen in interviews.
   - Expected state: cards load independently, partial API failures render soft
     warnings, and simulation/real-mode status is labeled clearly.

3. **SOAR Playbooks**
   - Show playbook definitions and execution history.
   - Open an execution detail and point to the read-only execution timeline.
   - Expected state: steps render in sequence with success, failure, skipped,
     approval, retry, recovery, and simulation/real indicators when data exists.

4. **SOAR Operations**
   - Show dead letters, retryability state, failed execution context, and safe
     operational recovery visibility.
   - Expected state: retry/abandon controls remain role-aware and are only the
     existing safe actions already implemented by the platform.

5. **SOAR Metrics**
   - Show worker, queue, execution, retry, stale recovery, and notification
     metrics.
   - Expected state: metrics explain system health without implying real
     remediation is active.

6. **SOAR Integrations**
   - Show adapter status and guard decisions.
   - Explain the four-guard model: real integration mode, approved SOAR
     environment, adapter-specific enable flag, and required credentials.
   - Expected state: simulation is the safe default; missing guards fail closed.

7. **Approvals / Incident Detail**
   - Show how human gates pause risky workflows and keep analysts in control.
   - Expected state: approval context is visible without introducing new
     mutation behavior in demo polish.

## Expected Dashboard States

- SOC Command Center: compact cards, timeline feed, attention panel, incident
  workspace, integration safety badge.
- Playbooks: execution list plus visual read-only timeline.
- SOAR Operations: dead-letter pressure, retryable vs non-retryable failures,
  duplicate-safe operational behavior.
- SOAR Metrics: queue health, worker health, execution outcomes, notification
  health.
- Integrations: adapters are registered, guarded, rate-limited, audited, and
  redacted; firewall remains simulation/dry-run only.

## Interview Story

Start with the SOC Command Center because it explains the product at a glance.
Then drill into one playbook execution timeline to prove operational traceability.
Close with the integration safety model to show engineering judgment around
real-world automation risk.

## Screenshot Evidence Checklist

- SOC Command Center overview with safety badge visible.
- Execution timeline showing at least one completed or failed playbook.
- SOAR Operations dead-letter or retryability view.
- SOAR Metrics worker and queue health view.
- Integration status showing simulation-safe or guarded real-mode state.
- Redaction review complete: no secrets, webhook URLs, auth headers, SMTP
  passwords, raw payloads, or private infrastructure values visible.

