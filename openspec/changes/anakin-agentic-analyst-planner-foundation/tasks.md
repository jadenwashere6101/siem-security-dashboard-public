## 1. Readiness and Contracts

- [x] 1.1 Trace current free-form routing, context resolution, tool selection, gateway/profile limits, session assertions, and isolated route boundaries against the implemented code.
- [x] 1.2 Document planner placement, transaction boundaries, strict plan contract, budget model, capability mappings, and the complete failure-class enforcement table.
- [x] 1.3 Add typed planner packet/plan contracts, strict parser/validator, bounded one-repair behavior, and safe planner-unavailable results.

## 2. Planner Integration

- [x] 2.1 Build a fit-by-construction planner packet from authoritative thread/entity/evidence state with provenance, freshness, omission, and size measurements.
- [x] 2.2 Integrate planning after bounded authoritative fact construction and before eligible conversation capability selection without holding a database lock during model generation.
- [x] 2.3 Dispatch validated direct, lookup, investigation, comparison, decision, artifact, clarification, and boundary plans through existing safe paths while preventing workflow reclassification.
- [x] 2.4 Preserve Repo Assistant, SOC Briefing, mutation/action, read-only Decision Support, and preview-only Generate Artifact boundaries.

## 3. Focused Verification

- [x] 3.1 Add unit tests for schema validation, semantic strategy mappings, entity/evidence provenance checks, budget enforcement, one repair, timeout/provider failure, and prohibited plans.
- [x] 3.2 Add three-paraphrase behavioral tests for lookup, priority, explanation, evidence, topic switch, comparison, correction, no-tool, ambiguity, and boundary intents.
- [x] 3.3 Add production-shaped PostgreSQL integration coverage from planner packet through controlled provider, dispatch, response envelope, and durable thread state.
- [x] 3.4 Add repeated-run local-model capability measurements when the configured local provider is available; report limitations without model or profile changes.
- [x] 3.5 Run Python compilation, focused PostgreSQL suites, prompt-budget and workflow-boundary tests, and the AI acceptance harness.

## 4. Final Gates

- [x] 4.1 Run the full PostgreSQL-backed repository suite once and compare failures against current-HEAD baseline with no new failures.
- [x] 4.2 Run `git diff --check` and `openspec validate anakin-agentic-analyst-planner-foundation --strict`.
- [x] 4.3 Review sticky-workflow, paraphrase, conflicting-state, evidence, malformed-plan, boundary, timeout, and nondeterminism variants and record remaining Spec 2/3 work.

## 5. Anakin Production Completion Gate

- [ ] 5.1 Before using working, done, fully verified, or production-ready language, follow `docs/anakin-production-acceptance-policy.md` and verify every affected workflow through `browser -> /siem/ -> nginx -> frontend -> backend -> worker/Ollama -> frontend-rendered result`, capturing workflow, browser/API/UI results, latency, pass/fail, root cause, mutation status, and remaining unverified behavior.
- [x] 5.2 Because this implementation phase forbids deployment and VM access, report exactly `Implementation complete; production behavior unverified.` and do not claim Anakin is now an intelligent analyst agent.

## 6. Production Integration Correction

- [x] 6.1 Register `agentic_analyst_planning` in the Ollama provider capability contract without weakening unsupported-provider checks or local-only/no-paid-fallback policy.
- [x] 6.2 Validate the original requested workflow before planner generation, repair, classification, or fallback; reject Repo Assistant, SOC Briefing, and unknown workflows deterministically.
- [x] 6.3 Add provider/gateway and orchestration/route regression tests proving generation reachability, original-intent boundary ordering, safe planner-unavailable behavior, and valid shortcut fallback.
- [x] 6.4 Run focused PostgreSQL-backed tests, AI acceptance harness, Python compilation, `git diff --check`, and strict OpenSpec validation.

## 7. Planner Model/Profile Correction

- [x] 7.1 Add a dedicated local-only `agentic_planning` profile, initially using `llama3.1:8b`, with planner-specific prompt, output, timeout, and temperature limits and paid fallback disabled; section 18 records the later benchmark-selected model replacement.
- [x] 7.2 Route initial and repair planner requests through the dedicated profile while preserving every existing workflow profile assignment.
- [x] 7.3 Keep deterministic cross-field validation authoritative, clarify semantic relationships in the planner prompt, and add focused valid, repair, and fail-closed tests.
- [x] 7.4 Run Python compilation, profile/provider/gateway/planner/orchestration tests, affected PostgreSQL-backed suites, AI acceptance harness, `git diff --check`, and strict OpenSpec validation.
- [ ] 7.5 After a separately authorized deployment, run the real-model planner capability matrix before declaring readiness for Spec 2.

## 8. Planner Contract Ownership Correction

- [x] 8.1 Audit every planner field and document one owner: model reasoning, authoritative server state, or deterministic derivation.
- [x] 8.2 Reduce model output to reasoning-bearing fields and compile entities, relationship, capability, safety, and execution metadata deterministically without weakening fail-closed validation or one-repair behavior.
- [x] 8.3 Update focused planner, orchestration, production-payload, metadata, and boundary tests; run Python compilation, affected PostgreSQL suites, `git diff --check`, and strict OpenSpec validation.
- [ ] 8.4 After separately authorized deployment, repeat the real-model planner matrix before Spec 2.

## 9. Planner Evidence-Intent Preservation

- [x] 9.1 Add a strict, schema-bounded `evidence_requirements` proposal field and document model reasoning versus server validation/translation ownership.
- [x] 9.2 Translate validated requirements into one existing SOC read-tool request while preserving read-only, RBAC, category, IP, time-window, sort, and limit bounds and failing closed when a requirement cannot be represented.
- [x] 9.3 Add focused planner, translation, read-tool, and PostgreSQL production-shaped coverage proving requested filters reach execution and exclude non-matching evidence.
- [x] 9.4 Run Python compilation, focused tests, `git diff --check`, and strict OpenSpec validation.

## 10. Evidence-Grounded Final Synthesis Correction

- [x] 10.1 Document the evidence envelope, grounding ownership, task-aware response contract, and complete synthesis failure-class invariants before implementation.
- [x] 10.2 Pass planner intent and validated requirements into final synthesis, build a compact server-authored evidence envelope, and remove unconditional Quick Explain example language.
- [x] 10.3 Validate tool-backed model output and deterministically normalize generic, unsupported, empty-result, and truncated-result answers from envelope facts only.
- [x] 10.4 Add production-derived explainer and PostgreSQL conversation tests covering alert, evidence, source-IP, time-window, empty, differing, injection, truncation, state, persistence, and boundary cases.
- [x] 10.5 Run Python compilation, focused PostgreSQL-backed suites, affected explainer/workflow regressions, AI acceptance harness, `git diff --check`, and strict OpenSpec validation.

## 11. Fit-by-Construction Synthesis Correction

- [x] 11.1 Trace Quick Explain, Decision Support, and regular Quick Explain prompt composition; document complete-prompt ownership, priority, fallback, repair, state-summary, and artifact-type failure invariants.
- [x] 11.2 Replace independent section budgets with a final-prompt builder that reserves mandatory evidence/safety content and admits optional context by measured priority.
- [x] 11.3 Return task-aware deterministic evidence answers when successful evidence cannot be synthesized within the active profile limit.
- [x] 11.4 Improve one-repair contract feedback, state-summary planning guidance, and bounded artifact draft-type handling without weakening validation.
- [x] 11.5 Add production-derived prompt measurements and PostgreSQL workflow tests, then run compilation, focused suites, acceptance harness, `git diff --check`, and strict validation.

## 12. Current-Turn Intent and Capability Reachability Correction

- [x] 12.1 Add the bounded current-turn action contract, action/strategy compatibility, conditional planner metadata ownership, and repair action pinning.
- [x] 12.2 Expose uniformly represented entity, turn, evidence, and stored-state facts with provenance as bounded planner context without server-authored conversational labels.
- [x] 12.3 Add server-owned evidence-filter provenance and reject unsupported narrowing constraints without inheriting stale query filters.
- [x] 12.4 Add production-shaped natural-language capability reachability, repair stability, reference, persistence, and PostgreSQL integration coverage.
- [x] 12.5 Run Python compilation, focused PostgreSQL and AI suites, the AI acceptance harness, `git diff --check`, and strict OpenSpec validation.

## 13. Planner-Owned Natural-Language Boundary Correction

- [x] 13.1 Replace the existing design/spec boundary with planner-owned intent, relationship, reference, entity, capability, filter, artifact-type, and clarification interpretation plus post-plan server validation.
- [x] 13.2 Remove the pre-planner deterministic reference resolver, candidate ranking, phrase matching, ambiguity decisions, sentence-derived filter extraction, and artifact language matching.
- [x] 13.3 Require planner-selected relationships, capabilities, resolved entities, correction targets, and bounded artifact types; validate selections against PostgreSQL ownership/RBAC before constructing one canonical execution context.
- [x] 13.4 Add three materially different phrasings for state, lookup, literal entity, Decision Support, artifact, continuation, comparison, clarification, topic switch, and return-to-prior scenarios through the planner boundary.
- [x] 13.5 Run Python compilation, focused unit and PostgreSQL suites, acceptance harness, `git diff --check`, strict OpenSpec validation, and the complete failure-class gate.

## 14. Pure Fact-Packet Boundary Refinement

- [x] 14.1 Document unrestricted-language planning, the permanent anti-phrasing-patch rule, and the model-agnostic server invariant.
- [x] 14.2 Replace interpretive context labels with a provenance-bearing authoritative fact packet without changing stored thread state or workflow behavior.
- [x] 14.3 Add regression assertions that planner packets contain no focus, priority, preferred-reference, intent, or relationship fields supplied by the server.
- [x] 14.4 Run the existing focused unit, PostgreSQL, acceptance, compilation, diff, and strict OpenSpec gates.

## 15. Structured Action and Entity Cardinality Correction

- [x] 15.1 Define one authoritative action/strategy contract covering entity cardinality, filter permission, clarification shape, tool execution, and capability dispatch without language interpretation.
- [x] 15.2 Generate planner and repair guidance from the contract, align deterministic validation, and support neutral entityless execution for open lookups and state summaries.
- [x] 15.3 Validate every planner-selected entity after planning, including non-executing clarification candidates, without server selection or substitution.
- [x] 15.4 Add focused unit and PostgreSQL production-derived coverage for open lookup, entity-bound capabilities, comparison cardinality, clarification persistence, invalid/unauthorized entities, and contract alignment.
- [x] 15.5 Run Python compilation, focused AI and PostgreSQL suites, grounding/prompt-budget regressions, acceptance harness, `git diff --check`, and strict OpenSpec validation.

## 16. Fit-by-Construction Planner Prompt Correction

- [x] 16.1 Make one complete-prompt builder reserve mandatory planner content and measured gateway framing before admitting deduplicated optional facts against the active profile ceiling.
- [x] 16.2 Build an independently bounded one-attempt repair prompt from the original proposal, exact errors, compact contract/schema, and required authoritative facts without nesting the initial prompt.
- [x] 16.3 Convert planner budget/configuration failures into truthful non-executing outcomes across synchronous and asynchronous conversation submission without sticky workflow fallback.
- [x] 16.4 Add first-turn, three-turn, twenty-turn, many-entity, evidence-deduplication, clarification/comparison, initial/repair stress, mandatory-overflow, and semantic-contract equivalence regressions.
- [x] 16.5 Run compilation, affected unit and PostgreSQL suites, prompt/grounding regressions, acceptance harness, `git diff --check`, and strict OpenSpec validation.

## 17. Structured-Output Prompt Regression Correction

- [x] 17.1 Document exact enum vocabulary, raw-JSON-only output boundaries, repair preservation, strict parsing, and prompt-budget invariants in the existing design and specification.
- [x] 17.2 Generate explicit initial and repair enum instructions from validator-owned constants and restore JSON-only response boundaries without parser relaxation.
- [x] 17.3 Add strict-output, enum-equivalence, repair-preservation, capability-reachability, and twenty-turn budget regressions.
- [x] 17.4 Run compilation, affected PostgreSQL-backed planner/orchestration suites, grounding regressions, acceptance harness, `git diff --check`, and strict OpenSpec validation.

## 18. Benchmark-Selected Planner Model Upgrade

- [x] 18.1 Record the apples-to-apples `qwen3:14b` benchmark, per-generation timeout semantics, latency tradeoff, and unchanged architecture in proposal, design, and specification.
- [x] 18.2 Change only the source-controlled `agentic_planning` model default to `qwen3:14b` while preserving all profile limits, local-only policy, and unrelated profile assignments.
- [x] 18.3 Align the canonical Mac/VM/Mini-PC source-of-truth policy with the planner model and deployment discipline.
- [x] 18.4 Add focused profile/provider metadata and documentation-contract regressions.
- [x] 18.5 Run compilation, profile/provider/planner/orchestration and PostgreSQL suites, acceptance harness, `git diff --check`, and strict OpenSpec validation.

## 19. Entity-to-Tool Binding Correctness

- [x] 19.1 Trace resolved entity facts through planner schema, cross-field validation, repair, evidence translation, read-tool validation, executor filtering, and synthesis; record the exact loss point and supported binding matrix.
- [x] 19.2 Extend the bounded evidence/tool contracts with existing structured identity arguments and reject missing, mismatched, or unsupported entity/category bindings without parsing conversational language.
- [x] 19.3 Preserve exact validated identities through planner repair and one bounded tool request while keeping genuinely entityless searches valid.
- [x] 19.4 Add focused planner, repair, orchestration, read-tool, executor, and no-language-interpretation regressions for alert `9663`, wrong/unfiltered IDs, generic searches, and other established entity bindings.
- [x] 19.5 Run focused and affected AI tests, the offline acceptance harness, Python compilation, `git diff --check`, and strict OpenSpec validation without real provider traffic.
