## Why

Anakin currently exposes many action-specific AI entry points whose labels, backend branches, and expected outputs are inconsistent. This makes the assistant harder to trust, slower to evolve, and more likely to regress when new buttons or actions are added.

## What Changes

- Introduce one backend-owned AI workflow orchestration layer for all Anakin requests.
- Route every AI interaction through exactly one of six canonical workflows:
  - `quick_explain`
  - `deep_investigate`
  - `decision_support`
  - `generate_artifact`
  - `soc_briefing`
  - `repo_assistant`
- Support natural-language `workflow=auto` requests with auditable conservative classification.
- Preserve existing UI and legacy API routes during this phase through compatibility adapters.
- Keep separate workflow engines behind the orchestrator instead of replacing them with one large conditional service.
- Add explicit request, response, validation, failure, token-budget, profile, and lifecycle contracts for every workflow.
- Add polling-based lifecycle support for Deep Investigate with truthful backend stages only.
- Preserve existing local-only model profile routing, RBAC, bounded tool policy, sanitization, audit logging, no-paid-fallback behavior, and mutation gates.
- Keep Generate Artifact as the only structured draft workflow; preview/confirm remains separate and permission-gated.
- Do not redesign frontend buttons, change models, change production runtime configuration, deploy, or access the VM.

## Capabilities

### New Capabilities

- `anakin-core-workflows`: Canonical backend workflow orchestration, classification, compatibility adapters, workflow contracts, and Deep Investigate lifecycle for Anakin.

### Modified Capabilities

- None.

## Impact

- Backend: AI routes, workflow orchestration, explain/chat/draft/investigation compatibility adapters, profile inventory, acceptance harness contracts, and focused tests.
- Frontend: no redesign in this phase; existing calls must continue to work.
- Runtime: no model, environment, service, database, or deployment change.
- Database: no migration.
