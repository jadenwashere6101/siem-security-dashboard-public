## Context

The deployed backend baseline `98b11a3` provides private PostgreSQL threads, ordered turns, active-request recovery, reset, entity focus, clarification turns, and workflow orchestration. The frontend only creates a default thread before a request; it neither reads the transcript nor restores it. `App` independently mounts `AiResponsePanel` and `AnakinCommandSurface`, while alert details, the investigation drawer, and the command palette own separate fixed overlays.

### Live UI audit

The local built `/siem/` shell was inspected in headless Chrome at 1440x1000. The dashboard visibly presented `ANAKIN`, `Ask Anakin`, `Quick Explain`, and `Deep Investigate` as competing controls. A dashboard Ask opened `AiResponsePanel` while the floating Ask trigger remained available. Opening the floating control then mounted a second dialog over it: the response occupied `x=980..1422, y=603..769` and the command surface occupied `x=882..1422, y=430..781`. `AlertSidePanel` uses a higher foreground level than both, so responses launched inside it are hidden behind it.

| Surface | Visible intent and actual behavior | Current continuity / layout finding |
|---|---|---|
| Dashboard metrics | `Anakin`, `Ask Anakin`, `Quick Explain`, `Deep Investigate`; immediately invokes workflow from dashboard context | Latest result opens in separate response panel; no follow-up transcript |
| Floating Ask | `Ask Anakin` opens `Analyst command surface`, text area, and unexplained workflow chips | Independent dialog can overlap response panel |
| Recent Alerts / Alert Details | Row can remain expanded while a fixed right drawer opens; controls invoke alert workflow | Response panel mounts behind higher alert drawer |
| Source IP Context | Raw workflow labels plus artifact select, source IP supplied | Result leaves source surface and loses visible conversational context |
| Incident view | Deep Investigate, Decision Support, artifact select, incident supplied | Inline detail and global response are disconnected |
| SOC Command Center / Recon | Workflow buttons on selected recon activity and source-IP context drawer | Uses global latest-response panel; source-IP drawer can compete with Anakin; no thread restoration |
| Response Registry | Workflow buttons on selected indicator | Uses global latest-response panel; generic implementation labels |
| Analyst Workspace | Workflow buttons on active investigation | Conversation does not write workspace state, but UI does not disclose thread identity |
| Command Palette | Raw workflow names/descriptions invoke the same callback | Palette closes, then a separate response panel appears |
| Repo Assistant | Dedicated super-admin repository panel | Correctly isolated; must remain separate |
| SOC Briefing | Dedicated job/history surface | Correctly isolated; must remain separate |

## Goals / Non-Goals

**Goals:**

- One canonical SIEM Anakin conversation panel with ordered authoritative turns and one primary question input.
- One application-shell foreground owner coordinating alert details, investigation, palette, and Anakin transitions.
- Task-oriented contextual shortcuts that preserve current entity and thread intent.
- Refresh, close/reopen, pending progress, clarification, failure/retry, reset/new thread, expiry, and stale-result handling.
- Accessible focus/Escape behavior and usable desktop/narrow layouts.

**Non-Goals:**

- Backend reasoning, reference resolution, model/tool/profile changes, database changes, frontend redesign outside Anakin, artifact apply/confirm, Repo Assistant integration, or SOC Briefing chat.

## Decisions

### App owns one canonical surface and foreground layer

`App` owns `foregroundLayer` and one controlled conversation state. `AnakinCommandSurface` becomes the only SIEM conversation response component; `AiResponsePanel` is removed from App. Contextual controls dispatch an open/focus intent through the existing callback. Opening one foreground owner intentionally closes the previous owner, and an alert-drawer shortcut hands off its alert context before the drawer closes. Command palette and investigation drawer report controlled visibility to App. This prevents duplicates by component topology and state ownership, not z-index escalation.

Alternative: patch every panel z-index. Rejected because both Anakin components could still mount and async output could remain attached to an obscured surface.

### Server-authoritative transcript with safe browser pointers

The panel resolves/creates a thread through `POST /ai/threads`, reads it with `GET /ai/threads/<id>`, and pages turns with `GET /turns`. Browser session storage retains only owner-scoped thread and request IDs. Every open, refresh, completion, conflict, and retry reloads authorized server state. Logout removes all pointers before another identity can render.

Alternative: preserve rendered messages in browser storage. Rejected because it creates stale, unauthorized, and conflicting history.

### A surface epoch binds async work to the visible thread

Every thread selection increments an epoch. Poll completions update the transcript only when request ID, thread ID, and epoch still match; otherwise they remain recoverable from the authoritative thread when reopened. Duplicate submit is disabled locally and remains protected by backend client-request idempotency.

### Contextual controls use analyst tasks

The common labels are `Ask Anakin`, `Explain this alert` (or current entity), `Investigate further`, `Recommend next action`, and `Draft an analyst artifact`. Tooltips explain the task. Freeform Ask requires no workflow selection. Shortcuts preserve workflow and current entity and execute in the same panel/thread; they are not modes or separate applications.

### Thread presentation is a projection, not a result formatter

The panel renders immutable turns by role, content, lifecycle, workflow task label, entity snapshot, and structured artifact safety fields. Existing validated workflow responses remain the source of content. Clarification assistant turns render like normal turns. Remembered state discloses active entity, compact summary, unresolved questions, corrections, and evidence counts without exposing internal routes, tools, model/profile, or request architecture.

### Foreground behavior

Opening Anakin from alert details captures alert identity, closes the drawer, and opens the conversation panel in the same frame. Opening alert details closes Anakin. The SOC Command Center source-IP dialog, command palette, and investigation drawer also participate in the shared handoff contract. Escape closes only the active owner and restores focus. At narrow widths the conversation occupies the viewport; desktop uses a fixed right panel. The panel owns its scrolling and does not globally trap body scroll.

## Failure Matrix

| Failure class | Shared invariant | State/layout owner | General variants tested |
|---|---|---|---|
| Response behind drawer | One foreground owner; handoff before render | App + alert table callback | Expanded row, drawer shortcut, direct global open |
| Two Anakin surfaces | Exactly one mounted response component | App | Dashboard then floating, palette then contextual |
| Competing overlays | Opening a layer closes prior layer | App | Alert, source-IP dialog, investigation, palette, Anakin orderings |
| Stale result in new thread | Request, thread, and epoch must match | Conversation controller | Entity switch, close/reopen, delayed completion |
| Resize / narrow width | Stable viewport-constrained panel | Conversation component | 1440, 1024, 430 widths |
| Refresh during async | Reload thread and active request from server | Conversation controller | Queued/running/terminal |
| Expired/unavailable | Clear pointer and offer fresh thread | Conversation controller | 410, inaccessible target |
| Reset while pending | Disable reset or confirm then detach old request | Conversation controller | Pending and completed |
| Clarification / no entity | Render assistant turn; no fake progress | Conversation component | Ambiguous reference, dashboard-only context |
| Focus / Escape / scroll | Only active owner handles Escape and focus return | App + controlled overlays | Mouse, keyboard, nested initiator |
| Duplicate submit | Single local submission plus backend idempotency | Conversation controller | Double click, repeated shortcut |
| Boundary leakage | SIEM registry excludes Repo/SOC from thread commands | Command registry | Palette and global shortcuts |

## Whack-A-Mole Review

- **Canonical surface:** the controlled `AnakinCommandSurface` mounted once by `App`.
- **Visibility owner:** `App.foregroundLayer` and conversation controller state.
- **Contextual invocation:** every `AnakinWorkflowControls` action calls one App handler with entity/workflow intent.
- **Stacking owner:** App transition rules; CSS only describes the selected layer.
- **Can two response components mount?** No; `AiResponsePanel` is removed from the shell and no contextual component mounts a response.
- **Can output render under another active layer?** No; Anakin is rendered only while it owns foreground.
- **Can stale async output attach after switch?** No; request/thread/epoch equality is required before visible update.
- **Are labels task-based?** Yes; legacy workflow names remain internal values only.

## Risks / Trade-offs

- [Closing alert details changes the analyst's immediate layout] -> Preserve the alert as the visible active entity and restore focus/context when Anakin closes; this is clearer than accidental overlap and avoids a cramped double drawer.
- [Existing backend turn content has several structured shapes] -> Render only known safe display fields and fall back to stored turn content, never stringify arbitrary objects.
- [A thread can contain more than one page of turns] -> Follow every server cursor in order so the newest persisted response is never silently omitted; reject a non-advancing cursor instead of looping or truncating.
- [Local audit data source returned no alerts] -> Source topology and measured overlap prove the defect; focused tests provide populated alert/entity scenarios and final browser verification uses deterministic local fixture interception if needed.

## Migration Plan

No schema migration is required. A later authorized deployment ships the frontend bundle with narrow AI-service plumbing. Rollback restores the previous frontend bundle; backend threads remain compatible and authoritative.

## Open Questions

None. Explicit New Thread is implemented as a non-default thread using the existing API; reset uses the existing reset endpoint and fresh replacement semantics.

## Production Correction: Bounded Turn Persistence

Production requests built by the canonical App path carry evidence-rich workflow context. A measured dashboard request was 8,094 serialized bytes at depth 6. Conversation orchestration then embedded its resolved copy under `anakin_turns.structured_payload.resolved_execution_context`, producing 5,873 bytes at depth 7 and correctly triggering the unchanged session-memory depth limit of 6 before model invocation.

The workflow request and conversation turn have different storage contracts. The workflow path retains the complete validated context needed by prompts and tools. The turn serializer persists only the question in `content`, workflow intent, compact entity identity/display fields, bounded reference outcome, safe provenance, and artifact safety labels. It must not copy workspace state, workflow envelopes, tool evidence, or nested context trees into `structured_payload`.

All mounted entry points continue through `App.handleAskAi` and therefore one frontend workflow-request builder. Backend orchestration applies the canonical turn serializer regardless of entry point or client variation. Retry retains the corrected workflow request and never reconstructs a turn payload from rejected browser data.

| Failure class | Invariant | Enforcement | Variants |
|---|---|---|---|
| Rich UI context exceeds turn depth | Workflow context and turn memory are serialized separately | Shared App request builder plus orchestration turn serializer | Dashboard, alert, source IP, incident, recon, registry, workspace |
| Deep metadata reaches persistence | Only allowlisted semantic scalars and bounded entity/reference lists enter a turn | Orchestration serializer before `append_turn` | Nested alert/event metadata and unknown objects |
| Retry repeats rejected shape | Retry reuses full workflow execution context but turn persistence is regenerated canonically | App retry plus backend idempotency | Sync and async workflows |
