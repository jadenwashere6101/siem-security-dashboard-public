## Context

The pfSense integration is split across code specs (parser/normalizer, ingest route, UDP listener daemon, and a future detections/SOAR spec) and this deployment/runtime-readiness spec. The code specs each explicitly exclude deployment, Azure NSG, VM firewall, live exposure, and uncle/pfSense handoff. Those excluded topics belong here.

This spec assumes the Mac repo remains the source of truth and the Azure VM remains deployment/runtime only, per the parent roadmap guardrails. It assumes no Azure NSG rule or VM firewall rule exists yet for the pfSense listener port, and that no live pfSense traffic has been sent. The detections/SOAR child spec (Phase 3 item 6.11, `pfsense-firewall-detections-soar`) has also been created; where readiness checks depend on detection/playbook behavior, this spec documents the check and defers execution until that spec's behavior is implemented.

## Goals / Non-Goals

**Goals:**

- Define the exact deployment sequence and verification steps for syncing code from GitHub to the VM and restarting affected services in a safe order.
- Define the infrastructure gating sequence for Azure NSG, VM firewall, UDP port confirmation, service installation, and required environment variables.
- Define a rollback plan for each deployed component (backend, workers, listener, NSG rule).
- Define the runtime validation procedure using synthetic pfSense packets to exercise the listener, parser, ingest route, database, dashboard, detections, playbooks, and approval gates end to end.
- Define production-readiness checklists (operator, monitoring, health checks) and explicit rollback/success criteria with a sign-off gate.
- Define what is needed from the uncle, how the expected public IP is confirmed, and the final pfSense-side configuration guidance.

**Non-Goals:**

- No parser, ingest route, UDP listener, detection, or SOAR implementation or redesign.
- No firewall rule implementation, Azure NSG rule creation, or VM firewall rule creation.
- No live deployment execution, service installation, or service restart performed by this spec-creation task.
- No production traffic collection or uncle/pfSense handoff performed by this spec-creation task.

## Decisions

1. Deployment sequence is sync-first, restart-in-dependency-order.

   Verify GitHub is up to date and the Mac repo is clean before touching the VM. Verify the VM repo is clean, then fetch/merge to match `origin/main`. Apply pending migrations before restarting any service that depends on schema changes. Restart order is backend first, then playbook/response-action workers, then the pfSense listener daemon, so that downstream consumers of a restart are available before upstream producers resume sending events.

2. Infrastructure changes are gated behind local validation, not the other way around.

   Azure NSG rule creation happens only after the listener is deployed on the VM and passes local synthetic packet testing on the VM itself (loopback or VM-local test traffic), consistent with the parent roadmap's Phase 2 security decisions. VM firewall rules remain an optional defense-in-depth decision, not a hard requirement, and must be explicitly recorded either way. The exact UDP listener port must be reconfirmed before any NSG rule is created, since the parent roadmap and listener spec treat `5514` as a default pending final pfSense capability confirmation.

3. Service installation stays operator-controlled.

   Listener and worker service installation reuses the existing install-helper pattern (copy unit, `daemon-reload`, explicit enable/start) rather than auto-starting on checkout, matching the pattern already established for `soar-playbook-worker.service` and the listener daemon spec.

4. Runtime validation uses synthetic traffic only.

   All parser, ingest, database, dashboard, alert, playbook, and approval verification in this spec is performed with synthetic/local test packets, not live pfSense traffic. Live traffic remains blocked until every runtime validation and production-readiness gate passes and sign-off is recorded.

5. Rollback is defined per component, before deployment, not improvised during an incident.

   Each deployed component (backend, workers, listener service, and any Azure NSG rule) has an explicit rollback action: service stop/disable, prior-version redeploy, or NSG rule removal. Rollback criteria are tied to observable failure conditions (health check failure, error-rate threshold, listener crash loop) rather than left to operator judgment alone.

6. Production sign-off is an explicit gate, separate from "tests pass."

   Deployment sign-off requires the operator checklist, monitoring checklist, and all runtime validation scenarios to pass together, and is recorded before any uncle/pfSense handoff communication is drafted or sent.

7. pfSense handoff information is minimal and confirmed, not assumed.

   The information requested from the uncle is limited to what pfSense needs to send logs (expected public source IP, confirmation pfSense can target the confirmed listener port, and remote syslog server target). The handoff checklist does not proceed until the expected public IP is confirmed and the receiving side (Azure NSG, listener) is already deployed and validated.

## Risks / Trade-offs

- [Risk] Restarting services out of order could drop events or cause the listener to forward to a backend that is not yet ready -> Mitigation: fixed restart order (backend, workers, listener) with per-service health verification before proceeding to the next.
- [Risk] Opening Azure NSG before validation increases exposure -> Mitigation: NSG creation is explicitly gated behind local VM-side synthetic validation and port/IP confirmation.
- [Risk] Uncle configures pfSense before our side is ready, causing lost or unparsed logs -> Mitigation: handoff checklist requires deployment sign-off before any handoff message is sent.
- [Risk] Rollback steps improvised during an incident increase downtime -> Mitigation: rollback plan and criteria are defined in this spec ahead of any deployment.
- [Risk] Detections/SOAR spec (6.11) implementation may lag this spec's creation -> Mitigation: alert/playbook/approval verification requirements are defined now but scoped to "verify existing/available behavior," so they can be exercised incrementally as 6.11 is implemented.

## Open Questions

- Final UDP listener port confirmation from pfSense capability (`5514` vs `514`) before any Azure NSG rule is created.
- Confirmed expected pfSense public IP for the NSG source restriction and listener allow-list.
- Whether VM firewall defense-in-depth rules will be added in addition to Azure NSG restriction.
- Exact scope of alert/playbook verification once `pfsense-firewall-detections-soar` is created.
