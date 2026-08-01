# Proposal: Anakin Async Workflow Execution

## Summary

Move the long-running canonical Anakin workflows out of synchronous browser-held requests and into durable queued execution with polling. Deep Investigate, Decision Support, and Generate Artifact will be queued through a new request API, executed by a backend worker, and rendered by the existing consolidated frontend after polling reaches a terminal result. Quick Explain remains synchronous. SOC Briefing and Repo Assistant remain outside this change.

## Motivation

Live production verification showed the deployed `/siem/` browser path can receive nginx 504 HTML at 60 seconds while Gunicorn/backend/Ollama later completes the same workflow. The frontend then parses a non-JSON timeout response into the generic `AI response unavailable.` fallback. Direct localhost backend success is therefore not proof of production UI success.

## Goals

- Add a durable job model for Deep Investigate, Decision Support, and Generate Artifact.
- Add fast queueing and polling APIs that use the canonical workflow envelope.
- Ensure long AI execution never runs inside the Gunicorn request.
- Add a worker with safe claiming, leases, bounded retries, stale recovery, timestamps, failure codes, and no production mutation.
- Preserve local-only model routing, RBAC, sanitization, bounded context/tool policy, no-paid-fallback behavior, audit logging, and strict artifact validation.
- Update consolidated frontend controls to queue and poll long-running workflows, preserve context, recover active requests when safe, prevent duplicates, and render specific errors.
- Keep Quick Explain synchronous.

## Non-Goals

- No nginx timeout increase as the primary fix.
- No SSE or WebSockets.
- No redesign of the six-workflow architecture.
- No SOC Briefing or Repo Assistant execution changes.
- No production runtime configuration changes, VM access, deployment, commit, push, or model installation.

## Production Completion Gate

This change follows `docs/anakin-production-acceptance-policy.md`. Automated tests and local verification are necessary but not sufficient for production readiness. Until deployed browser-path verification is performed through `/siem/`, completion wording must be:

```text
Implementation complete; production behavior unverified.
```
