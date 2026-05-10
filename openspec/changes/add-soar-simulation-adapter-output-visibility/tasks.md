# Tasks: SOAR Simulation Adapter Output Visibility

## Implementation steps
- [ ] Inspect the current `PlaybooksPanel` timeline rendering and existing helper patterns.
- [ ] Add a small local helper to detect and normalize `step.output.adapter_result`.
- [ ] Render a read-only adapter simulation section for steps with adapter output.
- [ ] Show adapter name, action, success or failure, message, `simulated`, `executed`, and metadata when present.
- [ ] Preserve existing timeline rendering for steps without adapter output.
- [ ] Keep raw JSON as a secondary read-only fallback only if consistent with the existing panel.
- [ ] Add focused tests in `frontend/src/components/PlaybooksPanel.test.js`.
- [ ] Confirm no backend, schema, executor, service, ingest, detection, correlation, SOAR queue, or approval decision files changed.

## Exact frontend test requirements
- [ ] Test adapter-backed timeline output for `notify_slack`.
- [ ] Test adapter-backed timeline output for `block_ip` and verify the UI labels it as simulated.
- [ ] Test metadata display for `adapter_result.metadata`.
- [ ] Test that steps without `adapter_result` still render using existing behavior.
- [ ] Test that this change does not add run, retry, cancel, approve, deny, or resume controls.

## Verification commands
Run from the repository root:

```bash
cd frontend
CI=true npm test -- --watchAll=false --runTestsByPath src/components/PlaybooksPanel.test.js
CI=true npm test -- --watchAll=false
npm run build
```

Then run from the repository root:

```bash
git status --short
```

## Stop and rollback conditions
- Stop if backend response shape changes are required.
- Stop if executor or adapter behavior changes are required.
- Stop if schema changes are required.
- Stop if implementation would add mutation controls or new API calls.
- Stop if implementation touches ingest, detection, correlation, SOAR queue, approval decision behavior, or real integration code.
- Roll back the UI/test edits if they broaden beyond read-only adapter output visibility.
