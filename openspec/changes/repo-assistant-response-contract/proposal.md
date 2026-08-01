## Why

Repo Architecture Assistant currently fails useful answers when the model does not emit citations in one exact inline syntax. This breaks normal questions such as “What is my most impressive feature?” by turning an evaluative answer into a citation-format failure.

## What Changes

- Classify repository questions as factual/repository-grounded, architectural explanation, or evaluative/opinion/recommendation.
- Keep retrieval-bounded repository grounding for all question types.
- Stop depending on model-generated citation syntax to accept answers.
- Attach citations in the backend from retrieved repository evidence.
- Preserve valid model citations as a hint when present, but never trust arbitrary model-selected paths.
- Allow evaluative/opinion answers to be direct and natural while clearly grounding judgment in retrieved evidence.
- Improve prompts so answers distinguish fact from judgment, avoid robotic disclaimers, cite evidence for factual support, and avoid fabricated repository details.
- Preserve read-only behavior, RBAC, bounded retrieval, developer-assistant profile routing, local-only policy, and no source mutation.

## Capabilities

### New Capabilities
- `repo-assistant-response-contract`: Backend-owned citation attachment and question-aware response contracts for Repo Architecture Assistant.

### Modified Capabilities

## Impact

- Backend Repo Assistant service response contract and tests.
- Frontend Repo Architecture Assistant panel metadata/copy only if needed for classification/citation display.
- No provider/model/runtime config changes, no migrations, no VM access, no deployment, and no source mutation outside this Mac repository.
