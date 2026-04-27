# SIEM Security Dashboard

## Overview

This project is a full-stack Security Information and Event Management (SIEM) system built to ingest, analyze, and surface security events from external applications.

It is designed as a portfolio-grade security operations platform with:
- event ingestion
- detection rules
- alert generation
- analyst workflows
- incident report export
- role-based access control

---

## What This Project Does

The SIEM service is responsible for:

- accepting event ingestion requests on `/ingest`
- validating and storing events in PostgreSQL
- running detection rules against ingested activity
- generating and tracking alerts
- exposing backend endpoints for monitoring and alert management
- serving the frontend dashboard for reviewing alerts and event activity

Current detection coverage includes:

- failed login threshold detection
- port scan detection
- password spraying detection
- successful login after password spray correlation

---

## Deployment Model

This project is intended to run as a small full-stack deployment with:

- a Flask backend
- a PostgreSQL database
- a React frontend
- an external application that can forward security-relevant events into the SIEM

The exact deployment environment, host layout, process manager, reverse proxy, and infrastructure details should be configured per environment and kept out of the public repository.

---

## High-Level Architecture

- External application → SIEM ingestion API
- SIEM ingestion API → event storage
- Detection rules → alerts
- Alerts → analyst dashboard, reports, and response workflows

---

## Frontend Dashboard

The frontend dashboard provides visibility into:

- current alerts
- alert severity
- event activity
- top source IPs
- timelines and security trends
- geographic enrichment on mapped alerts
- MITRE ATT&CK context in alert details and reports

The dashboard also includes administration features for authorized roles, such as:

- user management
- audit log review
- role changes
- password resets

---

## Repository Structure

```text
siem-security-dashboard/
├── frontend/                  # React frontend source
├── docs/                      # design/spec notes
├── openspec/                  # implementation specs and proposals
├── schema.sql                 # PostgreSQL schema
├── siem_backend.py            # active backend entrypoint
├── simulate_attacks.py        # local testing helper
└── README.md
```

Notes:
- `siem_backend.py` is the primary backend entrypoint in this repo
- `schema.sql` defines the core PostgreSQL schema
- older backup or legacy files should be reviewed separately during cleanup

---

## Local Development

Typical local setup includes:

```bash
cd /path/to/project
source venv/bin/activate
export $(grep -v '^#' .env | xargs)
python3 siem_backend.py
```

Use your own local configuration values and secrets. Do not commit local environment files.

---

## Security Notes

This repository should not include:

- passwords
- API keys
- secret keys
- raw `.env` contents
- private deployment commands
- internal infrastructure hostnames or IPs
- private key filenames or paths

If you are preparing the repo for public release:

- keep `.env` local only
- avoid committing logs, dumps, or local artifacts
- keep secrets environment-driven rather than hardcoded
- keep deployment scripts and infrastructure-specific runbooks private

---

## Future Improvements

Potential next improvements include:

- stronger env/config standardization
- broader detection coverage
- cleaner deployment abstraction
- additional threat intelligence integrations
- improved operator and analyst workflows

---

## Creator

your-user
