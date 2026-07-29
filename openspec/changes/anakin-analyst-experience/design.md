## Context

`analyst-experience-foundation` established the responsive shell, theme tokens, UI primitives, sidebar/topbar behavior, dashboard hierarchy patterns, and grouped operational feed model. This phase should reuse those pieces and add one coherent Anakin workflow layer above them.

The current app already has contextual AI affordances and AI service plumbing. This change should not redesign backend AI, add new providers, or create competing AI flows. It should centralize frontend command definitions, context assembly, and presentation.

## Goals / Non-Goals

**Goals:**

- Give analysts one primary Anakin command surface for ask, summarize, investigate, explain, draft, and suggested actions.
- Keep useful contextual AI buttons, but route them through the shared command registry.
- Add a read-oriented Cmd/Ctrl+K command palette for navigation, lookup, filters, common analyst actions, and Ask Anakin.
- Add a reusable Threat Brief surface that prioritizes attention using existing authoritative data.
- Create clear extension points for Analyst Workspace, Investigation Drawer, Threat Story, and future AI tools.

**Non-Goals:**

- No Analyst Workspace, Investigation Drawer, Threat Story, new persistence, new RBAC, backend AI redesign, new LLM providers, theme redesign, responsive shell redesign, privileged palette mutations, or VM work.

## Command Architecture

Add a frontend command architecture with these concepts:

- **Command model:** stable `id`, `label`, `group`, `intent`, `description`, `shortcut`, `requiredRole`, `readOnly`, `contextTypes`, `availability`, `execute`, and optional `analyticsLabel`.
- **Action registry:** one registry for Anakin commands and palette commands. Commands can be filtered by role, active section, selected object, data availability, and read-only safety.
- **Context providers:** small providers that expose contextual data from existing app state and services, such as current section, selected alert, selected incident, source IP, recon activity, dashboard filters, visible metrics, SOC command center data, and operational scope.
- **Command orchestrator:** resolves command availability, builds normalized command context, invokes existing AI routes/service functions, and opens the shared result surface.
- **Result surface:** uses foundation panels, badges, chips, loading/error states, and AI/cyan tokens. It should preserve existing distinction between read-only AI guidance, simulation, tracking-only state, pending, failed, blocked, and unknown outcomes.

The registry should be frontend-owned initially. It should avoid hardcoding business rules that already belong to existing services or derivation helpers.

## Component Relationships

- `App` owns global command providers and passes command handlers into shell surfaces.
- `AnakinCommandProvider` exposes registry, context, open/close state, active command, execution status, and results.
- `AnakinCommandSurface` is the primary analyst AI entry. Recommended placement: responsive dock/panel launched from the top bar and contextual AI buttons. On desktop it may render as a side panel or docked drawer; on mobile/tablet it should render as a full-width drawer/modal using foundation overlay behavior.
- `CommandPalette` listens for Cmd/Ctrl+K, searches commands and objects, and executes read-oriented commands through the same orchestrator.
- `ThreatBrief` renders a compact briefing panel/card using existing service data and derivation helpers. It can appear on the dashboard/SOC command center or in the Anakin surface, but should not create a second aggregation model.
- Existing `AiAssistantButton` usages become thin command launchers.

## Context Propagation

Context should flow from existing state into context providers, not from ad hoc prop drilling between unrelated panels. Providers should expose normalized context objects:

- `workspace`: active section, history destination, filters, operational scope.
- `object`: alert, incident, source IP, recon activity, approval, playbook execution, or notification delivery when selected.
- `data`: visible dashboard metrics, SOC command center summaries, grouped operations feed entries, and current loading/error state.
- `user`: current username, role, and derived role flags.

Providers must sanitize context before sending it to AI routes and avoid exposing secrets or infrastructure details.

## Orchestration Strategy

Start by wrapping existing AI actions with shared command definitions:

- Ask Anakin: open the command surface with current context.
- Summarize: generate a summary of the active surface or selected object.
- Investigate: invoke existing read-only investigation flows and bounded tool policies.
- Explain: explain an alert, recon activity, incident, metric, or workflow state.
- Draft: draft checklist, response recommendation, or analyst note text without saving.
- Suggested Actions: show recommended next steps derived from existing deterministic data plus optional AI explanation.

Existing AI routes should remain the execution backend. If a command cannot run because context is missing, it should explain what must be selected rather than fabricating context.

## Command Palette Design

The palette should be keyboard-first and read-oriented:

- Opens with Cmd/Ctrl+K and closes with Escape.
- Supports section navigation, object search, IP lookup, incident lookup, alert lookup, recon lookup, quick filters, common analyst actions, and Ask Anakin.
- Uses grouped results with icons, labels, secondary metadata, and disabled states.
- Does not run privileged mutations, approvals, block actions, retries, or production-affecting operations.
- Navigation and filters may update frontend state using existing app handlers.

Object search should initially use existing loaded data and existing service calls where already available. It should not require new backend aggregation endpoints for the first implementation.

## Threat Brief Design

Threat Brief should answer “What requires my attention right now?” with deterministic sections:

- Highest priority incident.
- Riskiest source IP.
- Pending approvals.
- Automation failures.
- Active investigations or recon activity.
- Recommended next action.

Data should originate from existing authoritative sources such as incident services, approval services, SOAR queue/dead-letter/notification data, dashboard summary data, recon activity services, and the grouped operations feed model. If a source is unavailable, the brief should render partial/stale/empty states clearly.

Recommended next action must be deterministic first. AI may explain why, but should not invent operational facts.

## Extension Points

- **Analyst Workspace:** commands can later support “pin to workspace,” “draft hypothesis,” or “create task,” but this phase only defines command slots and context metadata.
- **Investigation Drawer:** selected object context should be reusable by a later drawer without changing command definitions.
- **Threat Story:** command context can include timeline/correlation references, but no visual story view is implemented.
- **Future AI tools:** new commands can register capabilities through the same command model and context provider interface.

## Rollout Strategy

1. Introduce command registry, context provider, and orchestrator behind existing AI buttons.
2. Add the primary Anakin command surface using foundation primitives.
3. Add Cmd/Ctrl+K palette with navigation, lookup, filters, and Ask Anakin.
4. Add Threat Brief using existing data derivation and partial-state handling.
5. Incrementally route existing contextual AI buttons through the registry and remove only duplicate orchestration code.

## Risks

- Creating parallel AI entry points instead of one registry.
- Palette accidentally exposing mutation or privileged actions.
- Threat Brief duplicating business logic already owned by services or existing derivation helpers.
- AI commands fabricating context when required selected objects are unavailable.
- Mobile command surface overlapping shell controls if it bypasses foundation overlay primitives.

## Regression Strategy

- Unit tests for command registration, availability filtering, context assembly, and read-only command safety.
- Component tests for Anakin surface open/close, loading/error/result states, and existing AI button routing.
- Keyboard tests for Cmd/Ctrl+K, Escape close, focus return, arrow navigation, and command execution.
- Threat Brief tests for highest-priority derivation, partial data, empty states, stale/error states, and no fabricated recommended action.
- Existing AI affordance tests remain in place.
- Production build, `git diff --check`, and strict OpenSpec validation.

## Performance Considerations

Memoize derived command lists and brief inputs. Avoid broad polling. Reuse already loaded data before issuing extra service calls. Debounce object lookup where service search is used. Keep the palette and Anakin surface lazy-mounted where practical.
