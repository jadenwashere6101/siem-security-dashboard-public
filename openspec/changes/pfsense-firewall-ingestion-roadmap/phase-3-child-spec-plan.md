# Phase 3 Child Spec Planning and Scope Boundaries

Date: 2026-07-07

This is parent-roadmap planning only.

Phase 3 does not implement anything. Phase 3 does not create code. Phase 3 does not open Azure or VM ports. Phase 3 exists to define the child specs that will be created next.

The existing pfSense parent roadmap is enough to track the five child specs. A separate Phase 3 parent coordination spec is not needed.

## Recommended Child Spec Sequence

1. `pfsense-filterlog-parser-normalizer`
2. `pfsense-ingest-route-pipeline`
3. `pfsense-udp-listener-daemon`
4. `pfsense-firewall-detections-soar`
5. `pfsense-deployment-runtime-readiness`

## Dependency Notes

- Ingest route depends on parser normalized output contract.
- UDP listener depends on parser and ingest route contract.
- Detections/SOAR depend on stable normalized firewall event taxonomy.
- Deployment/runtime readiness depends on all code specs.
- Azure NSG and uncle handoff remain blocked until deployment/runtime readiness.
- External/live pfSense traffic remains blocked until synthetic validation passes.

## 1. pfsense-filterlog-parser-normalizer

Category: CODE SPEC

Purpose:

Parse and sanitize pfSense syslog/filterlog input into a validated normalized event contract.

Topics this future child spec should cover:

- syslog envelope handling
- UTF-8 safety
- control-character stripping
- packet-size assumptions
- IPv4 TCP/UDP pfSense filterlog parsing
- safe handling for IPv6/unknown variants
- malformed input behavior
- parse failure telemetry
- normalized event shape
- `source=pfsense`
- `source_type=firewall`
- no DB writes
- no Flask route
- no UDP socket
- no deployment

Why this is code:

It will eventually create or modify parser/adapter helper modules and tests.

## 2. pfsense-ingest-route-pipeline

Category: CODE SPEC

Purpose:

Add the centralized backend ingestion path for normalized pfSense firewall events.

Topics this future child spec should cover:

- `/ingest/pfsense` route
- API key guard
- schema validation
- call existing centralized `ingest_normalized_event` flow
- event source and source_type handling
- error responses
- route/API tests
- preserve detection/correlation/SOAR/queue/incident orchestration

Boundary:

- no UDP socket
- no systemd service
- no Azure NSG
- no VM firewall
- no uncle/pfSense handoff

Why this is code:

It will eventually modify backend routes/ingest pipeline and tests.

## 3. pfsense-udp-listener-daemon

Category: CODE + DEPLOYMENT SPEC

Purpose:

Implement the runtime UDP listener daemon that receives pfSense syslog packets and forwards validated payloads/events to the Flask ingestion route.

CODE topics:

- UDP socket listener
- chosen high unprivileged port, preferably 5514 unless final confirmation says otherwise
- source IP allow-list enforcement
- packet size limit enforcement
- rate limiting
- parser integration
- HTTP forwarding to `/ingest/pfsense`
- rejected packet logging/metrics
- listener tests
- synthetic local packet test

NON-CODE/operator topics:

- future systemd service placement
- service environment variables
- service health/logging expectations
- port selection confirmation
- no Azure NSG rule yet unless deployment child spec authorizes it

Boundary:

- no detection rules
- no SOAR/playbook tuning
- no uncle handoff
- no live production traffic yet

Why this is code + deployment:

It will eventually add listener code and likely systemd/service wiring, but actual external exposure remains blocked until runtime readiness.

## 4. pfsense-firewall-detections-soar

Category: CODE SPEC

Purpose:

Add or tune detection and SOAR behavior for pfSense firewall events after the normalized event contract is stable.

Topics this future child spec should cover:

- firewall event-type mapping
- `firewall_block` / `firewall_allow` or equivalent event taxonomy
- repeated block detection
- port sweep / port scan style behavior
- high-volume inbound behavior if supported by real normalized data
- correlation expectations
- SOAR/playbook expectations if appropriate
- tests proving alerts fire only where intended
- tests proving allowed traffic does not trigger block-specific detections

Boundary:

- no UDP listener
- no parser redesign
- no Azure NSG
- no VM firewall
- no uncle handoff

Why this is code:

It will eventually modify detection/event-type logic and tests, and possibly playbook seed definitions.

## 5. pfsense-deployment-runtime-readiness

Category: NON-CODE + DEPLOYMENT SPEC

Purpose:

Deploy and validate the full pfSense ingestion path safely before asking uncle to configure pfSense.

NON-CODE/operator topics:

- VM clean sync gate
- requirements verification
- migration check if needed
- backend restart decision
- worker restart decision
- listener service install/start verification
- final listener port confirmation
- Azure NSG rule creation gate
- Azure NSG source restriction to expected pfSense public IP
- optional VM firewall defense-in-depth decision
- synthetic UDP packet runtime test
- dashboard verification
- API verification
- service log verification
- uncle handoff message
- post-handoff live traffic verification
- temporary NSG cleanup if any broad rule was used

CODE topics:

- only deployment helper scripts or systemd units if they were not already handled in the listener child spec
- no parser logic
- no detection logic
- no route logic

Boundary:

- no new parser behavior
- no new detection behavior
- no new playbook behavior unless separately scoped
- no live pfSense handoff until all readiness gates pass

Why this is non-code + deployment:

Most work is operational verification and controlled exposure, not application feature logic.

## Phase 3 Coordination Decision

A separate Phase 3 parent coordination spec is not needed because this existing pfSense parent roadmap will track the five child specs, their sequencing, and their dependency gates.

