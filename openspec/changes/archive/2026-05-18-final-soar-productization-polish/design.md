## Context

The project has moved from feature construction into final presentation readiness. A reviewer, interviewer, or demo audience should be able to understand the architecture, click through the right screens in a safe order, see expected states, and understand why real integrations are guarded while demo execution remains simulation-safe.

Current high-value surfaces include SOC Command Center, SOAR Metrics, SOAR Operations, Playbooks with execution timeline, integration status/safety, approvals, dead letters, notification delivery attempts, and worker health. The final polish should unify the story around these surfaces without changing runtime behavior.

## Goals / Non-Goals

**Goals:**
- Create a clear safe demo path with expected UI states and evidence capture points.
- Create portfolio/interview docs that explain architecture, decisions, safety boundaries, and project ownership.
- Create a UI polish checklist that can be implemented in one frontend/docs batch.
- Consolidate operational documentation and link the correct runbooks.
- Document final validation steps for local frontend, backend regression, deployment verification, secret checks, and clean git status.
- Keep the final implementation docs-first, with only small UI label/empty-state/navigation polish if review identifies low-risk improvements.

**Non-Goals:**
- No schema or migration changes.
- No backend execution semantic changes.
- No new SOAR mutations, retry semantics, approvals behavior, or integration behavior.
- No real Slack, Teams, email, webhook, firewall, or other outbound calls.
- No VM actions unless explicitly requested during implementation.
- No dangerous reset/cleanup scripts.
- No broad frontend rewrite or design system migration.

## Decisions

### Decision 1: Docs-first productization

Create docs that make the existing platform understandable and demo-safe before touching UI.

Rationale: The platform is already functionally mature. The highest leverage final work is reducing demo friction and making the system easy to explain.

### Decision 2: One consolidated demo story

The demo guide should define a single recommended click path:
1. Login / dashboard posture.
2. SOC Command Center for operational overview.
3. Playbooks execution detail and timeline.
4. SOAR Operations for dead letters/retry visibility.
5. SOAR Metrics for operational proof.
6. Integrations status for simulation/real safety posture.

Rationale: A scripted path avoids wandering through tabs and makes the project feel intentional.

### Decision 3: Safe reset/seed guidance without destructive scripts

Document manual or existing safe setup/reset guidance, but do not add destructive cleanup scripts in this spec.

Rationale: Demo reset is useful, but careless cleanup scripts can damage local/VM state or erase evidence.

### Decision 4: Small frontend polish only if it reduces confusion

Potential UI changes should be limited to labels, empty states, help text, role-safe visibility, and simulation/real-mode wording. Navigation simplification is allowed only when it preserves existing tabs and behavior.

Rationale: This spec is productization, not a new feature build.

### Decision 5: Safety boundaries are part of the product story

The docs should explain simulation-safe defaults, guarded real-mode integrations, firewall simulation-only boundary, rate limiting/dedup, audit logging, approvals, dead letters, and retryability as deliberate security engineering choices.

Rationale: In interviews and demos, safety tradeoffs are a strength if explained clearly.

## Documentation Set

Recommended docs to create or update:
- `docs/demo/soar-demo-checklist.md`: pre-demo checks, safe env assumptions, click path, expected states, screenshots/evidence checklist, stop conditions.
- `docs/demo/soar-demo-script.md`: spoken demo script with timing, what to click, what to point out, and safe reset/seed guidance.
- `docs/portfolio/soar-architecture-summary.md`: system architecture, data flow, major modules, worker model, UI surfaces.
- `docs/portfolio/technical-decisions.md`: key decisions and tradeoffs.
- `docs/portfolio/security-safety-boundaries.md`: simulation model, real-mode guards, no-real-firewall boundary, redaction, audit, rate limit/dedup, approvals.
- `docs/portfolio/what-i-built.md`: concise project ownership and feature summary.
- `docs/portfolio/resume-bullets.md`: draft resume/interview bullets.
- Existing runbooks index or README sections: link worker daemon, frontend/backend deploy, integration smoke tests, and Mac vs VM workflow.

Exact paths may be adjusted to match existing docs conventions discovered during implementation.

## UI Polish Checklist

Review and apply only low-risk frontend polish:
- Empty states say what is missing and what is safe to do next.
- Simulation/real-mode labels are clear and consistent.
- SOC Command Center, SOAR Metrics, SOAR Operations, and Playbooks have distinct purposes.
- Navigation labels are understandable for a demo audience.
- Duplicate or confusing tab wording is reduced where safe.
- Viewer/auditor restrictions remain intact.
- No new mutation controls are introduced.
- Narrow-width rendering remains readable.

## Final Validation Checklist

The implementation batch should document and, where appropriate, run:
- `CI=true npm test -- --runInBand SocCommandCenter`
- `CI=true npm test -- --runInBand PlaybookExecutionTimeline`
- `CI=true npm test -- --runInBand PlaybooksPanel`
- `CI=true npm test -- --runInBand SoarMetricsDashboard`
- `CI=true npm test -- --runInBand DeadLettersPanel`
- `npm run build`
- focused backend regression tests for SOAR execution, dead letters, approvals, integrations, and worker behavior.
- secret scan/manual check for docs and screenshots.
- `git diff --check`
- `git status --short`
- deployment verification steps for frontend/backend/worker without triggering real integrations.

## Risks / Trade-offs

- Docs can drift from implementation -> write checklist-style docs with concrete commands and source links.
- Demo reset guidance can become unsafe -> avoid destructive scripts and clearly mark manual steps.
- Too much UI polish can become a redesign -> constrain changes to wording, empty states, and navigation clarity.
- Screenshots can leak secrets or host details -> include a redaction/evidence review checklist.
- Mac vs VM workflow can confuse readers -> separate local development, VM deployment, and no-VM-action implementation boundaries.

## Migration Plan

1. Audit existing docs/runbooks and current top-level README structure.
2. Create demo checklist and demo script.
3. Create portfolio/interview readiness docs.
4. Update or add an operational docs index linking Mac workflow, VM workflow, frontend/backend deploy, worker daemon, and integration smoke tests.
5. Apply small frontend polish only if needed and clearly scoped.
6. Run focused frontend/build checks and backend regression checks appropriate to touched files.
7. Confirm no backend/schema/runtime/VM/real-integration behavior changed.
