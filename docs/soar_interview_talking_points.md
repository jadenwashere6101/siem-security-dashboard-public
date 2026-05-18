# SOAR Interview Talking Points

Last updated: 2026-05-18

Use this as the concise narrative for portfolio reviews and interviews.

## What I Built

I built a SIEM/SOAR security operations platform that ingests security events,
creates alerts and incidents, runs simulation-safe response playbooks, tracks
worker execution, handles approvals and failures, and exposes operational views
for analysts and administrators.

The product is designed to feel like a real SOC console: SOC Command Center for
triage, Playbooks for execution traceability, SOAR Operations for failures and
recovery, SOAR Metrics for health, and guarded Integrations for controlled
outbound execution.

## Best Demo Narrative

1. Start in SOC Command Center to show operational pressure and safety state.
2. Open a specific incident or playbook execution.
3. Show the execution timeline and explain each step state.
4. Show SOAR Operations to explain dead letters and retryability.
5. Show SOAR Metrics to prove worker/queue observability.
6. Close with integration safety: simulation default, four real-mode guards,
   audit redaction, rate limiting, deduplication, and firewall dry-run boundary.

## Engineering Decisions

- Kept detection/correlation separate from SOAR execution so response automation
  does not destabilize alert generation.
- Moved playbook execution into a daemonized worker path to avoid long-running
  request handlers.
- Added lease ownership and stale recovery so interrupted workers can recover
  safely.
- Added dead letters because failed automations need durable investigation
  records, not lost exceptions.
- Added retryability classification so analysts only see actionable retry
  states.
- Designed integrations as simulation-first with real-mode guardrails because
  uncontrolled security automation is risky.
- Added audit redaction, rate limiting, and idempotency to make outbound
  integrations safer to operate and demo.

## Worker Orchestration Explanation

The worker claims queued playbook executions with a lease, processes bounded
batches, records step outcomes, and refreshes operational status through metrics.
If work gets stuck in a running state, stale recovery can move eligible rows into
the right recovery path without touching approval-paused executions.

## Simulation vs Real Execution

Simulation mode is the default and is what a normal demo should use. Real mode
is available only for approved adapters and only when the full guard model is
satisfied. Missing guards fail closed. Firewall remediation remains dry-run only.

## Security/Safety Framing

The project treats automation as a safety problem, not just an integration
problem. The controls include role-aware UI, approvals, real-mode guard checks,
audit redaction, adapter rate limits, idempotency checks, dead-letter
retryability, and explicit runbooks for any controlled staging smoke test.

## Resume Bullet Drafts

- Built a full-stack SIEM/SOAR platform with React, Flask, PostgreSQL, RBAC,
  alert triage, incident workflows, playbook automation, and operational
  dashboards.
- Implemented daemonized SOAR playbook execution with lease ownership, stale
  recovery, dead-letter handling, retry workflows, approvals, and worker health
  metrics.
- Designed simulation-safe real integration architecture with guarded Slack,
  Teams, email, webhook, and firewall dry-run boundaries, including audit
  redaction, rate limiting, and delivery deduplication.
- Built SOC Command Center, SOAR Metrics, SOAR Operations, and execution
  timeline UI surfaces to make automation state explainable during security
  investigations.
- Added productization runbooks, demo guidance, and validation checklists to
  make the platform safe to present and operate.

