## 1. Command Foundation

- [x] 1.1 Define the shared frontend command model and action registry.
- [x] 1.2 Add context provider interfaces for workspace, selected object, visible data, and user role context.
- [x] 1.3 Add the command orchestrator that resolves availability, builds sanitized context, and invokes existing AI routes/services.
- [x] 1.4 Add focused tests for command registration, availability filtering, context assembly, and read-only safety.

## 2. Unified Anakin Command Surface

- [x] 2.1 Implement the primary Anakin command surface using analyst-experience-foundation primitives and AI/cyan tokens.
- [x] 2.2 Support Ask Anakin, Summarize, Investigate, Explain, Draft, and Suggested Actions through registry-backed commands.
- [x] 2.3 Preserve existing contextual AI buttons while routing them through the shared command architecture.
- [x] 2.4 Add responsive desktop/tablet/mobile presentation and accessible open/close/focus behavior.
- [x] 2.5 Add focused tests for command surface state, command execution, existing AI affordance preservation, and mobile behavior.

## 3. Global Command Palette

- [x] 3.1 Add Cmd/Ctrl+K palette shell with grouped results, search input, keyboard navigation, Escape close, and focus return.
- [x] 3.2 Register read-oriented navigation, object lookup, IP/incident/alert/recon lookup, Ask Anakin, common analyst action, and quick-filter commands.
- [x] 3.3 Ensure privileged mutations, approval execution, block actions, retries, and production-affecting operations are unavailable from the palette.
- [x] 3.4 Add focused tests for keyboard behavior, command filtering, object lookup states, quick filters, and read-only enforcement.

## 4. Threat Brief

- [x] 4.1 Define reusable Threat Brief input model sourced from existing authoritative frontend data and services.
- [x] 4.2 Implement deterministic sections for highest priority incident, riskiest source IP, pending approvals, automation failures, active investigations, and recommended next action.
- [x] 4.3 Support loading, empty, partial-error, stale, and populated states without duplicating backend business logic.
- [x] 4.4 Add focused tests for deterministic derivation, partial data handling, stale/error states, and no fabricated recommendations.

## 5. Extension Points and Integration Boundaries

- [x] 5.1 Document and implement registry extension slots for Analyst Workspace, Investigation Drawer, Threat Story, and future AI tools without enabling those features.
- [x] 5.2 Verify no new persistence, RBAC, backend AI redesign, LLM provider, theme redesign, or shell redesign is introduced.
- [x] 5.3 Add regression tests confirming existing navigation, workspace history, dashboard AI actions, recon AI actions, and SOC command center AI actions remain functional.

## 6. Verification and Handoff

- [x] 6.1 Run focused frontend tests for command registry, Anakin surface, command palette, Threat Brief, and existing AI affordances.
- [x] 6.2 Run the frontend production build.
- [x] 6.3 Run `git diff --check`.
- [x] 6.4 Run `openspec validate anakin-analyst-experience --strict`.
- [x] 6.5 Run `openspec status --change anakin-analyst-experience`.
- [x] 6.6 Confirm no implementation occurred during spec creation, and during implementation confirm no VM access, commit, push, deploy, backend workflow, persistence, migration, RBAC, or production mutation occurred.
