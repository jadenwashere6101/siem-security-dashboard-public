## Why

The parser/normalizer, ingest route, and UDP listener daemon child specs define the code path for pfSense firewall log ingestion, and the detections/SOAR child spec will define alerting behavior. None of those specs cover how the finished pieces get deployed to the Azure VM, verified end-to-end with synthetic traffic, or safely handed off to the uncle's pfSense configuration. This child spec defines that deployment, runtime-validation, and production-readiness contract without implementing, deploying, or exposing anything now.

## What Changes

- Add a non-code, deployment/readiness child spec for `pfsense-deployment-runtime-readiness` (Phase 3 item 6.12).
- Define the deployment sequence: GitHub sync check, VM sync check, clean git verification on both sides, migration check/apply, service restart order (backend, then workers, then listener), and backend/worker/listener verification.
- Define the infrastructure sequence: Azure NSG deployment gating, VM firewall decision, UDP port confirmation, operator-controlled service installation, required environment variables, and a rollback plan per component.
- Define runtime validation: synthetic packet testing, parser verification, ingest verification, database verification, dashboard verification, alert verification, playbook verification, approval verification, logging verification, and failure-path verification (malformed, oversized, unauthorized source, rate-limited, backend failure).
- Define production readiness: operator checklist, monitoring checklist, health checks, rollback criteria, success criteria, and an explicit deployment sign-off gate.
- Define pfSense handoff: information required from the uncle, expected public IP confirmation, remote syslog configuration guidance, and a final production enablement checklist.
- Keep this child scope deployment/runtime-readiness only: no parser implementation, ingest implementation, UDP listener implementation, detection implementation, SOAR implementation, firewall rule implementation, Azure NSG creation, live deployment, or production traffic.

## Capabilities

### New Capabilities

- `pfsense-deployment-runtime-readiness`: deployment sequencing, infrastructure gating, runtime validation, production-readiness checklist, and pfSense handoff contract for the pfSense firewall log ingestion path.

### Modified Capabilities

- (none)

## Impact

- **Affected code later:** none expected beyond deployment helper scripts or systemd/environment documentation not already covered by the parser, ingest-route, or listener child specs. No parser, route, detection, or SOAR logic changes.
- **Affected systems now:** none. This spec creation does not modify application source files, create tests, touch the VM, open ports, create Azure NSG rules, or deploy anything.
- **Dependencies:** depends on `pfsense-filterlog-parser-normalizer`, `pfsense-ingest-route-pipeline`, `pfsense-udp-listener-daemon`, and `pfsense-firewall-detections-soar` for the code path being deployed and for alert/playbook verification scope.
- **Parent roadmap:** item 6.12 is marked created with a deployment/runtime-readiness-only boundary note.
