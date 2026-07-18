## ADDED Requirements

### Requirement: pfSense packet-role interpretation SHALL precede attacker-initiator conclusions
The system SHALL classify relevant pfSense TCP traffic before deriving source-driven scan or compromise meaning from blocked packets.

#### Scenario: Clear initiation traffic is marked as initiation-like
- **WHEN** a pfSense TCP packet shows `SYN` without `ACK`
- **THEN** the system SHALL be able to classify that packet as `initiation_like`

#### Scenario: Clear reply traffic is marked as reply-or-teardown-like
- **WHEN** a pfSense TCP packet is outbound from a protected host and shows reply or teardown flags such as `ACK`, `FIN+ACK`, `RST+ACK`, or `PSH+ACK` without a new initiating `SYN`
- **THEN** the system SHALL be able to classify that packet as `reply_or_teardown_like`

#### Scenario: Missing packet-role evidence stays ambiguous
- **WHEN** the packet facts do not reliably show who initiated the connection
- **THEN** the system SHALL classify the packet as `ambiguous` rather than overclaiming attacker initiation

### Requirement: Reply-or-teardown outbound protected-host traffic SHALL stay visible without becoming attacker evidence by default
The system SHALL preserve reply-or-teardown outbound protected-host pfSense events and related alerts while preventing that packet class from creating hostile source-initiator conclusions by itself.

#### Scenario: Reply-only outbound protected-host traffic does not create source-driven port-scan evidence
- **WHEN** blocked outbound protected-host traffic is classified as `reply_or_teardown_like`
- **THEN** that traffic SHALL NOT count by itself toward source-driven `pfsense_firewall_port_scan` breadth

#### Scenario: Reply-only outbound protected-host traffic does not imply compromised host
- **WHEN** blocked outbound protected-host traffic is classified as `reply_or_teardown_like`
- **THEN** `pfsense_firewall_repeated_deny` SHALL keep the activity visible without labeling it as a compromised internal host by default

#### Scenario: Reply-only outbound protected-host traffic is not incident-worthy by itself
- **WHEN** blocked outbound protected-host traffic is classified as `reply_or_teardown_like` and no stronger local evidence is present
- **THEN** the system SHALL NOT make that packet class alone incident-eligible, containment-eligible, or approval-eligible

### Requirement: Local evidence SHALL override commodity packet-role downgrades
The system SHALL keep stronger local evidence authoritative over packet-role downgrades.

#### Scenario: Legitimate outbound initiation remains actionable
- **WHEN** a protected host shows initiation-like outbound blocked traffic with sufficient breadth, recurrence, or corroboration
- **THEN** the existing pfSense detection and incident path SHALL remain able to escalate prospectively

#### Scenario: Inbound external scanning remains intact
- **WHEN** an external source performs inbound initiation-like scanning against protected targets
- **THEN** the system SHALL continue to support `pfsense_firewall_port_scan` detection without requiring protected-host semantics

### Requirement: Analyst explanations SHALL describe the downgrade plainly
The system SHALL explain packet-role downgrades in plain English using the packet facts that drove the interpretation.

#### Scenario: Analyst sees why reply traffic was downgraded
- **WHEN** the system lowers urgency because traffic was classified as `reply_or_teardown_like`
- **THEN** the alert context or why-fired payload SHALL explain that the source used reply or teardown traffic and that host compromise is not established

#### Scenario: Supporting packet facts remain visible
- **WHEN** packet-role context is shown
- **THEN** the system SHALL expose bounded supporting facts such as direction, TCP flags, source service port, and destination ephemeral port when available

### Requirement: Historical artifacts SHALL remain unchanged
The system SHALL apply this change prospectively only.

#### Scenario: Existing incidents and alerts remain preserved
- **WHEN** alerts or incidents were created before this interpretation change
- **THEN** the system SHALL NOT rewrite, close, or delete those historical records automatically
