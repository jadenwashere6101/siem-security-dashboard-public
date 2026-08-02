## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks.
- [x] 1.2 Validate `quick-explain-prompt-budget-optimization` strictly before implementation.

## 2. Measurements

- [x] 2.1 Capture before sizes for base persona, interactive persona, quick policies, and production-like Quick Explain prompt.
- [x] 2.2 Capture after sizes and margin under `fast_triage`.

## 3. Prompt Optimization

- [x] 3.1 Add compact Quick Explain persona/style policy.
- [x] 3.2 Remove duplicated Quick Explain instructions across persona, tone, workflow, and examples.
- [x] 3.3 Keep minimal Quick Explain few-shot guidance.
- [x] 3.4 Preserve Deep Investigate, Decision Support, Repo Assistant, Generate Artifact, and SOC Briefing prompt behavior.

## 4. Tests

- [x] 4.1 Add production-like alert Quick Explain budget test.
- [x] 4.2 Add casual/professional/technical Quick Explain budget tests.
- [x] 4.3 Add source-IP and dashboard Quick Explain budget tests.
- [x] 4.4 Assert required Quick Explain natural-conversation rules remain.
- [x] 4.5 Assert compaction preserves question, evidence identity, source identity, and truncation metadata.
- [x] 4.6 Assert non-Quick workflows remain within prompt limits.

## 5. Verification

- [x] 5.1 Run requested Python compilation.
- [x] 5.2 Run requested focused pytest command.
- [x] 5.3 Run offline acceptance harness with no live smoke.
- [x] 5.4 Run `git diff --check`.
- [x] 5.5 Run strict OpenSpec validation.
- [x] 5.6 Capture `git status --short`.
