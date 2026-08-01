# Anakin Production Acceptance Policy

This policy is the mandatory production completion gate for all Anakin changes. It applies to backend, frontend, prompt, workflow, model-profile, worker, SOC briefing, Repo Assistant, and acceptance-harness changes that affect Anakin behavior.

## Anakin Production Completion Gate

An Anakin change is NOT complete merely because:

- unit tests pass;
- integration tests pass;
- OpenSpec validates;
- the frontend builds;
- the backend route returns 200 directly on localhost;
- services are healthy;
- an acceptance harness passes offline.

Completion requires verification through the exact deployed user path:

```text
browser -> /siem/ -> nginx -> frontend -> backend -> worker/Ollama -> frontend-rendered result
```

For every affected canonical workflow, verify:

- Quick Explain
- Deep Investigate
- Decision Support
- Generate Artifact
- SOC Briefing
- Repo Assistant

Only workflows affected by a narrow change must be rerun, but every affected workflow must be verified end to end.

## Required Checks

1. Test through the nginx `/siem/` path, not only against `127.0.0.1`.
2. Capture both:
   - live API result;
   - actual frontend/UI result.
3. Confirm the full timeout chain is compatible:
   - nginx timeout;
   - backend/Gunicorn request behavior;
   - AI profile/provider timeout;
   - worker/runtime limit;
   - polling interval and terminal-state handling.
4. For asynchronous workflows, verify a real lifecycle:
   - queued;
   - running;
   - completed/partial/degraded/failed;
   - frontend update/history refresh.
5. Confirm the correct assistant/data source handled the request.
6. Confirm safe workflows do not persist, apply, or mutate anything unless the test explicitly authorizes it.
7. One successful retry does not prove reliability if the first equivalent attempt failed.

## Failure Conditions

A workflow may not be reported as working when:

- the UI shows a fallback or generic unavailable message;
- nginx times out before the backend finishes;
- the backend succeeds but the frontend cannot parse/render the envelope;
- a job queues but does not produce a usable terminal result;
- the wrong specialized assistant answers the question;
- only mocked/offline fixtures were tested;
- live browser-path verification was skipped.

## Required Final Report Fields

Every Anakin production-verification report must include:

- Workflow
- Browser-path result
- Live API result
- Latency
- UI-rendered result
- Pass/Fail
- Exact root cause for failures
- Production mutation performed: Yes/No
- Remaining unverified behavior

Required final totals:

- Passed
- Failed
- Unverified

A change may be called production-ready only when:

- Failed = 0
- Unverified = 0

If browser-path verification was not performed, the report must explicitly say:

```text
Implementation complete; production behavior unverified.
```

It may not say:

- working;
- done;
- fully verified;
- production-ready.

## Process Ownership

- Mac AI owns specs, source changes, and automated tests.
- VM AI owns runtime deployment and service/database verification.
- Final completion requires a deployed acceptance handoff through nginx and the UI.
- Direct backend success is never sufficient proof of frontend success.

## Reusable OpenSpec Completion-Gate Block

Paste this block into future Anakin OpenSpec implementation prompts:

```text
Anakin production completion gate:

Before reporting this Anakin change as working, done, fully verified, or production-ready, follow docs/anakin-production-acceptance-policy.md.

Automated tests, OpenSpec validation, frontend build success, service health, direct-backend localhost 200s, and offline acceptance harness success are necessary but not sufficient.

For every affected canonical workflow, verify the deployed browser path:
browser -> /siem/ -> nginx -> frontend -> backend -> worker/Ollama -> frontend-rendered result.

Capture Workflow, Browser-path result, Live API result, Latency, UI-rendered result, Pass/Fail, exact failure root cause, Production mutation performed: Yes/No, and remaining unverified behavior.

Confirm timeout compatibility across nginx, Gunicorn/backend, AI profile/provider, worker/runtime, polling, and terminal-state handling. Confirm the correct assistant/data source handled the request. Confirm safe workflows do not persist, apply, or mutate anything unless explicitly authorized.

Final totals must include Passed, Failed, and Unverified. Only report production-ready when Failed = 0 and Unverified = 0.

If browser-path verification was not performed, say exactly:
Implementation complete; production behavior unverified.
Do not say working, done, fully verified, or production-ready.
```
