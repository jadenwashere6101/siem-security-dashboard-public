## Why

Interactive SOC-facing Anakin actions passed static profile-routing tests but failed real analyst use: SOC Command Center actions overflowed prompt limits, alert-detail responses were treated as stale after normal refreshes, and several successful answers repeated visible fields instead of adding analytical value. This change makes the in-scope Anakin buttons bounded, context-specific, profile-aware, and useful before the feature is presented again.

## What Changes

- Bound context for dashboard, alert, source-IP, incident, recon, response-registry, command-palette, floating-chat, and analyst-workspace AI requests before prompt serialization.
- Stop injecting full visible dashboard context into entity-specific AI actions.
- Apply the selected semantic profile's prompt limit consistently across service-level and provider-level checks.
- Return context metadata describing included evidence, omitted evidence, and truncation state.
- Reassign correlation-heavy quick actions from `fast_triage` to `guided_analysis` while preserving `deep_briefing` and `developer_assistant` boundaries.
- Rewrite task-specific prompts so responses assess, correlate, identify uncertainty, and recommend concrete read-only next steps instead of restating visible fields.
- Relax stale handling for read-only explanations so background refreshes produce an advisory rather than hiding or blocking useful responses.
- Preserve strict stale blocking for confirmable or mutating previews.
- Add end-to-end contract tests covering the in-scope AI action inventory from frontend payload through backend context/profile/prompt behavior.

Out of scope: manual/scheduled SOC briefing lifecycle, Repo Architecture Assistant citation contract, new providers/models, paid fallback, production actions, VM/runtime configuration, deployments, commits, and model installation.

## Capabilities

### New Capabilities
- `anakin-context-and-response-quality`: Bounded, profile-appropriate, useful interactive SOC-facing Anakin responses with advisory stale handling for read-only outputs.

### Modified Capabilities

## Impact

- Backend AI services: context builders, explain/chat/draft/investigation prompt construction, profile selection helpers, and response metadata.
- Frontend AI workflow: `handleAskAi`, AI response stale handling, and affected button/component tests.
- Tests: AI inventory/profile/context contract tests, oversized fixture tests, stale UX tests, and frontend production build.
- No database migration, production runtime configuration, provider change, paid fallback, VM access, or deployment.
