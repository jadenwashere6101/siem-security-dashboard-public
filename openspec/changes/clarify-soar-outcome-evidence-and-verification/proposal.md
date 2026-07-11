## Why

Canonical SOAR outcomes correctly distinguish simulation from real external effects, but affected UI surfaces often show only “Simulated” without enough linked evidence to explain why. Metrics contracts are well tested in source, yet representative production outcome chains and table-to-metric values remain unverified.

## What Changes

- **MAC AI:** Explain that Queue “Run simulation batch” processes pending work with the simulation executor and cannot perform real provider/firewall effects.
- **MAC AI:** Audit affected user-facing Simulation/Simulated occurrences and render available canonical evidence: execution mode, executed/external-effect state, reason/failure code, and linked queue/execution/delivery/approval identifiers.
- **MAC AI:** Clarify Recent Alerts and SOAR Queue/Playbooks/Operations/Metrics presentation without cosmetic global replacement or weakening fail-closed contracts.
- **MAC AI:** Verify UI/service/API/backend/table ownership for every SOAR Metrics section and add focused regression coverage.
- **VM AI, future explicit authorization only:** perform read-only representative production tracing and metric/source reconciliation; no sends, retries, remediation, or mutation.
- Do not enable Teams or real firewall execution.

## Capabilities

### New Capabilities

- `soar-operational-verification`: Defines read-only production outcome-chain and metric-source verification evidence, gates, and stop conditions.

### Modified Capabilities

- `soar-mode-aware-presentation`: Requires canonical outcome evidence and explicit simulation-batch explanation across affected UI surfaces.

## Impact

- Frontend: ResponseOutcome components, Alert Details/Recent Alerts, SOAR Queue, Playbooks, Operations, Metrics, linked-record controls, services, and tests.
- Backend/API: primarily contract verification; additive read-model fields only if existing canonical fields cannot supply evidence. No writer semantics or real-execution enablement.
- Database/migrations: none expected; any discovered contract gap requiring schema work stops for a separate proposal.
- Future VM phase is read-only after approved deployment and clean-tree verification.

