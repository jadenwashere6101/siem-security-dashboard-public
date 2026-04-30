# SIEM Security Dashboard

  ## Overview

  This project is a full-stack **Security Information and Event Management (SIEM)** platform
  built to simulate realistic **SOC (Security Operations Center)** workflows.

  It ingests security events from external applications, analyzes them in real time, applies
  detection logic, generates alerts, and provides a dashboard for analysts and
  administrators.

  This system demonstrates:

  - detection engineering
  - backend system design
  - secure API development
  - role-based access control (RBAC)
  - incident response workflows
  - full-stack system integration

  ---

  ## Repo Map

  Quick navigation for contributors and AI agents:

  - Backend entrypoint: `siem_backend.py` (main Flask app)
  - Frontend: `frontend/src/App.js`
  - Frontend alerts UI: `frontend/src/components/AlertsTable.js`
  - Azure adapter: `adapters/azure_insights_adapter.py`
  - Nginx adapter: `adapters/nginx_adapter.py`
  - OpenTelemetry adapter: `adapters/otel_adapter.py`
  - Azure Function: `siem-azure-function/function_app.py`
  - Log file ingestion script: `scripts/ingest_log_files.py`
  - Attack simulation script: `simulate_attacks.py`
  - Demo alert script: `demo_alerts.sh`
  - Deployment script: `deploy.sh`
  - Azure setup/demo guide: `docs/azure-integration-setup.md`
  - Azure timer debug guide: `siem-azure-function/AZURE_TIMER_DEBUG.md`
  - Feature specs: `openspec/changes/`

  ---

  ## Real-World Integration

  This SIEM is designed to integrate with external applications that stream real-time
  security telemetry into the platform.

  - External systems send events to the `/ingest` API
  - Events are generated from authentication and user activity flows
  - The SIEM processes and analyzes these events in real time

  Example events include:

  - failed login attempts
  - successful logins
  - application activity events

  Detection coverage includes:

  - brute force attacks
  - password spraying attacks
  - account compromise scenarios such as successful login after spraying

  Example pipeline:

  **External App → SIEM `/ingest` API → Event Storage → Detection Engine → Alerts →
  Dashboard / Map / Reports**

  This reflects a centralized monitoring architecture commonly used in modern security
  operations.

  ---

  ## Tech Stack

  ### Backend
  - Python (Flask)
  - PostgreSQL
  - Flask-Limiter
  - ReportLab

  ### Frontend
  - React

  ### Security Concepts
  - API key authentication
  - role-based access control (RBAC)
  - input validation and defensive programming
  - rate limiting
  - audit logging
  - secure session handling

  ---

  ## Core Features

  ### Event Ingestion API

  - Endpoint: `/ingest`
  - Accepts JSON security events from external systems
  - Protected via `X-API-Key`
  - Strict validation before database insertion
  - Automatic geo-enrichment when location data is missing

  Required fields:

  - `event_type`
  - `severity`
  - `message`
  - `source_ip`
  - `app_name`
  - `environment`

  Protections include:

  - strict input validation
  - required field enforcement
  - rejection of invalid values
  - rate limiting

  ---

  ### Detection Engine

  Real-time detection and correlation logic includes:

  - failed login threshold detection
  - port scan detection
  - password spraying detection
  - successful login after spray correlation
  - duplicate alert suppression

  This includes multi-stage correlation, not just simple thresholds.

  ---

  ### Detection Rule Management

  Detection rule parameters can be reviewed and tuned through the administration workflow.

  - rule thresholds and windows are centrally managed
  - validation enforces safe parameter values
  - rule changes are audit logged
  - defaults remain available as a fallback path

  This models the kind of detection-tuning workflow used in real-world security teams.

  ---

  ### Alerting System

  - alerts generated from detection rules
  - severity, source IP, timestamps, and descriptive message
  - status tracking such as `open` and `resolved`
  - duplicate alert prevention

  ---

  ### Enrichment & Intelligence

  - IP geo-enrichment
  - MITRE ATT&CK mapping
  - threat context on alerts
  - PDF incident report generation

  Example mappings:

  - `T1110` – Brute Force
  - `T1110.003` – Password Spraying
  - `T1046` – Network Service Discovery

  ---

  ### Dashboard

  The frontend dashboard includes:

  - real-time alerts table
  - severity distribution
  - event trends
  - top source IPs
  - geographic visualization
  - filtering and sorting
  - MITRE ATT&CK context display

  ---

  ### Threat Hunting

  The platform also includes proactive event-hunting workflows:

  - search raw ingested events
  - filter by source IP, event type, and time window
  - inspect raw payload details
  - pivot from events to related alerts

  ---

  ### Admin & RBAC System

  Roles:

  - `super_admin`
  - `analyst`
  - `viewer`

  Administrative capabilities include:

  - user management
  - role assignment
  - password resets
  - audit log access
  - detection rule review

  ---

  ### Audit Logging

  The platform tracks sensitive actions, including:

  - authentication events
  - administrative actions
  - alert response actions
  - detection rule changes

  Audit records capture who performed the action, what changed, and when it happened.

  ---

  ### Security Hardening

  - API key enforcement on ingestion
  - rate limiting on sensitive endpoints
  - strict backend validation
  - secure session handling
  - audit logging
  - defensive programming patterns

  ---

  ## Architecture

  **External App / Simulator**
  ↓
  **`/ingest`**
  ↓
  **Event Storage (PostgreSQL)**
  ↓
  **Detection Engine**
  ↓
  **Alerts**
  ↓
  **Dashboard / Map / Reports / Admin Actions**

  ---

  ## Repository Structure

  ```text
  siem-security-dashboard/
  ├── frontend/
  ├── openspec/
  ├── schema.sql
  ├── siem_backend.py
  ├── simulate_attacks.py
  └── README.md

  ———

  ## Spec-Driven Development

  This project uses a spec-first workflow:

  1. Define changes in openspec/
  2. Review before implementation
  3. Apply minimal, controlled updates
  4. Validate before deployment

  ———

  ## Local Development

  cd /path/to/project
  source venv/bin/activate
  set -a
  source .env
  set +a
  python3 siem_backend.py

  ———

  ## Security Notes

  This repository does not include:

  - secrets
  - API keys
  - passwords
  - raw .env values

  Best practices:

  - keep .env local only
  - use environment variables
  - never commit sensitive data
  - keep deployment-specific configuration private

  ———

  ## Future Improvements

  Potential future work includes:

  - more advanced correlation chains
  - behavioral detection logic
  - external threat intelligence integrations
  - enhanced analyst workflows
  - further UI/UX improvements

  ———

  ## Creator

  Jaden Gomez
