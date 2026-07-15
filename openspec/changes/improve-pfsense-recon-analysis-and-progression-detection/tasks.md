## 1. pfSense Severity And Response Correction

- [x] 1.1 Audit and document the exact current pfSense detector severity paths in `engines/detection_engine.py` against this change’s contracts before editing code.
- [x] 1.2 Update `pfsense_firewall_repeated_deny` severity logic so inbound commodity scanning cannot become `high` from reputation alone and outbound/internal-host behavior remains the primary High path.
- [x] 1.3 Update `pfsense_firewall_port_scan` severity logic so `high` requires strong breadth or corroboration and reputation alone cannot elevate a base-threshold alert to `high`.
- [x] 1.4 Update `pfsense_firewall_suspicious_allow` severity logic so `high` requires repetition, multi-port corroboration, progression, or other approved supporting evidence rather than reputation alone.
- [x] 1.5 Confirm `pfsense_firewall_noisy_source` remains low-severity and suppression-focused under the new model.
- [x] 1.6 Update `engines/detection_config.py` rule metadata and descriptions so runtime rule documentation matches the new severity behavior.
- [x] 1.7 Update severity-facing backend projection code, including Severity Matrix inputs, so pfSense rule explanations reflect the new response philosophy and never claim `critical`.

## 2. Incident And Approval Noise Reduction

- [x] 2.1 Update automatic pfSense incident creation logic so low and medium pfSense alerts do not create incidents and distributed commodity recon does not create one incident per source.
- [x] 2.2 Define and implement aggregate-aware incident handling so qualifying distributed-recon member alerts can avoid per-source incident fan-out.
- [x] 2.3 Narrow pfSense containment eligibility so only source-specific actionable High behaviors can request approval-gated `block_ip`.
- [x] 2.4 Update core pfSense playbook trigger rules and descriptions in `core/core_playbook_pack_v1.py` to match the new incident and approval boundaries without bypassing approval gates.
- [x] 2.5 Preserve historical alerts, incidents, approvals, and existing lifecycle rows without rewriting or deleting them.

## 3. Distributed Recon Aggregation

- [x] 3.1 Implement the durable `Distributed Internet Reconnaissance Activity` persistence model and membership relationships using the minimal migration justified by this change.
- [x] 3.2 Define the protected-range key, service-signature key, aggregate status model, and coordination-status model for pfSense distributed reconnaissance.
- [x] 3.3 Implement aggregate enrollment logic that requires target-range and service overlap in addition to time overlap and excludes unrelated same-window activity.
- [x] 3.4 Exclude source-specific progression and containment behaviors from primary aggregate membership so the aggregate stays scoped to commodity distributed reconnaissance.
- [x] 3.5 Add additive read-only aggregate list and detail APIs exposing the required summary fields, linked incidents or approvals, and representative underlying alerts.
- [x] 3.6 Add additive alert-to-aggregate linkage so existing alert-detail and operational surfaces can link into the aggregate without hiding the underlying alert.

## 4. Target Evidence And Readable Descriptions

- [x] 4.1 Expand pfSense target-context snapshots with bounded exact-or-aggregate evidence fields, distinct counts, representative targets, timing, and related-event metadata.
- [x] 4.2 Implement deterministic sample selection for destination IPs and ports so bounded evidence is stable across renders and queries.
- [x] 4.3 Add a bounded related-event inspection path derived from stored evidence windows instead of persisting unbounded raw payloads on alerts or aggregates.
- [x] 4.4 Implement canonical backend-generated human-readable scan descriptions for host sweeps, port sweeps, and mixed-breadth scans with correct singular/plural grammar.
- [x] 4.5 Update pfSense alert APIs and read-only investigation payloads so structured target evidence and canonical descriptions are exposed additively without forcing clients to parse messages.

## 5. Allow-After-Deny Progression Detection

- [x] 5.1 Add the new `pfsense_firewall_allow_after_deny` detection family with the bounded same-source, inbound-only, deny-count, and progression-window rules defined by this change.
- [x] 5.2 Implement exact-target and same-service-within-range matching rules so unrelated later allows do not qualify as progression.
- [x] 5.3 Implement `medium` and `high` severity assignment for allow-after-deny progression without allowing reputation alone to create `high`.
- [x] 5.4 Persist bounded progression evidence that preserves both the qualifying deny history and the later allow target.
- [x] 5.5 Integrate allow-after-deny progression into incident, notification, and approval behavior while preserving approval-gated containment and prohibiting autonomous blocking.

## 6. UI And Notification Integration

- [x] 6.1 Update pfSense alert-detail surfaces to render richer target evidence, canonical scan descriptions, and related aggregate linkage in a bounded read-only form.
- [x] 6.2 Add the smallest useful recon-activity UI surface so analysts can inspect distributed reconnaissance summaries, representative sources and targets, and linked alerts or events.
- [x] 6.3 Add bounded SOC Command Center visibility for active distributed recon activities without redesigning the broader dashboard.
- [x] 6.4 Integrate aggregate opening and material-update notification behavior into the existing notification-policy path with deduplication.
- [x] 6.5 Update the Severity & Response Matrix and any read-only rule explanation surfaces so pfSense severity, incident, and containment behavior match the new contracts.

## 7. Verification And VM Handoff

- [x] 7.1 Add focused backend tests proving reputation alone cannot create `high` from minimum-threshold commodity scanning for repeated deny, port scan, or suspicious allow.
- [x] 7.2 Add focused backend tests proving real breadth, sustained activity, progression, or corroboration can still create `high` where this change allows it.
- [x] 7.3 Add focused backend tests proving routine distributed recon no longer creates one automatic P2 incident and one approval per source IP.
- [x] 7.4 Add focused backend tests proving aggregate membership requires target or service overlap and does not rely on time alone, and that unrelated same-window activity stays outside the aggregate.
- [x] 7.5 Add focused backend tests proving sample destination IPs and ports are accurate, deterministic, and bounded and that related-event inspection remains bounded.
- [x] 7.6 Add focused backend tests covering allow-after-deny true positives, false positives, severity assignment, incident eligibility, and no-unapproved-containment behavior.
- [x] 7.7 Add focused backend tests covering aggregate opening and update notification deduplication through the existing notification-policy flow.
- [x] 7.8 Add focused frontend tests for pfSense target evidence, canonical descriptions, aggregate detail rendering, and Severity Matrix accuracy.
- [x] 7.9 Run migration and schema validation for the aggregate persistence model, if implemented, and confirm no unrelated schema behavior changed.
- [x] 7.10 Run the focused backend test set, focused frontend test set, `openspec validate improve-pfsense-recon-analysis-and-progression-detection --strict`, and `git diff --check`.
- [x] 7.11 Produce a Mac-only VM handoff describing the new aggregate model, rollout/baseline steps, post-deploy baseline advancement, and required production verification with explicit confirmation that no implementation step in this authoring turn accessed the VM.
