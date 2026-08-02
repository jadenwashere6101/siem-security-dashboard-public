# Change: SOC Briefing Analyst Polish

## Why

SOC Briefings are structurally correct and now avoid raw JSON/Python metadata leaks, but some analyst-facing prose still feels templated. Critical Findings and Escalations can overlap, recommendations can read mechanically, and confidence statements can be too terse for shift handoff use.

## What Changes

- Refine existing SOC briefing language helpers so Critical Findings and Escalations serve distinct handoff purposes.
- Make recommendations read naturally while remaining grounded in evidence.
- Add evidence-bounded confidence explanations and cautious judgment language.
- Preserve existing Executive Summary quality, Evidence Reviewed prose, internal metadata filtering, read-only behavior, and acceptance coverage.

## Scope

Mac AI only. This is a backend language-rendering polish pass, not an architecture redesign. No VM work, deployment, persistence changes, worker scheduling changes, frontend changes, detection changes, or unrelated Anakin workflow changes.
