# Agent Instructions

## Required Reading

Read and follow [docs/mac-vm-source-of-truth-policy.md](docs/mac-vm-source-of-truth-policy.md) before any source, deployment, database, service, or VM work. It is the single source of truth for Mac/VM locations, ownership, workflow, and deployment rules — update it directly if a rule changes, rather than restating rules elsewhere, except for the intentional protective duplicate below.

## Top-Level Safeguard (intentional duplication)

- Do not commit, push, deploy, or mutate production unless explicitly requested.

## Engineering Gates

- Preserve unrelated dirty-worktree changes.
- Trace UI action -> frontend service -> API -> backend -> database/queue/worker/external effect -> resulting UI state.
- Preserve RBAC, audit logging, idempotency, protected-target checks, fail-closed integration guards, secrets, and intentionally simulated behavior.
- Distinguish requested actions from actual outcomes: real, simulation, tracking-only, read-only, pending, blocked, failed, or unknown.
- UI changes require focused tests, production build, dark-theme/accessibility review, and visual verification when practical.
- Backend/schema changes require focused regression tests, migration/schema validation, and a VM handoff.
- Run `git diff --check` and OpenSpec strict validation (`openspec validate <change> --strict`) before handoff.
