## Overview

The current assistant asks the model to emit citations in `[path:line_start-line_end]` form, then rejects the full response if `_validated_citations()` finds no valid match. That makes citation syntax part of correctness. The backend already owns retrieval and knows the allowed evidence chunks, so it should own final citation attachment.

## Question Classification

Classify the user message into:

- `factual`: asks where/how/what file/implementation details are grounded in source.
- `architectural`: asks for design explanation, component relationships, tradeoffs, or system behavior.
- `evaluative`: asks for judgment, ranking, recommendation, strongest/weakest/most impressive feature, or opinion.

This can be a deterministic lightweight classifier based on question wording. It does not require another model call.

## Citation Contract

Retrieval remains bounded through `RepoIndex.search()`. The response uses retrieved chunks as allowed evidence. Backend-selected citations are attached from the top current chunks, optionally narrowed to chunks referenced by valid model citation syntax. Missing or malformed model citations no longer invalidate the answer.

Model-provided citation strings are untrusted: only citations matching retrieved chunk paths/ranges may influence the selected citations. Arbitrary paths are ignored.

## Prompt Contract

Prompts tell the model:

- answer the user directly;
- use only supplied repository excerpts;
- distinguish repository fact from judgment/inference;
- for evaluative questions, make a clear judgment and explain why using retrieved evidence;
- avoid robotic citation disclaimers;
- omit unsupported claims or label them as inference;
- do not claim edits, deployments, VM/database access, commits, shell commands, or production mutation.

Factual and architectural answers should include evidence-backed statements. Evaluative answers should still return citations in the response payload, but the prose may be natural and does not need exact inline citation syntax.

## Response Shape

Keep the existing response shape and add a `question_type` field. Continue returning `citations`, `retrieval`, `metadata`, and `error`. Grounding failure should be reserved for no retrieved current evidence or provider failure, not missing citation syntax.

## Safety

The Repo Assistant remains super-admin-only, read-only, bounded to repository index retrieval, routed through `developer_assistant`, local-only/no-paid-fallback under existing gateway policy, and unable to mutate source or runtime state.

## Verification

Tests should prove:

- evaluative questions produce useful answers without model citation syntax;
- factual questions return backend-selected retrieved citations;
- architecture questions return explanation plus evidence;
- model hallucinated paths are ignored;
- no arbitrary model-selected citation path is trusted;
- missing current evidence still fails closed.
