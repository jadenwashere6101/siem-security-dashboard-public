## 1. Documentation Audit

- [ ] 1.1 Audit existing README, docs, runbooks, deployment notes, worker daemon docs, and integration smoke-test docs.
- [ ] 1.2 Identify stale or duplicate runbook notes that could confuse demo or interview flow.
- [ ] 1.3 Identify current frontend navigation labels and empty states that may confuse a first-time reviewer.
- [ ] 1.4 Confirm implementation can remain docs-first with only small frontend polish.

## 2. Demo Readiness Docs

- [ ] 2.1 Create or update a SOAR demo checklist with pre-demo safety checks, expected app state, and stop conditions.
- [ ] 2.2 Create a safe demo script with click order across Dashboard, SOC Command Center, Playbooks, SOAR Operations, SOAR Metrics, and Integrations.
- [ ] 2.3 Document expected dashboard states and what each screen proves.
- [ ] 2.4 Document safe reset/seed guidance using existing safe workflows only; do not add dangerous cleanup scripts.
- [ ] 2.5 Add screenshot/evidence capture checklist with secret/redaction review.

## 3. Portfolio / Interview Docs

- [ ] 3.1 Create architecture summary doc covering UI, APIs, stores, worker, integrations, and safety flow.
- [ ] 3.2 Create technical decisions doc covering tradeoffs and why simulation-safe/guarded real-mode design was chosen.
- [ ] 3.3 Create security/safety boundaries summary covering real-mode guards, firewall simulation-only boundary, audit/redaction, approvals, dead letters, rate limiting, and dedup.
- [ ] 3.4 Create “what I built” summary for portfolio readers.
- [ ] 3.5 Create resume bullet draft section with concise technical achievements.

## 4. Operational Docs Cleanup

- [ ] 4.1 Clarify Mac/local development vs VM/deployment workflow.
- [ ] 4.2 Document frontend build/deploy command path.
- [ ] 4.3 Document backend deploy/restart command path without running VM actions.
- [ ] 4.4 Link worker daemon runbook.
- [ ] 4.5 Link Slack/Teams/email/webhook integration smoke-test runbooks.
- [ ] 4.6 Consolidate or cross-link stale runbook notes instead of leaving conflicting instructions.

## 5. UI Polish Checklist / Optional Small Polish

- [ ] 5.1 Review SOC Command Center labels, empty states, and simulation/real-mode wording.
- [ ] 5.2 Review Playbooks execution timeline labels and empty states.
- [ ] 5.3 Review SOAR Metrics and SOAR Operations labels for demo clarity.
- [ ] 5.4 Review top-level navigation labels for confusing duplication while preserving existing architecture.
- [ ] 5.5 Apply only small frontend copy/label/empty-state polish if needed.
- [ ] 5.6 Confirm viewer/auditor restrictions remain intact.

## 6. Final Validation Checklist

- [ ] 6.1 Run focused frontend tests for touched UI: SOC Command Center, Playbook Execution Timeline, PlaybooksPanel, SOAR Metrics, DeadLettersPanel, and App if navigation changes.
- [ ] 6.2 Run `npm run build` from `frontend/`.
- [ ] 6.3 Run focused backend regression tests for SOAR execution, approvals, dead letters, integrations, and worker behavior if docs reference final validation evidence.
- [ ] 6.4 Run secret/redaction review for new docs and any screenshots/evidence references.
- [ ] 6.5 Run `git diff --check`.
- [ ] 6.6 Run `git status --short`.
- [ ] 6.7 Document deployment verification steps without performing VM/runtime actions unless explicitly requested.
- [ ] 6.8 Confirm no schema, backend execution semantics, real integrations, VM actions, dangerous cleanup scripts, or credential exposure were introduced.
