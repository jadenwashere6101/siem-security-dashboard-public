## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `soc-briefing-analyst-quality`.
- [x] 1.2 Run strict OpenSpec validation.

## 2. SOC Briefing Quality

- [x] 2.1 Strengthen SOC Briefing synthesis prompt for analyst handoff value.
- [x] 2.2 Normalize section content into analyst-readable language without raw JSON dumps.
- [x] 2.3 Replace placeholder summaries with deterministic analyst summaries.
- [x] 2.4 Explain empty critical, escalation, low-priority, evidence, and recommendation sections.
- [x] 2.5 Preserve bounded repair, read-only safety, evidence refs, and deterministic fallback behavior.
- [x] 2.6 Correct production raw-dict leakage by replacing direct dict stringification with section-aware semantic normalization.
- [x] 2.7 Expand internal-term filtering for `dedup_key`, source/tool metadata, record metadata, bounded-evidence language, and lifecycle/storage terminology.
- [x] 2.8 Strengthen synthesis and repair schema guidance with preferred section-specific object shapes while keeping post-processing tolerant.

## 3. Tests And Acceptance

- [x] 3.1 Add focused tests for no placeholder executive summary.
- [x] 3.2 Add focused tests for readable Evidence Reviewed language.
- [x] 3.3 Add focused tests for recommendations referencing specific evidence.
- [x] 3.4 Add focused tests for critical finding reasoning and confidence.
- [x] 3.5 Add focused tests for empty-section explanations and alert correlation.
- [x] 3.6 Expand acceptance/golden coverage for professional, shareable SOC Briefing output.
- [x] 3.7 Add focused and acceptance tests that reject internal pipeline terminology, raw source paths, tool names, and record-count metadata in analyst-facing prose.
- [x] 3.8 Add production-regression tests for observed Evidence Reviewed dict shapes: `fact`, `fact` + `inference` + `uncertainty`, `type` + `description`, and type-only.
- [x] 3.9 Add production-regression tests for observed Recommendation dict shapes: `step` + `description`, `action` + `target`, and `recommended_action` + `reason`.
- [x] 3.10 Add production-regression tests for unknown and nested dict/list shapes, metadata preservation in `evidence_refs`, and absence of Python/JSON literal output.

## 4. Verification

- [x] 4.1 Run affected backend tests.
- [x] 4.2 Run acceptance harness tests.
- [x] 4.3 Run Python compilation for modified modules.
- [x] 4.4 Run `git diff --check`.
- [x] 4.5 Run `openspec validate soc-briefing-analyst-quality --strict`.
- [x] 4.6 Capture `git status --short`.
