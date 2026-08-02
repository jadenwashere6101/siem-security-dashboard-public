## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks.
- [x] 1.2 Validate `anakin-natural-conversation-and-style` strictly before implementation.

## 2. Natural Conversation Prompt Contract

- [x] 2.1 Add interactive natural-conversation rules to the shared persona.
- [x] 2.2 Add concise few-shot examples to interactive workflows only.
- [x] 2.3 Strengthen tone-specific instructions for casual, professional, and technical prompts.
- [x] 2.4 Preserve formal/shareable prompt behavior for artifacts and SOC Briefing.

## 3. Positive Response Enforcement

- [x] 3.1 Add property helpers for robotic preambles, generic endings, and low-value paragraphs.
- [x] 3.2 Extend golden acceptance cases for the production-like prompts.
- [x] 3.3 Ensure prompt-size checks remain within profile limits.

## 4. Decision Support Ordering

- [x] 4.1 Normalize markdown headings, bullets, numbering, punctuation, and whitespace.
- [x] 4.2 Recognize markdown recommendation labels.
- [x] 4.3 Verify reordering and metadata are accurate.
- [x] 4.4 Verify unrelated labels are not treated as recommendations.

## 5. Verification

- [x] 5.1 Run Python compilation for modified backend files.
- [x] 5.2 Run focused persona/style tests.
- [x] 5.3 Run Decision Support ordering tests.
- [x] 5.4 Run Quick Explain, Deep Investigate, and Repo Assistant regression tests.
- [x] 5.5 Run offline acceptance harness.
- [x] 5.6 Run frontend tests/build only if frontend files change.
- [x] 5.7 Run `git diff --check`.
- [x] 5.8 Run strict OpenSpec validation.
- [x] 5.9 Capture `git status --short`.
