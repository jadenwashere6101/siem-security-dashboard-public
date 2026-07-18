## Context

The existing pfSense pipeline is field-correct and semantically overconfident. The adapter preserves pfSense source and destination fields accurately, and the normalized event keeps raw packet text. The problem begins later when downstream detectors infer attacker initiation directly from `source_ip` plus breadth or repetition.

That assumption fails for a real pfSense packet class already observed in production on July 14-15, 2026:

- `firewall_block`
- `direction=out`
- source IP belongs to a protected host
- source port is a local service port such as `443`
- destination port is ephemeral
- TCP flags are reply or teardown shaped rather than initiation shaped

Those packets can represent blocked replies, teardown traffic, or state/NAT edge cases from an existing connection rather than new attacker-initiated probing by the protected host. The fix should therefore live at the interpretation layer shared by pfSense detectors and analyst context, not in the parser and not as a broad incident-policy rewrite.

## Goals / Non-Goals

**Goals**

- Classify relevant pfSense TCP traffic into reusable role buckets before deriving scan or compromise meaning.
- Prevent reply-or-teardown outbound protected-host traffic from creating false port-scan evidence, false hostile repeated-deny escalation, false incidents, or false containment paths by itself.
- Preserve legitimate outbound initiation detection, inbound external scan detection, and any stronger local-evidence override path.
- Expose plain-English explanation so analysts understand the downgrade and the remaining escalation path.

**Non-Goals**

- No parser rewrite or NAT-state reconstruction engine.
- No historical record rewrites or incident cleanup.
- No new alert families.
- No threshold redesign outside the minimum needed prospective interpretation changes.
- No VM production audit or deployment work in this change.

## Decisions

### 1. Add one shared pfSense traffic-role classifier

The cleanest architecture is one backend helper reused by pfSense detectors and alert-context generation.

Recommended contract:

- `classification`
  - `initiation_like`
  - `reply_or_teardown_like`
  - `ambiguous`
  - `not_applicable`
- `reason`
  - short plain-English justification
- `evidence`
  - bounded facts used for the decision such as direction, protected-host membership, source port, destination port, and TCP flags

The classifier should inspect existing packet facts only:

- protocol
- direction
- source and destination IP protected-range membership
- source port
- destination port
- TCP flags
- interface only where it clarifies the explanation

Deterministic principles:

- `initiation_like`
  - TCP `SYN` without `ACK`
  - especially from a protected source toward many remote destinations or services
- `reply_or_teardown_like`
  - no `SYN`
  - reply or teardown shapes such as `ACK`, `FIN+ACK`, `RST+ACK`, `PSH+ACK`
  - plus outbound protected-host service-port to remote-ephemeral-port patterns when consistent with an existing connection response
- `ambiguous`
  - missing or incomplete flags
  - mixed packet facts that do not reliably reveal the initiator
- `not_applicable`
  - non-TCP traffic

### 2. Port-scan logic should consume only initiation-like source evidence

`pfsense_firewall_port_scan` is the clearest false-positive path. Today it groups blocked events by `source_ip` and breadth without deciding whether the source was actually initiating those packets.

Revised policy:

- initiation-like blocked traffic still contributes to source-driven port-scan breadth
- inbound external scanning remains unchanged
- reply-or-teardown-like outbound protected-host packets stay stored and queryable but do not count as scan breadth by themselves
- ambiguous packets are conservative evidence and must not create high-confidence source-driven scan conclusions without corroboration

### 3. Repeated-deny interpretation should stay visible but stop implying compromise by default

`pfsense_firewall_repeated_deny` should preserve low-friction operational visibility for this packet class while changing the hostile interpretation.

Required behavior for reply-or-teardown-like outbound protected-host traffic:

- remain visible as an alert or operational record
- do not claim `possible compromised internal host`
- do not become containment-eligible by themselves
- do not become incident-eligible by themselves
- explain that the observed packet looks like blocked outbound response or teardown traffic and does not establish host compromise

Existing stronger evidence still overrides:

- initiation-like outbound traffic
- meaningful breadth
- repeated behavior across windows
- corroborating detections
- progression or successful behavior

### 4. Incident policy should remain driven by operational flags

`core/incident_store.py` already respects `context.operational_flags.incident_eligible`, so the narrowest architecture is to change pfSense detector-produced flags prospectively.

Required rule:

- reply-or-teardown-like outbound protected-host traffic alone is not sufficient for incident creation, `block_ip` approval, or compromised-host ownership

This preserves the current architecture and avoids a second policy engine.

### 5. Analyst explanation should be additive and local-evidence-first

The alert message and context should explain the downgrade with packet facts, not hide the alert.

Target wording direction:

- `Blocked outbound response traffic`
- `Source used a protected service port`
- `Remote port was ephemeral`
- `TCP flags matched reply or teardown traffic`
- `No connection-initiation evidence was observed`
- `Host compromise is not established`

The same context should also make clear that stronger local evidence still restores urgency.

## Alternatives Considered

### Alternative: Treat all outbound protected-host repeated denies as suspicious

Rejected because the July 14-15, 2026 production evidence already disproved that assumption.

### Alternative: Rewrite pfSense parsing to infer initiator state

Rejected because the parser is already preserving the correct raw facts and this change does not justify stateful reconstruction.

### Alternative: Fix incidents only

Rejected because the false incident is downstream of false detector interpretation, false alert wording, and false containment eligibility.

## Risks

- Over-conservative classification could hide true outbound initiation evidence if the packet-role helper is too broad.
- TCP flag extraction may require a narrowly additive parser change if the current normalized payload does not expose flags cleanly enough for deterministic downstream use.
- Ambiguous packets need careful treatment so the system neither overclaims nor silently drops useful evidence.

## Implementation Phases

1. Add the shared classifier and its unit coverage.
2. Thread classifier output into pfSense repeated-deny and port-scan detector decisions and messages.
3. Surface classifier context in why-fired and alert detail payloads where useful.
4. Run focused regression tests and strict OpenSpec validation.
