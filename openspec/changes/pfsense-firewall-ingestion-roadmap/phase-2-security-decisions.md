# Phase 2 Security Decisions

Date: 2026-07-07

This file is a short decision record for future child specs. The full live VM audit findings are in `phase-2-security-review.md`.

## Decisions

1. Do not modify or repurpose rsyslog for pfSense ingestion.
2. Leave UDP 514 unused/reserved unless pfSense cannot send to a custom port.
3. Prefer a high unprivileged UDP listener port such as 5514.
4. If UDP 514 is required, document the privilege/capability plan before implementation.
5. Azure NSG is the primary network allow-list layer.
6. Do not open Azure NSG until listener implementation exists and local synthetic packet tests pass.
7. Eventual Azure NSG source should be restricted to expected pfSense public IP if possible.
8. Do not use `Any` source unless explicitly accepted as a temporary test exception with cleanup/removal task.
9. Do not assume VM-local firewall protection; UFW is inactive and INPUT policy is ACCEPT.
10. Consider VM firewall rules only as later defense-in-depth.
11. Do not make fail2ban a prerequisite.
12. Application-level validation and rate limiting are required.
13. Validate sender source IP against an allow-list before parsing/ingest.
14. Reject unexpected senders before parsing and avoid storing full attacker-controlled payloads.
15. Start with a 4096-byte UDP packet limit unless later implementation audit justifies another value.
16. Malformed syslog, malformed UTF-8, oversized packets, and unsafe control characters must not crash the listener.
17. Prefer normalized firewall event storage over raw full-payload retention.
18. Store pfSense logs on the Azure VM in the SIEM PostgreSQL database.
19. Tell uncle where logs are stored and what logs are being sent before requesting pfSense configuration.
20. Do not request uncle/pfSense configuration until all runtime readiness gates pass.

## Runtime Readiness Gates

Do not request pfSense configuration until all of these are true:

- listener deployed
- selected UDP port open only to allowed source
- synthetic packet test passed
- parser test passed
- normalized event appears in DB/dashboard
- backend health passes
- listener service health/logging passes
- rejection tests pass
- deployment checklist complete

