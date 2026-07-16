## 1. Command Reliability Contract

- [x] 1.1 Audit the current Response Registry mutation path and define the minimum alert, incident, and indicator context that must be preserved for manual commands from every supported entry surface.
- [x] 1.2 Update the registry command request and server-side handling so commands use the richest available provenance instead of relying on indicator value alone when correlated context exists.
- [x] 1.3 Add focused backend and frontend regression coverage for `monitor`, `stop_monitor`, and `block_ip` from registry-native, alert-driven, and incident-driven entry paths.

## 2. Investigation and Relationship Workflow

- [x] 2.1 Add one canonical `Investigate` action with deterministic target priority: linked incident, originating alert, Source/IP Context, then explicit no-target guidance.
- [x] 2.2 Replace raw related-ID text with a compact clickable relationship summary covering alerts, incidents, playbooks, and approvals.
- [x] 2.3 Add focused navigation tests proving relationship links and `Investigate` preserve the correct destination context.

## 3. Analyst-Facing Summary and Guidance

- [x] 3.1 Add a compact Response Summary that answers alert, indicator, response, and outcome without duplicating downstream detail panels.
- [x] 3.2 Add a deterministic Recommended Next Step section driven by current disposition, latest outcome, linked relationships, and approval state.
- [x] 3.3 Add consistent analyst-facing outcome badges for executed, awaiting approval, monitoring, tracking only, simulated, skipped, and failed states across the scoped registry surfaces.

## 4. Scoped Usability Fixes

- [x] 4.1 Add a retry control for detail-load failures and preserve current pagination when retrying list-load failures.
- [x] 4.2 Separate tracking reason and incident-creation reason inputs and rename `Escalate` to clear incident wording.
- [x] 4.3 Replace generic registry command failures with actionable analyst messages for known failure classes.

## 5. Verification

- [x] 5.1 Add focused Response Registry component coverage for loading, detail-error retry, relationship rendering, investigate routing, next-step guidance, and role-gated actions.
- [x] 5.2 Add focused API contract coverage for additive detail relationships and command-failure messaging where applicable.
- [x] 5.3 Run `openspec validate improve-response-registry-analyst-workflow --strict`.
- [x] 5.4 Run `git diff --check`.
