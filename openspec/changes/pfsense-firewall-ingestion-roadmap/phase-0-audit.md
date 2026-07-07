# Phase 0 Read-only Environment Audit

Date: 2026-07-07

Scope: read-only Phase 0 audit for `pfsense-firewall-ingestion-roadmap`. No application source files were edited. No VM files or services were modified. No ports were opened. No commits or pushes were performed.

## Summary

- Mac repo is aligned with GitHub `origin/main`, but the working tree is not clean because there are uncommitted roadmap/policy files.
- VM working tree is clean, but VM Git history is not synced with current GitHub `main`.
- Backend health is OK.
- SOAR playbook worker is active.
- SOAR response action worker timer is active, with the one-shot service inactive after successful execution.
- UDP 514 is not listening and does not currently conflict.
- `rsyslogd` exists as a process, but it is not listening on UDP 514.
- Existing ingestion is HTTP/Flask route based; no raw syslog listener exists.
- Existing normalized ingestion and detection pipeline can be reused by a future child spec.

## Evidence

### Mac Repo Cleanliness

Mac command:

```bash
git status --short
git status -sb
git rev-parse HEAD
git rev-parse @{u}
git ls-remote origin refs/heads/main HEAD
```

Finding:

- Mac working tree is not clean due to uncommitted roadmap/policy files.
- Mac `HEAD`, local upstream, remote `HEAD`, and remote `refs/heads/main` all resolve to `af24fae54ad1a1c91e7e62c2d52921793fe42321`.

### VM Repo Sync

VM command:

```bash
cd /home/jaden/siem-security-dashboard
git status --short
git status -sb
git rev-parse HEAD
git rev-parse @{u}
git ls-remote origin refs/heads/main
```

Finding:

- VM working tree is clean.
- VM branch reports `main...origin/main [ahead 8]`.
- VM `HEAD` is `489e4ed4be2789e82709af77ccce84c6da930d45`.
- VM local upstream ref is `76ae5b54c2a1ad977045d8e2eed26ae1c6b379cd`.
- Current GitHub `origin/main` is `af24fae54ad1a1c91e7e62c2d52921793fe42321`.
- Do not run VM merge/deploy work until the VM divergence is intentionally handled.

### Backend Health

VM command:

```bash
curl -sS -m 5 -i http://127.0.0.1:5051/health
```

Finding:

- HTTP 200.
- Response body includes `"service": "siem_dashboard"` and `"status": "ok"`.

### Worker Services

VM command:

```bash
systemctl is-active siem-backend.service soar-playbook-worker.service soar-response-action-worker.timer soar-response-action-worker.service
systemctl --no-pager --plain status soar-playbook-worker.service soar-response-action-worker.timer soar-response-action-worker.service
```

Finding:

- `siem-backend.service`: active.
- `soar-playbook-worker.service`: active/running.
- `soar-response-action-worker.timer`: active/waiting.
- `soar-response-action-worker.service`: inactive/dead after last successful timer-triggered run.

### Listening Ports

VM command:

```bash
ss -H -tulpen
ss -H -lunp | grep -E '(^|[.:])514\b|:514\b'
ps aux | grep -Ei 'syslog|rsyslog|syslog-ng|udp.*514|514' | grep -v grep
```

Finding:

- TCP listeners observed: 22, 80, 443, 5051, 5052, 8080, local PostgreSQL 5432, local MySQL 3306/33060, local DNS 53.
- UDP listeners observed: local DNS 53, DHCP 68, chrony 323.
- No UDP 514 listener found.
- `rsyslogd` is running, but it is not listening on UDP 514.

### Existing Adapters And Listeners

Finding:

- Active adapter/ingest files are HTTP/normalizer based:
  - `routes/ingest_routes.py`
  - `engines/ingest_engine.py`
  - `adapters/nginx_adapter.py`
  - `adapters/azure_insights_adapter.py`
  - `adapters/otel_adapter.py`
  - `helpers/ingest_normalizers.py`
- No active raw UDP/syslog listener or pfSense/filterlog parser was found.

### Honeypot Pattern

Finding:

- Honeypot runtime listens separately on TCP 8080.
- Backend ingestion endpoint is `/ingest/honeypot`.
- Backend normalizes honeypot events with `source=honeypot`, `source_type=honeypot`, `app_name=flask_honeypot`, then calls `ingest_normalized_event`.
- This is the closest existing deployment pattern for an external runtime producer feeding normalized backend ingestion.

### Normalization And Detection Reuse

Finding:

- Reusable normalized ingestion path: `engines/ingest_engine.ingest_normalized_event`.
- Reusable validation/normalization patterns:
  - IP validation in `routes/ingest_routes.py` and adapter normalizers.
  - `helpers/ingest_normalizers.reject_raw_password_fields`.
  - Narrow adapter normalizer modules.
- Overlapping detections:
  - `port_scan` / `port_scan_threshold`
  - `failed_login` / `unauthorized_access` / `failed_login_threshold`
  - `http_error` / `http_error_threshold`
  - honeypot scanner/admin/env/credential-stuffing detections
  - correlated activity and targeted correlation

### Reusable Tests

Finding:

- Reusable backend tests:
  - `tests/test_ingest_api_contracts.py`
  - `tests/test_ingest_normalized_event.py`
  - `tests/test_port_scan_detection.py`
  - `tests/test_failed_login_detection.py`
  - `tests/test_honeypot_ingest_adapter.py`
  - `tests/test_honeypot_event_detections.py`
  - `tests/test_correlated_activity.py`
  - `tests/test_targeted_correlation.py`
- Reusable deployment/service tests:
  - `tests/test_deploy_backend_vm_script.py`
  - `tests/test_response_action_worker_deployment.py`

## Phase 0 Blockers For Later Phases

- VM is not synced with current GitHub `main`. Future deployment planning must resolve this before any VM merge or runtime sync.
- Phase 1 may proceed as architecture audit only, but implementation must remain blocked until VM divergence is handled and Phase 1 completes.

