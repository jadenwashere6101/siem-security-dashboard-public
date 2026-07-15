# VM Handoff

Change: `improve-pfsense-recon-analysis-and-progression-detection`

Repository source of truth: `/Users/jadengomez/Projects/siem-security-dashboard-public`

Authoring-turn VM access: none. No implementation step in this Mac turn accessed the VM.

## Scope

- Additive migration `0023_recon_activities.sql`
- Backend severity/incident/notification/playbook updates for pfSense recon handling
- Frontend analyst surfaces for bounded recon activity inspection and richer Target Context
- No historical alert, incident, approval, or severity rewrite

## Migration 0023

Apply:

```bash
bash scripts/deploy_backend_vm.sh --dry-run-migrations
bash scripts/deploy_backend_vm.sh
```

Migration contents:

- creates `recon_activities`
- creates `recon_activity_alerts`
- adds `notification_delivery_attempts.recon_activity_id`
- adds supporting indexes

Migration expectations:

- additive only
- no backfill required
- no historical mutation

## Backend Deployment

Deploy only an explicitly approved Mac commit after VM clean-tree verification.

Production expectations after deploy:

- reputation alone no longer converts minimum-threshold commodity pfSense detections into `high`
- distributed commodity recon member alerts can enroll into one durable recon aggregate
- commodity aggregate members do not create one incident, approval, or Slack notification per source
- allow-after-deny progression remains source-specific and outside the commodity aggregate

## Frontend Deployment

After backend health is green, deploy the Mac-built frontend artifact.

Analyst-visible changes:

- Alert Details renders richer pfSense Target Context and aggregate linkage
- SOC Command Center shows bounded `Distributed Internet Reconnaissance Activity` summaries
- Severity & Response Matrix wording matches the new pfSense severity and response philosophy

## Playbook Reconciliation

Reconcile and verify the current core playbook pack on the VM so the deployed playbook definitions match the Mac source:

- `core-v1-pfsense-repeated-deny-investigation`
- `core-v1-pfsense-port-scan-investigation`
- `core-v1-pfsense-port-scan-containment`
- `core-v1-pfsense-suspicious-allow-containment`
- `core-v1-pfsense-allow-after-deny-investigation`
- `core-v1-pfsense-allow-after-deny-containment`

Verification goals:

- commodity port-scan and repeated-deny investigation behavior remains bounded
- source-specific High progression remains approval-gated
- no autonomous `block_ip`

## Operational Baseline Advancement

Do not set from Mac.

After successful deployment and smoke verification, VM AI should determine and apply the new pfSense tuning baseline timestamp so post-fix operations can be separated from pre-fix artifacts.

Baseline guidance:

- advance only once deployment is live and verified
- do not rewrite historical rows
- keep legacy artifacts visible under pre-tuning history

## Production Verification

Verify all of the following in production after deployment:

1. Migration `0023` applied cleanly and schema is current.
2. Backend health endpoint is green.
3. Frontend loads the recon activity surfaces without API errors.
4. Minimum-threshold commodity inbound pfSense scanning with high AbuseIPDB reputation no longer creates `high` by reputation alone.
5. Distributed commodity recon enrolls into one or a very small bounded number of `Distributed Internet Reconnaissance Activity` records by protected range and service overlap.
6. Aggregate member alerts remain preserved and viewable.
7. Commodity aggregate members do not create one P2 incident per source.
8. Commodity aggregate members do not create one `block_ip` approval per source.
9. Aggregate notifications open once when policy-eligible and do not re-notify without material change.
10. A source-specific allow-after-deny High case remains outside the commodity aggregate, can notify, and can create the approved incident path without automatic containment.

Recommended production checks:

- compare counts of new pfSense `high` alerts before and after rollout
- compare incident and approval creation volume for new pfSense alerts
- inspect `recon_activities` and `recon_activity_alerts` membership for deterministic grouping
- inspect `notification_delivery_attempts` rows for aggregate-level dedup behavior

## Rollback

Rollback target:

- revert to the previously approved application commit
- leave additive schema objects in place unless a separately approved rollback procedure requires otherwise

Rollback notes:

- `recon_activities` tables are additive and can remain unused if the application is rolled back
- do not delete historical alerts, incidents, approvals, aggregates, or delivery attempts during rollback
- if rollback is required after baseline advancement planning but before baseline application, do not advance the baseline

## VM Owner Checklist

- verify clean tree on VM
- sync only to the approved commit
- dry-run migrations
- deploy backend
- verify backend health
- deploy frontend build
- reconcile playbook definitions if required by repo deployment workflow
- run production smoke verification
- decide whether and when to advance the pfSense tuning baseline
- record sanitized before/after evidence
