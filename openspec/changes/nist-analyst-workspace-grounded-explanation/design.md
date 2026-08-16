## Context

Spec 1 persists immutable NIST SP 800-171 Rev. 3 catalog identity, declared boundaries, bounded assessment runs, exactly 12 requirement results, source-health snapshots, and reference-only provenance. Production has verified that evidence can become available while degraded/unknown collection remains fail closed. The missing product layer is a cohesive analyst workspace and an optional explanation action.

The current NIST API lacks boundary run history and accepts an arbitrary requirement ID on the evidence route without proving a corresponding result. The generic Anakin explain route accepts client context, while conversational workflows can invoke planner and session-memory selection. Those paths are inappropriate for an immutable NIST result. Existing `ai_workflow_requests`, its owner-bound polling API, and the workflow worker provide the required asynchronous lifecycle without adding infrastructure.

## Goals / Non-Goals

**Goals:**

- Present persisted boundaries, runs, 12 results, bounded provenance, exports, and authorized controls in one accessible workspace.
- Preserve mapping strength, evidence status, and collection confidence as separate, non-compliance concepts.
- Add bounded keyset run history and fail-closed evidence ownership checks.
- Queue an ID-only explanation, revalidate all bindings in the worker, synthesize from at most 25 persisted references, and strictly validate the complete model response.
- Keep Gunicorn free of inference work and keep the workspace useful during every AI failure state.

**Non-Goals:**

- Compliance, satisfaction, pass/fail, certification, CMMC, maturity, or percentage decisions.
- Planner, Deep Investigate, conversation/session memory, SOC tools, entity resolution, generic AI context, collectors, source health, mappings, provider routing, or Anthropic changes.
- Raw payload display, explanation-history UI/table, saved views, comparisons, reports, charts, automatic runs, or unsupported entity navigation.

## Decisions

### One state-based NIST workspace

Add one SOC section using the existing App/Sidebar state navigation, `MasterDetailLayout`, async-state components, UI primitives, theme tokens, and service helpers. Boundary/run selection drives lazy persisted reads. The selected result opens a detail pane and paginated evidence; evidence for unselected results is not fetched. A permanent server-consistent disclaimer and three separately labelled status chips prevent compliance interpretation. A new router, component library, global store, or scorecard was rejected.

### Existing APIs plus two narrow corrections

Add `GET /nist/evidence/boundaries/<id>/runs` with `limit <= 50` and an optional `(before_created_at, before_id)` cursor. Fetch `limit + 1`, return a next cursor, and reuse the existing boundary/created index. Require both cursor fields together and a timezone-aware timestamp. The evidence route first resolves the exact `(run_id, requirement_id)` result and returns 404 when absent. Neither path invokes collectors.

### ID-only asynchronous explanation

`POST /nist/evidence/explanations` accepts exactly `boundary_id`, `run_id`, `requirement_result_id`, `requirement_id`, and UUID `client_request_id`. It rejects unknown fields and performs one authoritative four-ID join before inserting an idempotent `nist_evidence_explanation` workflow request. Migration `0038` changes only the existing workflow CHECK constraint; the current claim, lease, lifecycle, result, retention, and owner-polling machinery is reused.

The worker dispatches this workflow directly to an isolated NIST explanation service. It does not call `run_workflow`, planner, conversation preparation/completion, tools, collectors, events, or source health. The service repeats the four-ID join, retrieves up to 26 persisted references, supplies 25, and reports database total, supplied count, aggregate omissions, and truncation. Revalidation protects queued jobs from malformed or substituted payloads.

### Local bounded synthesis with total-response rejection

The service calls `AiGateway.generate` with the existing `fast_triage` profile and `text_generation` capability. The prompt is JSON-structured, server-authored, redacted, capped below the profile prompt limit, and requests one small JSON object containing only `summary`, `why_it_matters`, `limitations`, `additional_evidence_needed`, and `citation_ids`.

Validation permits no unknown fields, bounds every string/list, requires citation IDs to be a subset of supplied NIST evidence-reference IDs, rejects introduced identifiers and prohibited compliance/satisfaction language, and checks deterministic status, confidence, mapping, truncation, and operational-classification claims. Deterministic fields are never model-owned. Parse, schema, grounding, provider, or contradiction failure discards all prose and persists a safe `explanation_unavailable` result. No repair loop is added.

### Safe audit and failure isolation

The enqueue route audits queued, duplicate, and binding-rejected outcomes with IDs only. The worker audits completed, rejected, unavailable, and failed outcomes with whitelisted provider/token/latency/reference metadata. It never logs prompts, model prose, raw evidence, request payloads, or secrets. Existing Analyst+ and super-admin RBAC remains authoritative, and request polling remains owner-bound.

## Risks / Trade-offs

- [A small model emits subtle overclaiming] → use a narrow schema, deterministic server block, lexical/identity/semantic guards, and discard the entire response on any validation doubt.
- [Async worker changes affect generic workflows] → add one explicit dispatch branch and bypass conversation preparation for only the isolated workflow; retain existing behavior for every other workflow.
- [Run-history timestamps tie] → use the `(created_at, id)` cursor while letting the existing index constrain boundary and time; no new index is justified for persisted run volume.
- [AI or worker is unavailable] → preserve all deterministic UI data and render a clear explanation-unavailable state without retry loops or fallback providers.
- [A boundary is edited after a run] → bind explanation to immutable run/result/reference records and use the boundary only for ownership identity, not as model-authored scope evidence.
- [Frontend polling completes after selection changes] → compare all four returned binding values with the active selection before rendering.

## Migration Plan

1. **Mac AI:** add migration `0038`, schema snapshot, backend/worker/service changes, frontend workspace, and offline tests.
2. **Mac AI:** run strict OpenSpec validation, migration/schema tests, PostgreSQL suites, frontend tests/build/visual review, compilation, and diff checks without provider calls.
3. **VM AI after explicit authorization:** clean-tree sync an approved commit, dry-run/apply migration through the deployment helper, restart backend and Anakin worker units, and verify health/security gates.
4. **VM AI:** deploy the built frontend and verify the browser path with one authorized local-Ollama explanation plus failure-state checks. This production acceptance is not part of Mac implementation.

Rollback application/frontend source while leaving the additive workflow enum constraint in place. Existing queued workflow rows and NIST records remain preserved.

## Open Questions

None. Production behavior remains unverified until separately authorized browser-path acceptance.
