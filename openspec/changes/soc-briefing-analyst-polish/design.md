# Design: SOC Briefing Analyst Polish

## Approach

Refine the existing SOC briefing rendering helpers in `core/ai/soc_briefing_investigation_engine.py`. Do not add another formatter layer, fallback engine, prompt layer, or workflow component.

The implementation keeps the current structured output and normalizer path, but tightens language construction:

- Critical Findings focus on what happened and why it matters.
- Escalations focus on immediate analyst attention, next action, urgency, and why the item cannot wait.
- Recommendations avoid generic target concatenation and produce natural SOC instructions.
- Confidence statements include a short evidence-based justification.
- Judgment language remains bounded by available evidence and avoids unsupported maliciousness claims.

## Preservation

The change must preserve Executive Summary quality, Evidence Reviewed prose, recommendation evidence grounding, internal metadata filtering, raw JSON removal, read-only behavior, and existing acceptance harness behavior.

## Non-Goals

- No SOC Briefing architecture redesign.
- No new prompt layer or fallback engine.
- No worker, database, frontend, detection, or investigation-selection changes.
- No changes to unrelated Anakin workflows.
