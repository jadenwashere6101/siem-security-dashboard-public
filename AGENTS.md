# Agent Instructions

## Required Reading

Read and follow [docs/mac-vm-source-of-truth-policy.md](docs/mac-vm-source-of-truth-policy.md) before any source, deployment, database, service, or VM work. It is the single source of truth for Mac/VM locations, ownership, workflow, and deployment rules — update it directly if a rule changes, rather than restating rules elsewhere, except for the intentional protective duplicate below.

This project has a long history. You may observe some inconsistencies in coding style.
When making changes, use best practices as described
and try to improve the code style where possible and where relevant to the current task.
Do not attempt to fix too much at once, or when it is not related to the current changes

## Top-Level Safeguard (intentional duplication)

- Do not commit, push, deploy, or mutate production unless explicitly requested.
- Production backend deployments must use the documented Gunicorn/systemd path; never run Flask's development server for production.
- Production Flask-Limiter storage must remain shared and production-safe under Gunicorn; do not regress to in-memory limiter storage for production.

## Engineering Gates

- Preserve unrelated dirty-worktree changes.
- Trace UI action -> frontend service -> API -> backend -> database/queue/worker/external effect -> resulting UI state.
- Preserve RBAC, audit logging, idempotency, protected-target checks, fail-closed integration guards, secrets, and intentionally simulated behavior.
- Distinguish requested actions from actual outcomes: real, simulation, tracking-only, read-only, pending, blocked, failed, or unknown.
- UI changes require focused tests, production build, dark-theme/accessibility review, and visual verification when practical.
- Backend/schema changes require focused regression tests, migration/schema validation, and a VM handoff.
- Run `git diff --check` and OpenSpec strict validation (`openspec validate <change> --strict`) before handoff.

- UI/UX changes must optimize for analyst-visible outcomes, not just implementation correctness. Before considering a UI task complete, verify that:
  - the requested improvement is immediately noticeable in normal use;
  - the workflow feels simpler, clearer, or faster for the analyst;
  - hidden state or subtle copy-only changes are not the primary solution when a visible workflow improvement was requested;
  - if the requested change cannot be clearly perceived in the live UI, continue iterating rather than considering the task complete.
  - For UI changes, do not rely solely on source code, tests, or API verification. Perform a visual review whenever practical and ask: "Would a human immediately notice and understand the requested improvement?"
  - Do not satisfy a UX request by making only backend or hidden-state changes. If the user requested a workflow improvement, confirm the visible UI actually reflects that improvement.
