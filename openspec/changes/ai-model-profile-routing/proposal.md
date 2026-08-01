## Why

The AI Gateway currently uses one local model and one timeout for every AI-powered feature. That makes quick dashboard explanations too slow when routed to an 8B model, while deeper investigations and SOC briefings need longer bounded runtime. Some AI buttons also fail before reaching the model because frontend action/context identifiers are not fully accepted by backend allowlists and context builders.

## What Changes

- Add a centralized backend AI model profile registry and machine-readable AI invocation inventory.
- Route every AI generator path through an approved semantic profile:
  - `fast_triage` for short dashboard, alert, source/IP, recon, response, and general chat explanations.
  - `guided_analysis` for guided investigations and review-only drafts.
  - `deep_briefing` for manual and scheduled SOC briefing synthesis.
  - `developer_assistant` for repo architecture/source-code assistance.
- Add profile-specific model, timeout, prompt budget, output budget, and temperature configuration with safe local-only/no-paid-fallback defaults.
- Preserve compatibility with existing `AI_LOCAL_MODEL` and `AI_LOCAL_TIMEOUT_SECONDS` for guided/deep/developer rollout where profile-specific env vars are absent.
- Fix broken AI button contracts discovered during inventory:
  - SOC Command Center `Explain recon` now maps to a supported backend explain action.
  - Generic Anakin command actions such as summarize/explain/suggested-actions now map to supported backend explain actions.
  - Workspace section IDs from command-palette flows are normalized safely to backend context types.
- Include selected profile/model/timeout metadata in sanitized AI response metadata.

## Capabilities

### New Capabilities
- `ai-model-profile-routing`: Backend-trusted semantic routing for every AI invocation, including model profiles, profile metadata, and button-contract coverage.

### Modified Capabilities

## Impact

- Backend: AI config, gateway, provider request generation, explain/chat/draft/investigation/repo/SOC briefing call sites, context normalization, profile inventory tests.
- Frontend: AI metadata display only; clients do not choose models or timeouts.
- Runtime: VM/Mini PC will need profile-specific `.env` values only if defaults are not desired, and the Mini PC must have required Ollama models installed. This task does not change runtime config or pull models.
- Database: no migration.
