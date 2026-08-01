## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `repo-assistant-response-contract`.
- [x] 1.2 Validate the OpenSpec strictly.

## 2. Backend Response Contract

- [x] 2.1 Add deterministic repo question classification.
- [x] 2.2 Update repo assistant prompt instructions by question type.
- [x] 2.3 Replace citation-syntax-required failure with backend-owned citation attachment.
- [x] 2.4 Ignore model citations that do not match retrieved evidence.
- [x] 2.5 Preserve developer-assistant profile routing, read-only behavior, RBAC, bounded retrieval, and no mutation.

## 3. Frontend Contract

- [x] 3.1 Surface question type if useful without adding noisy UI.
- [x] 3.2 Preserve existing citation/retrieval display.

## 4. Tests

- [x] 4.1 Add backend tests for evaluative answer without model citation syntax.
- [x] 4.2 Add backend tests for factual SOAR worker answer with backend-selected citations.
- [x] 4.3 Add backend tests for architecture explanation with evidence.
- [x] 4.4 Add backend tests proving arbitrary model citation paths are ignored.
- [x] 4.5 Add/update frontend tests if response metadata changes are displayed.

## 5. Verification

- [x] 5.1 Run Python compilation for modified modules.
- [x] 5.2 Run focused Repo Assistant backend tests.
- [x] 5.3 Run affected frontend tests if applicable.
- [x] 5.4 Run frontend production build if frontend changes.
- [x] 5.5 Run `git diff --check`.
- [x] 5.6 Run `openspec validate repo-assistant-response-contract --strict`.
- [x] 5.7 Run `openspec status --change repo-assistant-response-contract`.
