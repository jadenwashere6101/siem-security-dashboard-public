## Why

pfSense alerts already preserve destination evidence in `events.raw_payload`, but the investigation UI does not expose a normalized target summary. Analysts can see that an alert fired, but they still have to infer what asset or port was targeted from detector-specific text or by inspecting lower-level event data.

## What Changes

- Add a documented `target_context` snapshot shape under `alerts.context` for the four pfSense firewall alert families.
- Populate that snapshot from existing pfSense event fields already stored in `events.raw_payload`, without changing event storage or adding new tables.
- Keep the existing alerts APIs as the transport for the new read-only context.
- Add one compact read-only `Target Context` section to `AlertDetailsPanel` for pfSense alerts only.
- Distinguish exact single-target evidence from aggregate multi-target evidence and render `Unavailable` only when no target evidence exists.
- Preserve the existing `Why this fired` section, playbook behavior, and all non-pfSense alert surfaces unchanged.

## Capabilities

### New Capabilities
- `pfsense-alert-target-context`: read-only normalized target-investigation context for pfSense firewall alerts in existing alert APIs and Alert Details.

### Modified Capabilities
- (none)

## Impact

- Backend detection logic: additive context snapshot changes in `engines/detection_engine.py` for the four pfSense alert families.
- Alert APIs: additive `context.target_context` data through the existing alert payload and existing pfSense alert detail contract.
- Frontend: `frontend/src/components/AlertDetailsPanel.js` gains one compact pfSense-only display section.
- Tests: focused detector, alert API, and alert detail rendering coverage updates.
- Data model: no migration expected; existing `events.raw_payload` remains authoritative and `alerts.context` remains the minimal persisted summary.
