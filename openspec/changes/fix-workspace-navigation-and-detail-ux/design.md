## Context

`SidebarLayout` owns the scrollable `<main>`, but `App.js` only stores an `activeSection` string. `handleNavigate` and specialized handlers replace content without controlling that element. Incident, Playbook, and Dead Letter details are placed after their complete lists. Existing deep navigation carries filters/correlation through ad hoc state and must not be broken.

## Goals / Non-Goals

**Goals:**

- **MAC AI:** Make ordinary navigation open the target workspace at its top and move keyboard focus to its primary heading.
- **MAC AI:** Preserve intentional deep targets, filters, selected identifiers, and correlation provenance.
- **MAC AI:** Present selected details near their list at desktop and as a stacked, focused region at narrow widths.
- **MAC AI:** Provide deterministic back/close focus restoration and testable behavior without changing APIs.

**Non-Goals:**

- React Router, URL history, backend navigation state, new API contracts, or database state.
- Redesigning record contents, changing RBAC, or changing response semantics.
- VM runtime work.

## Decisions

### 1. The shell owns navigation effects

`SidebarLayout` SHALL expose the actual main element through a ref/imperative destination interface. `App.js` SHALL issue a structured navigation request containing `sectionId`, `destination` (`top`, `element`, or `preserve`), optional target key, and a nonce. Ordinary sidebar/SOC attention navigation uses `top`; explicit Recent Alerts and Response Registry requests use `element`; `preserve` is permitted only for same-workspace state updates.

This centralizes scroll behavior without introducing a router. A global `window.scrollTo` was rejected because `<main>`, not `window`, scrolls.

### 2. Scroll and focus are one transaction

After the requested section commits, the shell waits until the target ref exists, scrolls it with user motion preferences respected, then focuses a programmatically focusable heading/region. Missing deep targets fail safely to the workspace top. Navigation never silently retains an unrelated previous offset.

### 3. Use a responsive master-detail region

Incidents, Playbooks, and SOAR Operations SHALL render list and detail in a two-column master-detail grid when space permits. On narrow viewports, detail stacks immediately after the list container and the View action scrolls/focuses it. This retains surrounding context and avoids adding another fixed overlay competing with Alert Details. Close returns focus to the invoking row/button when it still exists.

### 4. Preserve deep-link state separately from presentation

Existing registry navigation payloads, source-IP filters, related alert/incident IDs, and approval filters remain authoritative. The new destination field controls only presentation. No API request shape changes.

### 5. Acceptance evidence

Component tests SHALL verify scroll/focus calls and preserved filters. Manual evidence SHALL cover keyboard-only use, reduced motion, 1280px/desktop and narrow/mobile layouts, dark theme, sticky/top-bar obstruction, and all named transitions. `npm run build` and `git diff --check` are gates.

## Risks / Trade-offs

- [Async target not mounted] → Retry only through React effects keyed to section/request nonce; fall back to the workspace heading.
- [Focus steals input unexpectedly] → Move focus only for explicit navigation/View actions, never background refreshes.
- [Long tables still dominate narrow layouts] → Bound the list region visually while preserving existing data access and scrolling.
- [Ad hoc handlers bypass contract] → Repository-wide audit and tests for every `setActiveSection`, `onNavigate`, `Open in`, and `View` path.

## Migration / Deployment / Rollback

1. **MAC AI:** Implement shell contract, migrate handlers, then migrate detail surfaces and tests.
2. **MAC AI:** Run focused/full affected tests, production build, accessibility and visual checks.
3. Future deployment requires explicit authorization and deploys only the Mac-built frontend artifact; no backend restart or migration.
4. Roll back by deploying the previous frontend artifact/approved commit. No data rollback exists.

## Stop Conditions

- Stop if a deep destination would lose source-IP, related-resource, approval, or filter context.
- Stop if implementation requires router adoption, API changes, or VM source edits without a new approved design.
- Stop if keyboard focus cannot be restored predictably or a detail pattern obscures actions at required viewports.

## Open Questions

None material. The exact grid breakpoint may be selected during visual verification without changing the contract.

