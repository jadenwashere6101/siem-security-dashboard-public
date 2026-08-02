## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks.
- [x] 1.2 Validate `anakin-response-quality-enforcement` strictly before implementation.

## 2. Backend Response-Quality Enforcement

- [x] 2.1 Add deterministic tone classification helpers.
- [x] 2.2 Pass tone instructions into workflow prompts and metadata where response envelopes allow.
- [x] 2.3 Enforce Decision Support recommendation-first structure in prompt contract.
- [x] 2.4 Add explicit disagreement behavior for unsupported user assumptions.
- [x] 2.5 Add semantic filler/disclaimer pattern checks.
- [x] 2.6 Ensure Deep Investigate ends with next step or unresolved question.
- [x] 2.7 Preserve Generate Artifact and SOC Briefing professional/shareable boundaries.

## 3. Tests

- [x] 3.1 Add focused tests for tone classification and metadata.
- [x] 3.2 Add tests for Decision Support recommendation-first contract.
- [x] 3.3 Add tests for explicit disagreement on weak evidence.
- [x] 3.4 Add tests for casual/professional/technical tone behavior.
- [x] 3.5 Add tests for filler paraphrase and disclaimer rejection.
- [x] 3.6 Add tests preserving uncertainty and evidence-bounded reasoning.

## 4. Verification

- [x] 4.1 Run Python compilation for modified backend files.
- [x] 4.2 Run focused response-quality/persona tests.
- [x] 4.3 Run affected acceptance tests and offline acceptance harness.
- [x] 4.4 Run `git diff --check`.
- [x] 4.5 Run strict OpenSpec validation.
- [x] 4.6 Capture `git status --short`.
