## 1. Bounded Synthesis

- [x] 1.1 Implement complete-prompt fit-by-construction budgeting for guided analysis without changing the 14,000-character profile limit
- [x] 1.2 Preserve mandatory question, task/entity context, essential evidence, provenance, truncation, grounding, and safety content while prioritizing optional compaction
- [x] 1.3 Add deterministic grounded partial synthesis when mandatory content cannot fit and skip provider invocation
- [x] 1.4 Record sanitized before/after prompt-budget measurements and fallback metadata

## 2. Verification

- [x] 2.1 Add focused large-evidence and mandatory-overflow tests that verify bounded prompts and grounded fallback
- [x] 2.2 Run affected AI, planner, orchestration, acceptance, compilation, and diff checks
- [x] 2.3 Validate `guided-analysis-prompt-budget-resilience` with strict OpenSpec validation

## 3. Production Acceptance Gate

- [ ] 3.1 Follow `docs/anakin-production-acceptance-policy.md`: automated checks are necessary but not sufficient; verify the deployed Deep Investigate browser path before using working/done/fully verified/production-ready language, otherwise report exactly `Implementation complete; production behavior unverified.`
