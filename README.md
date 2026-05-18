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

  ## SOAR Demo and Productization Docs

  Current portfolio/demo guidance lives in:

  - SOAR docs index: `docs/soar_docs_index.md`
  - Demo walkthrough: `docs/soar_demo_walkthrough.md`
  - Demo reset guide: `docs/soar_demo_reset_guide.md`
  - Architecture summary: `docs/soar_architecture_summary.md`
  - Security boundaries: `docs/soar_security_boundaries.md`
  - Interview talking points: `docs/soar_interview_talking_points.md`
  - Final validation checklist: `docs/soar_final_validation_checklist.md`

  Operational references:

  - Worker daemon runbook: `docs/soar_playbook_worker_daemon_runbook.md`
  - Dead-letter validation: `docs/soar_dead_letter_validation.md`
  - Execution locking validation: `docs/soar_execution_locking_validation.md`
  - Slack smoke test: `docs/soar_slack_staging_smoke_test_runbook.md`
  - Teams smoke test: `docs/soar_teams_staging_smoke_test_runbook.md`
  - Email smoke test: `docs/soar_email_staging_smoke_test_runbook.md`
  - Webhook smoke test: `docs/soar_webhook_staging_smoke_test_runbook.md`

  Local Mac workflow is for development, tests, frontend build, and
  simulation-safe demos. VM deployment and runtime service changes are separate
  operator actions documented in the deployment/runbook references and should
  not be performed during a normal demo.

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

  Features were designed and documented before implementation using an OpenSpec-style
  workflow. Each change followed a structured process:

  1. A proposal defined the problem and intended solution.
  2. A spec detailed expected behavior and acceptance criteria.
  3. Implementation was performed against the spec, not open-ended.
  4. Completed changes were verified and archived.

  Specs are plain markdown files stored under `openspec/`. All 42 completed changes are
  archived in `openspec/changes/archive/`, covering the full feature set of the platform.

  AI-assisted development was used throughout, but scoped to individual specs rather than
  open-ended sessions. Each feature had defined requirements before any code was written.
  This kept the backend modularization phase controlled and prevented unscoped changes
  from accumulating.

  OpenSpec organized the planning process. It did not generate the code.

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
