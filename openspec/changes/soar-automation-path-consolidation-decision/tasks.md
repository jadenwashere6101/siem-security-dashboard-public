This is a decision/specification-only child spec. No code, schema, freeze notice, coverage map, queue retirement, or playbook content is implemented here. The active checklist below tracks only the decision-only work that belongs to this spec.

## 1. Decision-Only Scope

- [x] 1.1 Complete architecture review of the response-action queue path and playbook engine path.
- [x] 1.2 Document the current-path summary, including trigger mechanisms, execution models, and safety enforcement differences.
- [x] 1.3 Record the decision that the playbook engine is the authoritative future SOAR orchestration layer.
- [x] 1.4 Document alternatives considered and rejection/selection rationale.
- [x] 1.5 Document boundaries and non-goals for this decision-only child spec.
- [x] 1.6 Document acceptance criteria for future enforcement readiness.
- [x] 1.7 Complete validation for the decision-only OpenSpec artifacts.

## 2. Future Enforcement Notes (not active tasks)

These items are intentionally not checkboxes because they do not belong to this decision-only spec:

- Freeze/deprecation notices for queue-path modules belong to a later enforcement spec.
- Protected-target parity confirmation belongs to the playbook engine correctness-hardening work.
- Queue-path coverage mapping belongs to a later enforcement or migration-readiness spec.
- Removing the ingest-time queue trigger belongs to a later queue-retirement spec after parity and coverage are proven.

## Safety Boundaries

- [x] Do not modify any file under `engines/`, `core/`, `routes/`, `migrations/`, `frontend/`, or `tests/`.
- [x] Do not create any new playbooks, engine features, branching, schedules, or evidence-collection work as part of this spec.
- [x] Do not change `response_actions_queue` or `playbook_definitions` schema.
- [x] Do not commit.
