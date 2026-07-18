## Why

Production evidence from July 14, 2026 through July 15, 2026 showed a narrower pfSense interpretation bug than the earlier recon-policy work addressed. pfSense correctly preserved source, destination, direction, interface, action, and raw packet details, but the downstream detectors treated `source_ip` as the initiating attacker even when the blocked packet was outbound reply or teardown traffic from a protected host.

Confirmed examples included:

- `direction=out`
- `action=block`
- protected hosts such as `8.14.136.151`
- local service ports such as `443`
- remote ephemeral destination ports
- reply or teardown flag shapes such as `ACK`, `FIN+ACK`, `RST+ACK`, and `PSH+ACK`

That interpretation bug produced false pfSense port-scan evidence, false `possible compromised internal host` wording, and four open P2 incidents from protected hosts. The raw events are still useful and must remain visible. The change is to classify packet role before deriving attacker-oriented meaning.

## What Changes

- Add one deterministic pfSense traffic-role classifier for relevant TCP firewall events that distinguishes initiation-like traffic from reply-or-teardown-like traffic and from ambiguous traffic.
- Use that classification to stop reply-or-teardown outbound protected-host packets from counting as source-driven port-scan evidence by themselves.
- Refine repeated-deny interpretation so reply-style outbound protected-host bursts remain visible but no longer imply hostile initiation, incident eligibility, or containment by default.
- Add analyst-facing plain-English context explaining why the traffic was downgraded and what local evidence would still override that downgrade.
- Add focused regression tests across classifier behavior, detectors, incident eligibility, and alert explanation payloads.

## Capabilities

### New Capabilities
- `pfsense-outbound-reply-traffic-classification`: classify pfSense TCP packet role for downstream detector, incident, and analyst-context decisions without altering raw event preservation.

### Modified Capabilities
- (none)

## Impact

- **Affected code later:** `engines/detection_engine.py`, `core/incident_store.py`, `routes/alerts_events_routes.py`, `adapters/pfsense_filterlog_adapter.py` only if narrowly needed to persist existing packet facts already present in the raw log, and focused pfSense detector or incident tests.
- **Affected data model later:** none expected.
- **Affected APIs later:** additive pfSense alert context and why-fired evidence only.
- **Operational constraints:** no VM access, no production mutation, no historical incident cleanup, no parser redesign, no threshold tuning, and no raw-event rewriting.
