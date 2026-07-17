## ADDED Requirements

### Requirement: Contextual Response Registry opens SHALL override stale local filters
Opening Response Registry from another analyst workflow SHALL apply the incoming investigation context authoritatively enough that stale registry-local filters cannot hide the intended record.

#### Scenario: Alert-driven registry handoff
- **WHEN** an analyst opens Response Registry from `Recent Alerts`, incidents, approvals, playbooks, queue items, or another related workflow with source-IP or relationship context
- **THEN** the registry SHALL apply the incoming view, indicator query, and related identifiers, reset pagination and current detail selection, and clear incompatible local filters that would prevent the intended record from appearing

#### Scenario: Analyst continues manual registry review after the handoff
- **WHEN** the contextual open has finished
- **THEN** the analyst SHALL still be able to adjust registry-local filters manually without losing the applied investigation context until they change it
