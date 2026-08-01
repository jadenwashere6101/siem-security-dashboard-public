## Why

Anakin still presents many repetitive AI controls even though the backend now has six canonical workflows. Analysts should primarily ask Anakin in natural language and use a few workflow shortcuts, not choose between dozens of action-specific buttons.

## What Changes

- Consolidate frontend AI controls around one Anakin assistant experience and six shared workflows:
  - `quick_explain`
  - `deep_investigate`
  - `decision_support`
  - `generate_artifact`
  - `soc_briefing`
  - `repo_assistant`
- Wire consolidated Anakin interactions to `POST /ai/workflows`.
- Keep SOC Briefing and Repo Assistant as explicit destinations/commands with existing role boundaries.
- Replace repeated summary/explain/why/suggested-action controls with surface-appropriate workflow shortcuts.
- Use a Generate Artifact menu for supported artifact types instead of individual draft buttons.
- Show classified workflow and model/profile metadata compactly in the Anakin response panel.
- Show truthful Deep Investigate running stages from backend lifecycle metadata without presenting synchronous requests as durable background jobs.
- Render low-confidence chooser state when the backend returns one.
- Preserve preview/confirm as separate gated post-artifact actions.
- Update frontend and acceptance tests so removed controls cannot silently return.

## Capabilities

### New Capabilities

- `anakin-interface-consolidation`: Consolidated Anakin UI controls, workflow shortcuts, artifact menu behavior, workflow routing visibility, and frontend acceptance coverage.

### Modified Capabilities

- None.

## Impact

- Frontend: AI services, Anakin command surface, contextual AI controls in dashboard/detail surfaces, response panel, command palette contracts, and focused tests.
- Backend: acceptance inventory/test expectations only; backend compatibility adapters remain.
- Runtime: no environment, model, database, deployment, or VM change.
