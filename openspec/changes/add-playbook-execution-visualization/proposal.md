## Why

The SOAR platform now records rich playbook execution state through execution rows, `steps_log`, approvals, dead letters, notification delivery attempts, retry/recovery metadata, and worker lease fields. Operators can inspect this data across existing panels, but playbook execution review is still text-heavy and fragmented. A polished Playbook Visualization + Execution Timeline will make each run easier to understand, troubleshoot, and explain without changing execution behavior.

## What Changes

- Add a visual, read-only playbook execution timeline that renders step-by-step state from existing execution detail data.
- Show pending, running, success, failed, skipped, and awaiting-approval states with timestamps, durations, retry attempts, and safe failure messages when available.
- Add a compact execution flow visualization with node-style step representation, current-step highlighting, terminal-state highlighting, approval pause markers, and recovery/lease indicators when present.
- Integrate the full visualization into `PlaybooksPanel` execution detail while preserving existing playbook list, execution list, and control behavior.
- Optionally expose a compact execution timeline/summary in SOC Command Center when existing execution data is already present.
- Clearly label simulation vs real-mode execution context and avoid showing raw payloads, credentials, webhook URLs, auth headers, or provider responses.
- Keep implementation frontend-first and read-only: no schema changes, no backend execution changes, no real integrations, and no new mutation controls.

## Capabilities

### New Capabilities
- `playbook-execution-visualization`: A frontend visualization surface for playbook execution flow and timeline, using existing execution, step log, approval, recovery, and delivery metadata.

### Modified Capabilities
- `soc-command-center-ui`: May show a compact execution timeline/summary when feasible from already-loaded execution data.

## Impact

- Frontend React code: likely `frontend/src/components/PlaybookExecutionTimeline.js`, `frontend/src/components/PlaybooksPanel.js`, optional compact reuse in `frontend/src/components/SocCommandCenter.js`, and focused tests.
- Existing frontend services expected to be reused: `playbookService.getPlaybookExecution()`, `playbookService.listPlaybookExecutions()`, notification delivery service helpers, approval service data where already linked, and dead-letter data where existing detail responses expose it.
- Backend/API impact should be none unless implementation discovers a tiny read-only field gap that blocks safe visualization.
- No database schema/migration changes, no new execution semantics, no VM/runtime actions, no new mutation buttons, and no real outbound integrations.
