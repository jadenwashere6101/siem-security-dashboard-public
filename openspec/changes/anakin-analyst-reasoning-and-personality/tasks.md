## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `anakin-analyst-reasoning-and-personality`.
- [x] 1.2 Run strict OpenSpec validation before implementation.

## 2. Shared Persona Policy

- [x] 2.1 Add shared Anakin Detection Engineer persona and reasoning policy helpers.
- [x] 2.2 Add workflow-specific policy builders without creating one universal prompt.

## 3. Prompt Integration

- [x] 3.1 Apply Quick Explain policy to explain/chat prompts.
- [x] 3.2 Apply Deep Investigate policy to investigation prompts.
- [x] 3.3 Apply Decision Support recommendation-only policy.
- [x] 3.4 Apply Generate Artifact evidence-specific policy while preserving strict schemas and repair.
- [x] 3.5 Apply SOC Briefing prioritization policy.
- [x] 3.6 Apply Repo Assistant fact-vs-judgment policy.

## 4. Tests And Acceptance

- [x] 4.1 Add prompt-contract tests for all six workflows.
- [x] 4.2 Add golden reasoning-property acceptance cases.
- [x] 4.3 Prove Decision Support does not draft/apply and Quick Explain stays tool-free.
- [x] 4.4 Prove artifact validation and bounded repair remain intact.

## 5. Verification

- [x] 5.1 Run focused backend prompt/service tests.
- [x] 5.2 Run workflow architecture regression tests.
- [x] 5.3 Run offline AI acceptance harness.
- [x] 5.4 Run affected frontend tests/build only if frontend files change.
- [x] 5.5 Run `git diff --check`.
- [x] 5.6 Run strict validation for all three active OpenSpecs.
- [x] 5.7 Capture combined `git status --short`.
