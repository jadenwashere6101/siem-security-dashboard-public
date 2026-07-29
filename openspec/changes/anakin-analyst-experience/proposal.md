## Why

Analysts currently have multiple AI entry points across dashboard, recon, incident, and SOC command center surfaces. These entry points are useful, but they do not yet feel like one coherent Anakin workflow. Analysts should be able to ask, summarize, investigate, explain, draft, and review suggested actions through one command architecture while preserving contextual shortcuts where they already help.

This change builds directly on `analyst-experience-foundation`. It reuses the responsive shell, dark SOC theme primitives, AI/cyan semantics, sidebar/topbar behavior, and grouped feed patterns without changing the foundation architecture.

## What Changes

- Introduce a unified Anakin command surface that orchestrates existing AI capabilities instead of duplicating them.
- Define one reusable AI command model, action registry, context provider pattern, and command execution flow.
- Route existing contextual AI buttons through the same command architecture while keeping them visible where appropriate.
- Add a read-oriented global command palette for navigation, object lookup, quick filters, common analyst actions, and Ask Anakin.
- Add a reusable Threat Brief surface that answers “What requires my attention right now?” using existing authoritative frontend data and service results where possible.
- Define extension points for Analyst Workspace, Investigation Drawer, Threat Story, and future AI tools without implementing those later features.
- Do not add new persistence, RBAC, backend AI redesign, LLM providers, theme redesign, shell redesign, privileged palette mutations, or new backend workflows.

## Capabilities

### New Capabilities

- `anakin-analyst-experience`: Covers unified Anakin command orchestration, global command palette design, Threat Brief presentation, reusable AI command registry/context providers, and extension points for later analyst workflows.

### Modified Capabilities

- None.

## Impact

- Frontend architecture: new command registry/orchestrator, command surface components, command palette components, Threat Brief components, and focused tests.
- Existing AI entry points: preserved visually where useful, but routed through shared command definitions.
- Existing services/routes: reused. No backend AI route redesign required for the initial implementation.
- Backend/API/database: no required backend workflows, schema changes, persistence, new RBAC, or VM work.
- Verification: focused frontend tests for command registry behavior, command surface routing, palette keyboard behavior, Threat Brief derivation, existing AI affordance preservation, production build, `git diff --check`, and strict OpenSpec validation.
