## 1. Recon Activity Triage

- [x] 1.1 Audit the current Recon Activity list/detail data already available from `core/recon_activity_store.py` and define the compact card-summary contract.
- [x] 1.2 Implement compact Recon Activity cards in `SocCommandCenter` with distinct headlines, target/service identity, timing, status, and investigation-value summary.
- [x] 1.3 Implement truthful `New` / `Updated` / reviewed behavior using the smallest safe persistence model justified by the existing architecture.
- [x] 1.4 Rework Recon Activity detail so it leads with target, representative source, service, timing, linked-alert count, related incident, investigation value, and current assessment.
- [x] 1.5 Add only the approved investigation pivots: linked alerts, related incident, representative source, and primary target when supported.
- [x] 1.6 Replace touched Recon Activity wording that is not understandable at a glance with shorter plain-English labels and reason text.
- [x] 1.7 Add focused frontend tests covering distinct card summaries, last-seen display, investigation-value reasons, new/updated state, pivots, compact layout, and missing relationship behavior.

## 2. Incident Eligibility And Priority

- [x] 2.1 Audit the current incident-creation path in `routes/ingest_routes.py` and `core/incident_store.py` against the approved honeypot and pfSense policy.
- [x] 2.2 Implement explicit incident-eligibility rules so `honeypot_scanner_detected` and `honeypot_admin_probe` remain alert-only.
- [x] 2.3 Implement the approved alert-first policy for `honeypot_env_probe_threshold`, preserving incident eligibility only when stronger supporting evidence is present in context.
- [x] 2.4 Preserve `honeypot_credential_stuffing_threshold` incident eligibility only when its existing approved threshold/evidence path is met.
- [x] 2.5 Implement explicit policy so routine aggregate pfSense recon remains incident-free while progression-backed pfSense behavior remains incident-eligible.
- [x] 2.6 Replace direct severity-driven priority mapping with explainable P1/P2/P3 reasoning based on actionability and render that reasoning in incident detail/list payloads.
- [x] 2.7 Implement grouped recon incident ownership so one recon activity can own at most one grouped incident and member alerts link to it without source-level fan-out.
- [x] 2.8 Preserve and verify the existing safe P3 auto-close guards without expanding closure scope beyond what this change requires.
- [x] 2.9 Add focused backend tests covering honeypot incident eligibility, pfSense incident eligibility, grouped ownership, no duplicate fan-out, priority assignment, priority reasoning, historical non-rewrite behavior, and P3 auto-close safety.

## 3. Verification And Handoff

- [x] 3.1 Run `python3 -m py_compile` on changed backend and backend-test files.
- [x] 3.2 Run the focused backend recon, incident, honeypot, and pfSense test suites required by this change.
- [x] 3.3 Run the focused frontend SOC Command Center, Incidents, and navigation tests required by this change.
- [x] 3.4 Run `npm run build`.
- [x] 3.5 Run `openspec validate improve-recon-activity-triage-and-incident-policy --strict`.
- [x] 3.6 Run `git diff --check`.
- [x] 3.7 Confirm the change remained Mac-only work with no commit, push, deployment, archive, or VM access.
