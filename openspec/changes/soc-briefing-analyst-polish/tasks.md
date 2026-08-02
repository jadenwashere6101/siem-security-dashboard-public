## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `soc-briefing-analyst-polish`.
- [x] 1.2 Run strict OpenSpec validation.

## 2. Analyst Prose Polish

- [x] 2.1 Refine Critical Findings so they focus on what happened and why it matters.
- [x] 2.2 Refine Escalations so they focus on immediate attention, next action, urgency, and why the issue cannot wait.
- [x] 2.3 Improve recommendation rendering to avoid awkward concatenation and generic target labels.
- [x] 2.4 Add evidence-based confidence explanations.
- [x] 2.5 Keep judgment language cautious and evidence-bounded.
- [x] 2.6 Preserve existing summary quality, evidence prose, metadata filtering, JSON removal, and read-only behavior.

## 3. Tests

- [x] 3.1 Add tests proving Critical Findings and Escalations are meaningfully different.
- [x] 3.2 Add tests for natural recommendation wording.
- [x] 3.3 Add tests for confidence explanations.
- [x] 3.4 Add tests that cautious evidence-bounded language is preserved.
- [x] 3.5 Run affected SOC Briefing and acceptance tests.

## 4. Verification

- [x] 4.1 Run Python compilation.
- [x] 4.2 Run PostgreSQL-backed SOC Briefing tests.
- [x] 4.3 Run AI acceptance harness.
- [x] 4.4 Run `git diff --check`.
- [x] 4.5 Run `openspec validate soc-briefing-analyst-polish --strict`.
- [x] 4.6 Capture `git status --short`.
