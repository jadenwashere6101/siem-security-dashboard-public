# Change: SOC Briefing Analyst Quality

## Why

SOC Briefing output is structurally valid but can read like placeholder or raw machine output. Analysts need shift-handoff value: what happened, why it matters, what changed, what needs attention, what can wait, and what evidence supports the judgment.

## What Changes

- Strengthen SOC Briefing synthesis prompting so the model writes concise analyst handoff content rather than inventory or generic recommendations.
- Add deterministic post-processing that rejects placeholder summaries, avoids raw JSON-style section content, explains empty sections, references available evidence, and preserves deterministic fallback behavior.
- Expand focused tests and acceptance coverage for analyst-readable evidence, evidence-specific recommendations, reasoning in findings, correlation, uncertainty, and professional shareability.

## Scope

Mac AI only. No VM development, no deployment, no persistence/schema/workflow architecture changes, no fabricated evidence, no invented alerts, no commit.
