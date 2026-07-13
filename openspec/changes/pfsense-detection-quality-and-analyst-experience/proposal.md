## Why

`pfsense-firewall-detections-soar` (implemented, not yet archived) shipped four pfSense rules — `pfsense_firewall_repeated_deny`, `pfsense_firewall_port_scan`, `pfsense_firewall_suspicious_allow`, `pfsense_firewall_noisy_source` — validated against synthetic/demo traffic. The SIEM has now received its first sustained real-world pfSense event stream. Two prior audits (detection-noise audit, operational-reliability audit) confirmed concrete problems this spec exists to fix:

- `pfsense_firewall_port_scan` fires on 2 distinct destination ports in 15 minutes — background internet scanning clears this constantly.
- `pfsense_firewall_suspicious_allow` fires on a single allowed event, always forced to `high` severity — no aggregation, no repetition requirement.
- `pfsense_firewall_repeated_deny` treats WAN→LAN scan noise and LAN→WAN traffic identically, missing the higher-value "possibly compromised internal host" signal.
- Alert dedup only checks for a currently-*open* alert per `(source_ip, alert_type)` — once closed, a still-active offender re-alerts immediately with no cooldown.
- Investigation-only playbooks (`monitor`-outcome) Slack analysts with the same urgency as containment playbooks.
- Analysts have no in-UI answer to "why did this fire," "is this rule currently noisy," or "has this source been suppressed."

This is a quality and experience problem, not a coverage gap: the goal is to make the four existing detections production-grade and make operating the SIEM during continuous traffic tractable for one analyst, not to add a large new detection surface.

## What Changes

- Re-tune aggregation *logic* (not just numeric thresholds — those are already live-editable via the existing `/admin/detection-rules/<rule_id>` override, out of band from this spec) for port-scan (add destination-host breadth, not port-count alone), repeated-deny (add WAN→LAN vs LAN→WAN direction split), and suspicious-allow (require repetition/context instead of single-event auto-`high`).
- Add a bounded post-close cooldown so a resolved alert's still-active source does not immediately regenerate a duplicate.
- Split notification behavior: investigation-only (`monitor`) outcomes stop paging Slack with containment urgency; containment outcomes are unaffected.
- Add analyst-facing "why this fired" context to alert detail, and a small detection-health surface (top-firing rules, recent noise, suppression counts), both sourced from data already stored on `alerts`/`audit_log` — no new tables assumed.
- Preserve all approval gates, SOAR architecture, ingest filtering, and the frozen response-action queue exactly as-is.

## Capabilities

### New Capabilities
- `pfsense-detection-quality-and-analyst-experience`: detection-logic quality, alert-lifecycle suppression, notification-severity mapping, and analyst investigation/health UX for the four existing pfSense rules.

### Modified Capabilities
- (none) — this spec does not modify `pfsense-firewall-detections-soar` or any other existing spec. It is a refinement layer on top of what that spec already implemented.

## Impact

- **Affected code later:** `engines/detection_engine.py` (four pfSense detector functions), `engines/detection_config.py` (rule metadata/description only, not the override mechanism), `core/core_playbook_pack_v1.py` (investigation-playbook notification steps only), a small number of new read-only route(s) for alert "why fired" context and detection health, corresponding frontend alert-detail and a new detection-health panel, and focused tests.
- **Affected APIs later:** additive, read-only endpoints only (alert investigation context, detection health/rule-hit metrics). No existing endpoint contract changes.
- **Affected systems now:** none. Writing this proposal/design/tasks/spec makes no changes under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`, does not touch the VM, and performs no runtime validation.
- **Dependencies:** builds on the already-implemented `pfsense-firewall-detections-soar` capability and the already-implemented `detection_config` override mechanism; does not depend on any unimplemented spec.
- **Migrations:** none assumed. One column (`alerts.resolved_at`) is flagged as a possible fallback in `design.md` if the no-migration cooldown approach (joining `audit_log`) proves insufficient at implementation time — not assumed here.
