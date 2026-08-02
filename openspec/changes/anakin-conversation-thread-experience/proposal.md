## Why

Anakin currently appears as independent dashboard controls, a floating command surface, and a separate response panel. These surfaces can overlap or render behind alert details, expose workflow terminology, and show only the latest response even though PostgreSQL now provides authoritative conversation threads and turns.

## What Changes

- Replace separate SIEM Anakin response surfaces with one canonical conversation panel owned by the application shell.
- Make every contextual Anakin control open or focus that panel with the current entity and optional analyst-task shortcut.
- Present one clear freeform question input, task-based optional shortcuts, active context, ordered turns, per-turn progress, clarification, retry, reset, and explicit new-thread behavior.
- Restore authoritative turns and active request progress from the existing thread APIs after refresh while storing only safe thread pointers in the browser.
- Coordinate alert details, investigation drawer, command palette, and Anakin as mutually exclusive foreground layers with deterministic focus, Escape, and scroll behavior.
- Preserve Generate Artifact preview-only labels and keep Repo Assistant and SOC Briefing outside SIEM conversation threads.
- Remove analyst-facing workflow, routing, request, profile, model, and implementation terminology from the conversation experience.

## Capabilities

### New Capabilities

- `anakin-conversation-thread-experience`: Canonical SIEM conversation surface, contextual shortcut routing, authoritative thread restoration, lifecycle presentation, and foreground-layer coordination.

### Modified Capabilities

None.

## Impact

The change affects the React application shell, shared Anakin controls and command registry, alert-details overlay coordination, AI client services, and focused frontend tests. It consumes existing authenticated thread, turn, reset, and async-request APIs without changing model selection, workflow reasoning, SOC tools, persistence schema, Repo Assistant, or SOC Briefing behavior.
