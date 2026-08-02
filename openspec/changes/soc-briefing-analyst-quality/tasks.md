## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `soc-briefing-analyst-quality`.
- [x] 1.2 Run strict OpenSpec validation.

## 2. SOC Briefing Quality

- [x] 2.1 Strengthen SOC Briefing synthesis prompt for analyst handoff value.
- [x] 2.2 Normalize section content into analyst-readable language without raw JSON dumps.
- [x] 2.3 Replace placeholder summaries with deterministic analyst summaries.
- [x] 2.4 Explain empty critical, escalation, low-priority, evidence, and recommendation sections.
- [x] 2.5 Preserve bounded repair, read-only safety, evidence refs, and deterministic fallback behavior.

## 3. Tests And Acceptance

- [x] 3.1 Add focused tests for no placeholder executive summary.
- [x] 3.2 Add focused tests for readable Evidence Reviewed language.
- [x] 3.3 Add focused tests for recommendations referencing specific evidence.
- [x] 3.4 Add focused tests for critical finding reasoning and confidence.
- [x] 3.5 Add focused tests for empty-section explanations and alert correlation.
- [x] 3.6 Expand acceptance/golden coverage for professional, shareable SOC Briefing output.
- [x] 3.7 Add focused and acceptance tests that reject internal pipeline terminology, raw source paths, tool names, and record-count metadata in analyst-facing prose.

## 4. Verification

- [x] 4.1 Run affected backend tests.
- [x] 4.2 Run acceptance harness tests.
- [x] 4.3 Run Python compilation for modified modules.
- [x] 4.4 Run `git diff --check`.
- [x] 4.5 Run `openspec validate soc-briefing-analyst-quality --strict`.
- [x] 4.6 Capture `git status --short`.
