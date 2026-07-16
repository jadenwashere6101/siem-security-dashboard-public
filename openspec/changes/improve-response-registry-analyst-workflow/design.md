## Context

The Response Registry is intended to be the canonical analyst workspace for indicator response state and Blocklist tracking, but its current implementation still exposes backend truth in a low-context way. The panel can list records, open a detail pane, and invoke canonical commands, yet it does not consistently guide investigation flow, does not expose relationships as navigable analyst objects, and does not always carry enough provenance into mutations to make action results feel reliable from every entry surface.

The scope here is intentionally narrow. The change must stay inside the Response Registry experience and its immediate read or write contracts. It must not duplicate Alert Details, Incident Details, or create a second case-management surface. It also must not redesign SOAR, approvals, playbooks, or other workspaces.

## Goals / Non-Goals

**Goals:**

- Define one deterministic investigation handoff for the Response Registry detail pane.
- Define a compact, clickable relationship summary for the most relevant linked objects.
- Define a lightweight Response Summary and a rule-driven Recommended Next Step section.
- Define consistent analyst-facing outcome badges for registry history and summary surfaces.
- Define sufficient command context so manual registry actions behave consistently whether the record was opened from the registry, an alert, an incident, or another investigation handoff.
- Define actionable analyst error feedback and the scoped retry or pagination fixes already identified in the audit.

**Non-Goals:**

- Redesigning the application shell, adding a new dashboard, or broadening scope outside Response Registry.
- Duplicating full Alert Details or Incident Details inside the registry.
- Adding raw JSON dumps, unbounded evidence, or many new list columns.
- Creating a generic case-management system, new response framework, or unrelated SOAR redesign.
- Changing runtime configuration, migrations, VM state, or production data as part of this design.

## Decisions

### 1. One canonical investigation handoff

The Response Registry SHALL expose one `Investigate` action instead of multiple competing investigation choices. The target is deterministic: linked incident first, then originating alert, then Source/IP Context, then an explanatory no-target state.

Rationale:

- Analysts need one obvious next action, not a choice between raw IDs.
- The existing audit shows the detail pane already has enough related identifiers to route deterministically.
- This keeps the registry lightweight by sending analysts to authoritative detail surfaces instead of duplicating them.

Alternative considered:

- Expose separate `Open Incident`, `Open Alert`, and `Open Source Context` controls. Rejected because it shifts triage logic onto the analyst and recreates the current ambiguity in a more crowded form.

### 2. Relationship summary stays compact and navigable

The detail pane SHALL replace raw related-ID text with a compact relationship summary that renders counts and click targets for alerts, incidents, playbooks, and approvals. The registry remains a response-state workspace, not a full investigation workspace.

Rationale:

- Relationship counts answer “what else is connected?” quickly.
- Clickable counts preserve investigation momentum without duplicating downstream detail UIs.
- A compact summary is sufficient because the full evidence remains in the linked workspaces.

Alternative considered:

- Inline tables for every relationship type. Rejected because it bloats the pane and duplicates downstream workspace responsibilities.

### 3. Command reliability depends on carried provenance, not local inference alone

Registry commands SHALL receive sufficient context to execute truthfully regardless of entry surface. The design does not prescribe an exact payload shape, but the implementation must preserve all available alert, incident, and indicator provenance through the command path and must not rely solely on a best-effort indicator string when richer context is already known.

Rationale:

- The current panel sends only `indicator_value` for manual registry actions, which is the most likely explanation for the reported analyst-facing reliability problems.
- The backend already supports alert and incident identifiers, so the contract should require using them when available.
- This preserves canonical behavior and auditability without inventing a second command system.

Alternative considered:

- Make the registry fully self-sufficient from `indicator_value` alone. Rejected because it loses provenance and weakens failure explanation for records opened from correlated workflows.

### 4. Analyst guidance must be deterministic and rule-driven

The workspace SHALL add a compact Response Summary and a rule-driven Recommended Next Step section. Recommendation text must derive from current disposition, latest outcome, linked relationships, and approval state; it must not use generated prose or AI decision-making.

Rationale:

- Analysts need a fast read on what happened and what to do next.
- Deterministic rules are testable and consistent across environments.
- This avoids inventing a broader assistant layer inside the UI.

Alternative considered:

- Free-form narrative summaries. Rejected because they are harder to test and easier to drift from actual state.

### 5. Error handling and wording must explain state, not just failure

Generic mutation failures and ambiguous labels SHALL be replaced with analyst-facing messages tied to known failure classes and clearer control wording. This includes a dedicated detail retry, preserving list pagination on retry, separate reason state for tracking vs incident creation, and renaming `Escalate` to clearer incident language.

Rationale:

- The audit found that several failures are currently surfaced as generic command errors even when the likely cause is specific and actionable.
- Clear wording reduces mistaken expectations without changing backend truth.
- These fixes are high-value and still tightly scoped.

Alternative considered:

- Leave labels unchanged and document the nuance elsewhere. Rejected because the problem is in the live workflow, not in missing documentation.

## Risks / Trade-offs

- [Too much registry detail] → Keep summaries compact and route to authoritative workspaces for full investigation.
- [Navigation ambiguity when multiple relationships exist] → Use a fixed target priority for `Investigate` and surface the full relationship summary separately.
- [Overfitting error messages to current backend paths] → Define messages by stable failure class such as missing target, protected target, inactive tracking, or unavailable linked object.
- [Cross-workspace coupling] → Reuse existing navigation contracts and preserve existing authoritative destinations rather than inventing new routing logic.
- [Implementation drift into a larger redesign] → Keep all tasks bounded to Response Registry panel, its related service or API contract, and focused tests.

## Migration / Deployment / Rollback

- No database migration is expected.
- No VM activity is required for this authoring step.
- A future implementation pass would be deployable as normal frontend and backend source changes with focused regression coverage and no historical data rewrite.
- Rollback is source-only because the change is workflow and presentation oriented.

## Open Questions

- Whether the existing registry detail payload already carries all approval relationship IDs needed for navigation, or whether a small additive read-model expansion is required.
- Whether the recommended-next-step rules can derive approval state entirely from current linked records or need an explicit registry detail field.
- Whether any current registry records can legitimately lack every investigation target, and if so how frequently the no-target explanation path will occur.
