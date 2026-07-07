# Phase 2.5 Threat Model

Date: 2026-07-07

This is a parent-level threat model for future pfSense firewall log ingestion child specs. It is documentation/specification work only. It does not implement code, create implementation child specs, touch the VM, open ports, or implement security controls.

## 1. Scope

This threat model covers the future pfSense firewall log ingestion pipeline from the public Internet through runtime execution inside the SIEM.

Covered path:

```text
pfSense firewall telemetry
  -> public Internet
  -> Azure NSG
  -> Azure VM networking
  -> future pfSense listener daemon
  -> future parser
  -> future normalizer
  -> Flask ingest route
  -> PostgreSQL database
  -> detection engine
  -> playbook/SOAR engine
  -> dashboard and analyst workflows
```

This document covers architecture and security decisions only. It does not implement listener code, parser code, adapter code, routes, detection rules, deployment scripts, firewall rules, Azure NSG rules, or runtime configuration.

## 2. Protected Assets

Protected assets include:

- Azure VM
- SIEM backend
- PostgreSQL database
- SOAR worker
- future pfSense listener daemon
- future pfSense adapter
- detection engine
- playbook engine
- production firewall telemetry
- business network metadata
- deployment pipeline
- GitHub source repository

## 3. Trust Boundaries

Primary trust-boundary chain:

```text
Internet
  -> Azure NSG
  -> VM networking
  -> pfSense listener
  -> parser
  -> normalizer
  -> Flask ingest route
  -> database
  -> detection engine
  -> SOAR
  -> dashboard
```

Untrusted input first enters at the UDP packet received by the future pfSense listener. The packet sender address, packet bytes, syslog envelope, filterlog fields, and any raw payload text must be treated as untrusted until validated.

Trust boundary notes:

- Internet to Azure NSG: unauthenticated external traffic reaches the cloud perimeter.
- Azure NSG to VM networking: Azure filtering decisions become the first network control before VM runtime.
- VM networking to listener: the listener receives untrusted UDP datagrams and must not assume source legitimacy.
- Listener to parser: bytes become text and structured fields; malformed input must fail safely.
- Parser to normalizer: parsed fields become SIEM event fields; schema and semantic validation are required.
- Normalizer to Flask ingest route: only normalized events should cross into the centralized ingest path.
- Flask ingest route to database: validated events become durable records.
- Database to detection engine: stored event data can influence alerts and downstream response.
- Detection engine to SOAR: alerts can trigger playbooks and response workflows.
- SOAR to dashboard: runtime outcomes are exposed to analysts and operators.

## 4. Threat Enumeration

### Network

- spoofed UDP packets
- unexpected source IPs
- packet flooding
- denial of service
- malformed packets

### Parser

- malformed filterlog
- malformed UTF-8
- oversized packets
- parser crashes
- parser exceptions
- parser resource exhaustion

### Application

- schema violations
- invalid normalization
- log poisoning
- alert poisoning
- database growth
- duplicate ingestion
- replay

### Operational

- Azure NSG misconfiguration
- VM firewall misconfiguration
- Git/VM deployment drift
- service failures
- configuration drift

### Privacy

- storing unnecessary raw logs
- retaining business metadata longer than required

## 5. Required Mitigations

### Network

- Azure NSG allow-list
- optional VM firewall defense-in-depth
- expected pfSense source validation

### Listener

- packet size limits
- timeout handling
- malformed packet rejection
- UTF-8 safety
- control-character stripping
- rate limiting

### Parser

- never crash
- fail closed
- reject invalid records
- structured parse errors

### Pipeline

- schema validation
- normalized events
- no direct DB writes
- centralized ingest path

### Operations

- deployment checklist
- runtime validation
- health checks
- monitoring
- logging

## 6. Explicit Non-Goals

This parent roadmap intentionally does not include the following unless future requirements justify them:

- TLS syslog
- mutual TLS
- VPN transport
- IPSec tunnels
- HA clustering
- distributed collectors

## 7. Security Principles

Future pfSense child specs must preserve these principles:

- least privilege
- defense in depth
- fail safely
- centralized validation
- explicit trust boundaries
- no hidden assumptions
- source-of-truth architecture
- reproducible deployment
- auditable runtime behavior

## 8. Child Spec Guidance

Every future pfSense child spec must inherit this threat model.

Child specs should reference this document instead of redefining shared threats and mitigations. Each child spec should describe only implementation-specific behavior, such as exact parser rules, listener service flags, route validation, deployment commands, or test cases.

Required child-spec behavior:

- Identify which threats from this model the child spec touches.
- State which mitigations from this model the child spec implements.
- Include explicit acceptance criteria for those mitigations.
- Include validation steps that prove the mitigation works.
- Preserve the Mac source-of-truth and VM deployment/runtime-only boundary.

