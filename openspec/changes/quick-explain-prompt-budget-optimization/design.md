# Design

## Compact Quick Explain Policy

Quick Explain does not need the entire interactive policy. It needs a small fixed instruction block that preserves:

- Detection Engineer teammate identity;
- immediate answer;
- 2-6 concise sentences;
- natural tone adaptation;
- no corporate preambles;
- no visible-field-only restatement;
- evidence-bounded uncertainty;
- one concrete next step;
- no generic closing disclaimer;
- read-only boundaries.

The new compact policy stays separate from `interactive_persona_policy()` so Deep Investigate, Decision Support, and Repo Assistant keep their existing deeper prompt contracts.

## Few-Shot Budget

Quick Explain keeps a tiny style example, shorter than the broader interactive examples. It demonstrates the deployed failure mode: casual question, robotic bad answer, natural good answer. The example is framed as style-only so its conclusion is not copied into unrelated contexts.

## Context Budgeting

Prompt compaction remains fail-closed. Tests assert that production-like prompt construction preserves:

- user question;
- source identity;
- context/truncation metadata;
- evidence identity.

No profile limits are raised.

## Regression Boundary

Deep Investigate, Decision Support, Repo Assistant, Generate Artifact, and SOC Briefing prompt contracts are not redesigned. Tests cover that they remain within their configured prompt limits after this change.
