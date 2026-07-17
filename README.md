# SIEM Security Dashboard

A full-stack SIEM/SOAR platform built around detection engineering, analyst
workflow, and realistic security operations behavior.

This project ingests telemetry from web apps, Azure Application Insights,
honeypot services, OpenTelemetry sources, and pfSense firewall logs; detects and
correlates suspicious behavior; creates alerts and incidents; runs approval-gated
SOAR playbooks; tracks notification delivery and response outcomes; and exposes a
React analyst console built around real SOC workflows.

It is built to show how a small SOC platform should actually behave, not just how
it should look in a dashboard demo. The repository models bounded ingest
pipelines, explainable detections, analyst-facing evidence, recon aggregation,
incident gating, approval boundaries, guarded integrations, failure handling, and
auditability.

## Why This Project Stands Out

- Detection logic is treated as product behavior, not just a list of rules.
- The analyst experience is coherent end to end: alerts, incidents, recon
  activities, approvals, playbooks, and source context all share the same backend
  evidence model.
- The SOAR layer is intentionally safety-aware, with approvals, retry paths,
  idempotency, dead-letter handling, and guarded integrations.
- pfSense support goes beyond basic port-scan alerts with target evidence,
  distributed recon aggregation, and allow-after-deny progression tracking.

## Tech Stack

- Backend: `Flask`, `PostgreSQL`, `psycopg2`
- Frontend: `React`, Create React App
- Integrations: Slack, Teams, email, webhook, Azure Function
- Detection/SOAR: custom detection engine, correlation engine, playbook engine,
  worker daemon, approval workflow, notification policy service
- Development process: OpenSpec-driven design and implementation

## Screenshots

### SOC Command Center

![SOC Command Center overview](screenshots/soc-command-center-overview.png)

The Command Center gives a reviewer one screen that proves this is a real SOC
workflow: incident pressure, approval load, automation health, notification
posture, and live recon triage all in one place.

### Alert Investigation

![Alert investigation with target context](screenshots/alert-investigation-target-context.png)

This alert view shows that detections are written for analysts, not just engines:
plain-English reasoning, target evidence, reputation context, and a concrete
progression story are all visible without reading backend logic.

### Distributed Internet Reconnaissance Activity

![Distributed reconnaissance activity detail](screenshots/distributed-recon-activity-detail.png)

This recon workspace shows the platform turning noisy internet scanning into a
single investigation object, with compact triage on the left and a bounded
campaign-style summary on the right.

### Incident Workspace

<table>
  <tr>
    <td width="50%">
      <img src="screenshots/incident-workspace-response-context-incident.png" alt="Incident workspace detail" />
    </td>
    <td width="50%">
      <img src="screenshots/incident-workspace-response-context-playbook.png" alt="Incident-linked playbook execution detail" />
    </td>
  </tr>
</table>

Together these panels show the handoff from detection to action: the incident
explains why the case matters, and the paired response view shows the guarded
playbook execution path behind that investigation.

### Approval Workflow

![Approval workflow detail](screenshots/approval-workflow-detail.png)

This approval detail makes the safety model obvious: disruptive actions stay
human-gated, reviewers get the operational context they need, and every outcome is
auditable.

### Playbook Execution Timeline

<table>
  <tr>
    <td width="50%">
      <img src="screenshots/playbook-execution-timeline-detail.png" alt="Playbook execution outcome detail" />
    </td>
    <td width="50%">
      <img src="screenshots/playbook-execution-timeline-steps.png" alt="Playbook execution step timeline" />
    </td>
  </tr>
</table>

These execution views show that SOAR behavior is real and inspectable, with both a
clear outcome summary and the step-by-step path the system followed to get there.

### Detection Rules And Severity Philosophy

<table>
  <tr>
    <td width="50%">
      <img src="screenshots/detection-rules-and-severity-matrix.png" alt="Severity and response matrix" />
    </td>
    <td width="50%">
      <img src="screenshots/detection-rules-runtime-table.png" alt="Runtime detection rules table" />
    </td>
  </tr>
</table>

These views make the detection philosophy visible in the product itself: severity
means something operationally, incident behavior is documented, and rule metadata
is available without digging through source code.

## What It Does

At a high level, the platform:

1. Ingests normalized security telemetry through source-specific and generic APIs.
2. Stores events in PostgreSQL and evaluates detections and correlations.
3. Creates enriched alerts with MITRE, reputation, target evidence, and
   workflow metadata.
4. Creates incidents only when the activity is operationally actionable.
5. Starts SOAR playbooks after commit, outside the ingest transaction.
6. Routes notification attempts through a centralized notification policy.
7. Tracks approvals, queue state, execution outcomes, dead letters, and audit
   evidence across the analyst workflow.

## Current Architecture

```text
Telemetry sources
  -> source-specific ingestion routes / adapters
  -> PostgreSQL events
  -> detection engine
  -> correlation engine
  -> enriched alerts
  -> incident creation / linking
  -> SOAR playbook orchestration
  -> worker daemon, approvals, queue, outcomes, dead letters
  -> notification policy routing
  -> React analyst console
```

### Backend

- `Flask` backend exposing ingest, alerting, incident, approval, playbook,
  notification, metrics, source-context, and admin workflows
- `PostgreSQL` as the system of record for events, alerts, incidents,
  approvals, playbook executions, notification attempts, response outcomes, and
  recon aggregates
- additive migrations plus a schema snapshot in `schema.sql`

### Frontend

- single React application with dedicated workspaces for:
  - Dashboard
  - Alerts
  - Incidents
  - Recon Activities
  - Approvals
  - Playbooks
  - SOAR queue and dead letters
  - Notification Policy
  - Severity & Response Matrix
  - Source Health
  - Threat Hunt
  - Response Registry

### Detection Pipeline

- source-specific normalization and ingest filtering where needed
- durable event persistence before downstream alerting depends on it
- detector families in `engines/detection_engine.py`
- targeted and cross-source correlation in `engines/correlation_engine.py`
- backend-owned enrichment for MITRE, reputation, target evidence, and bounded
  correlation context

### Incident Workflow

- alerts carry operational flags that determine incident, containment, aggregate,
  and notification eligibility
- incidents are created for actionable work, not for every medium alert or
  commodity scan
- alert and incident lifecycles stay distinct but linked

### SOAR

- post-commit playbook orchestration
- daemonized worker with leases, stale recovery, bounded batches, and worker
  heartbeat support
- playbook execution records, step logs, notification steps, approval pauses,
  and canonical response outcomes

### Notification Policy

- centralized policy for minimum severity, alert vs incident routing, Slack
  enablement, and per-source destinations
- pfSense and honeypot route independently
- aggregate recon notifications use the same policy path instead of a parallel
  system

### Response Approvals

- approval-gated handling for disruptive actions such as `block_ip`
- explicit decision records, expiry handling, and linked queue / incident /
  source context
- no autonomous containment path for pfSense progression or commodity recon

### Severity Model

- severity is intentionally conservative
- `critical` is reserved for likely-compromise behavior such as successful
  authentication after password spraying
- pfSense detections do not escalate to `critical`
- reputation strengthens evidence but does not independently justify the most
  severe outcomes for commodity scanning

## Detection And Analysis Capabilities

This repository contains more rules than are useful to list in a README. The
important part is the detection model.

### Firewall And Perimeter Detection

- pfSense repeated deny detection for blocked activity
- pfSense port-scan detection with richer target evidence and human-readable
  scan descriptions
- pfSense suspicious allow detection for inbound access to sensitive services
- pfSense noisy-source suppression rollups for operational visibility without
  overstating severity

### Distributed Reconnaissance Analysis

- durable `Distributed Internet Reconnaissance Activity` aggregation for
  many-source commodity scanning
- membership based on protected-range overlap, service-signature overlap, and
  bounded time overlap
- preserved underlying alerts plus one analyst-facing investigation object
- aggregate-level notification deduplication and material-change handling

### Allow-After-Deny Progression

- `pfsense_firewall_allow_after_deny` detects same-source inbound progression
  from repeated denies to a later allow
- bounded 30-minute window
- medium/high severity based on progression strength, target exactness, and
  corroboration
- source-specific incident and approval path when justified

### Azure Telemetry Support

- Azure Application Insights polling through `siem-azure-function/`
- checkpoint-based polling with bounded fallback windows
- normalization of request, exception, dependency-failure, and availability
  telemetry into the same backend ingestion model as other sources

### Cross-Source Correlation

- correlated activity across distinct sources
- targeted correlations such as web-to-app attack patterns, spray-then-success,
  cloud/app error patterns, and Azure auth abuse plus exception correlations

### Reputation And MITRE

- external reputation snapshots and internal behavioral reputation support
- reputation influences prioritization and enrichment but is not treated as a
  standalone substitute for observed behavior
- MITRE ATT&CK mapping is attached to relevant alerts for analyst context and
  reporting

## SOAR And Response Model

### Approval Workflow

- approvals are first-class operational objects
- queue items, approvals, incidents, and outcomes stay linked but distinct
- reviewers can inspect decision state directly instead of inferring it from
  alert status alone

### Response Outcomes

- response actions produce canonical outcome records
- the platform distinguishes real execution, simulation, tracking-only,
  blocked, pending, and failed outcomes
- that matters because "a playbook ran" is not the same thing as "a real
  containment action executed"

### Notification Routing

- centralized notification policy controls whether alerts or incidents notify
- Slack delivery attempts are tracked durably
- deduplication, blocked deliveries, and route-test behavior are visible to the
  platform rather than hidden in integration code

### Slack Notification Policy

- per-source routing for pfSense, honeypot, and critical cross-source cases
- minimum severity enforcement
- aggregate pfSense recon notifications open once when eligible and update only
  on material aggregate change
- individual commodity-recon member alerts do not flood Slack independently

### Response Actions

- `monitor`, `flag_high_priority`, notifications, and approval-gated
  `block_ip` workflows are represented in the platform
- firewall-style blocking remains intentionally guarded and dry-run oriented in
  this public repository
- the project is designed to demonstrate response discipline, not reckless
  autonomous enforcement

## Azure Architecture

Azure support in this repository is real and implemented, but intentionally
scoped.

### Application Insights Ingestion Design

- Azure polling is handled by a dedicated Azure Function under
  `siem-azure-function/`
- the function queries Application Insights / Log Analytics for bounded windows
  of telemetry
- forwarded events are normalized into the same backend ingestion contract used
  by the rest of the platform

### Checkpoint-Based Polling

- the Azure Function reads and writes a checkpoint through backend endpoints
- bounded fallback windows prevent unbounded re-polling when checkpoint data is
  missing or invalid
- retry behavior exists for both telemetry query and forward steps

### Unified Azure Ingestion Pipeline

- Azure request failures, application exceptions, dependency failures, and
  availability failures are normalized into one SIEM pipeline
- once ingested, they participate in the same enrichment, correlation, incident,
  and SOAR model as other telemetry sources

Unfinished Azure work is intentionally not claimed here. This README only
describes the Application Insights architecture currently present in the
repository.

## Analyst Experience

### Alerts

- searchable alert list
- alert details with severity, MITRE, reputation, and response context
- additive pfSense target context instead of forcing analysts to parse raw text

### Recon Activities

- compact list/detail workflow for distributed commodity recon
- source counts, destination counts, primary ports, coordination status, and
  assessment text

### Incidents

- linked alerts, timeline context, assignments, status changes, and analyst
  workflow continuity

### Approvals

- pending approval review with linked incident, queue, and source-IP context
- explicit approve/deny handling and notification visibility

### Playbooks

- execution history
- execution timeline
- approval-paused states
- outcome evidence

### Source Health

- source-level operational status for telemetry visibility and troubleshooting

### SOC Command Center

- incident pressure
- automation state
- pending approvals
- dead-letter pressure
- notification health
- worker health
- recon activity visibility

### Threat Hunting

- direct event exploration and investigative pivoting

### Target Context

- primary destination IP/port
- bounded sample destinations
- distinct host and port counts
- human-readable scan descriptions
- related-event path for deeper inspection

## Repository Structure

```text
siem-security-dashboard-public/
├── adapters/                 # Source-specific telemetry adapters
├── core/                     # Stores, auth, audit, DB helpers, SOAR support
├── docs/                     # Runbooks, architecture notes, handoffs
├── engines/                  # Detection, correlation, ingest, SOAR worker/executor logic
├── frontend/                 # React analyst console
├── helpers/                  # Shared enrichment and utility code
├── integrations/             # Guarded adapter integrations
├── migrations/               # PostgreSQL migrations
├── openspec/                 # Spec-driven design history
├── routes/                   # Flask APIs and ingest routes
├── scripts/                  # Worker, migration, and deploy helpers
├── siem-azure-function/      # Azure Function for Application Insights polling
├── tests/                    # Backend test suite
├── schema.sql                # Schema snapshot
└── siem_backend.py           # Flask app entrypoint
```

## Key Files

- Backend entrypoint: `siem_backend.py`
- Frontend entrypoint: `frontend/src/App.js`
- Detection engine: `engines/detection_engine.py`
- Correlation engine: `engines/correlation_engine.py`
- Severity model projection: `engines/severity_response_matrix.py`
- Notification policy service: `core/notification_policy_service.py`
- Recon aggregate store: `core/recon_activity_store.py`
- SOAR worker daemon: `engines/soar_playbook_worker.py`
- Playbook step executor: `engines/playbook_step_executor.py`
- Azure Function poller: `siem-azure-function/function_app.py`

## Local Development

Backend:

```bash
source venv/bin/activate
set -a
source .env
set +a
python3 siem_backend.py
```

Frontend:

```bash
cd frontend
npm install
npm start
```

Focused verification:

```bash
python3 -m pytest

cd frontend
CI=true npm test -- --watchAll=false
npm run build
```

## Engineering Approach

The project uses spec-driven development through OpenSpec artifacts stored under
`openspec/`.

That matters because the repository was not grown as an ad hoc demo. Major
workflow changes such as notification policy routing, pfSense recon analysis,
Azure ingestion, SOAR reliability, and analyst workspace behavior were designed
before implementation and verified afterward.

## Security And Scope Notes

This public repository does not include secrets, live credentials, or production
environment values.

The project intentionally avoids claiming live destructive enforcement. In this
codebase, simulation, tracking-only, approval-gated, blocked, and real-capable
states are differentiated explicitly because that distinction matters in real
security operations.

## Intentionally Not Documented In Detail

- every individual detection rule
- private deployment configuration
- production secrets, guard values, or webhook destinations
- unfinished roadmap items that are not already implemented in the repo
- VM-only operational procedures beyond referencing their docs

## Creator

Jaden Gomez
