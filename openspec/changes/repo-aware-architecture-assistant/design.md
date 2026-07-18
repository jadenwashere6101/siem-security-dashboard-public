## Context

Phase 1A provides the provider-neutral `AiGateway`, local-first routing, status vocabulary, timeouts, and request metadata. Phase 1B adds read-only SIEM explanation/chat endpoints and shared AI response patterns for analyst workflows. Phase 2 must reuse those contracts but answer a different class of question: internal repository architecture and maintenance questions such as where detection rules live, how incident state changes flow, which files affect a feature, and which project policies govern a proposed change.

The repository contains mixed-trust material. Current source files, `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, `schema.sql`, `migrations/`, tests, active OpenSpecs, accepted specs under `openspec/specs/`, `openspec/config.yaml`, and current docs indexes/runbooks are useful grounding sources. Some docs are explicitly historical or stale: `docs/internal-ai-notes/ARCHITECTURE_DISCOVERY_REPORT.txt` describes a pre-`create_app()` backend, `docs/MODULARIZATION_HANDOFF.md` still references old `backend_*` filenames despite noting modularization completion, archived OpenSpecs are useful history but not current requirements, and generated Sonar exports/build/cache files should not drive architecture answers.

The current auth model has `super_admin`, `admin`, `analyst`, and `viewer`. Phase 1B analyst chat is intentionally scoped to SIEM data. Repo-aware answers may expose source layout, internal policy, deployment rules, and implementation details, so they should not be available through the floating analyst chat.

## Goals / Non-Goals

**Goals:**

- Add a read-only repo-aware architecture assistant grounded in current repository files.
- Define canonical source hierarchy, include/exclude paths, stale-content handling, and citation rules.
- Reuse `AiGateway.generate()` and standard metadata for provider/model/cost/latency/fallback reporting.
- Implement retrieval without fine-tuning, schema migrations, vector database dependencies, shell execution, or background indexing.
- Provide a separate internal developer surface or route, protected more tightly than analyst AI chat.
- Return source-cited answers and safe insufficient-evidence responses.
- Add focused tests for retrieval trust rules, citation coverage, freshness, and read-only behavior.

**Non-Goals:**

- Analyst triage or SOC investigation assistance; Phase 1B already owns that.
- AI tool calling, arbitrary shell/code execution, database access, file writes, commits, pushes, deployment, or VM access.
- Autonomous repo cleanup or broad documentation rewrites.
- Fine-tuning, embeddings service setup, persistent vector stores, or schema migrations.
- Persisted chat history or model memory.
- Treating archived specs, generated reports, or old handoffs as current truth.

## Decisions

### Create a separate repo assistant service, not another analyst chat mode

Add backend modules under `core/ai`:

- `core/ai/repo_sources.py`: source allowlist/exclusion/trust policy and file metadata.
- `core/ai/repo_index.py`: lightweight repository scanner, chunker, cache, and lexical retriever.
- `core/ai/repo_assistant_service.py`: request validation, retrieval orchestration, prompt construction, gateway invocation, citation enforcement, and response mapping.

Extend `routes/ai_routes.py` with thin internal endpoints:

- `GET /ai/repo/status`
- `POST /ai/repo/chat`

Protect both with `login_required` and `super_admin_required`. Do not expose this through Phase 1B floating chat. Add a separate super-admin-only developer/admin panel such as `RepoArchitectureAssistantPanel`, reusing `AiResponsePanel` display pieces where practical but not reusing SIEM visible-context chat.

Alternative considered: add a "repo mode" to the floating SIEM chat. Rejected because the floating chat is analyst-facing and grounded in SIEM data, while repo assistance includes source policy and developer workflow context.

Alternative considered: CLI-only tool. Rejected for this phase because the roadmap calls for a reusable assistant capability and the existing app already has authenticated AI patterns. The backend service may still be testable without the browser, but the planned user surface is a separate super-admin developer panel.

### Use allowlisted, trust-tiered repository retrieval

The assistant SHALL retrieve only from configured repository paths. Initial trust tiers:

- Tier 0 authoritative policy: `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, `openspec/config.yaml`, `openspec/spec-index.md`.
- Tier 1 current implementation truth: tracked Python/JS source under `core/`, `routes/`, `engines/`, `helpers/`, `adapters/`, `integrations/`, `scripts/`, `frontend/src/`, `siem_backend.py`, `schema.sql`, `migrations/`, and focused tests under `tests/` and `frontend/src/**/*.test.js`.
- Tier 2 active/current specs and docs: non-archived `openspec/changes/*/{proposal,design,tasks,specs/**/*.md}`, accepted `openspec/specs/**/*.md`, `README.md`, `docs/soar_docs_index.md`, current runbooks referenced by that index, `docs/openapi.yaml`, and active architecture/runbook docs that are not marked historical.
- Tier 3 historical/context-only: archived OpenSpecs, `docs/*_vm_handoff.md`, `docs/internal-ai-notes/*`, old roadmaps, decomposition plans, cleanup plans, and migration handoff notes. These MAY be retrievable only when the user explicitly asks for historical context and MUST be labeled historical.
- Excluded: `.git/`, `__pycache__/`, `.pytest_cache/`, `frontend/build/`, `node_modules/`, generated Sonar JSON/CSV, screenshots/images, temporary files, `.env*`, private keys, logs, runtime artifacts, and files above the size limit.

If Tier 0 conflicts with any other source, Tier 0 wins. Current source code beats docs for implemented behavior. Active/accepted OpenSpecs beat archived OpenSpecs for requirements. Historical docs cannot override current source or current policy.

Alternative considered: index every text file and rely on the model to sort it out. Rejected because this repo intentionally retains many historical handoffs and generated reports that would produce confident but wrong answers.

### Retrieval uses deterministic lexical search and citations first

Phase 2 SHALL NOT require fine-tuning or embeddings. Implement a deterministic lexical retriever:

- scan allowlisted files from the Mac repository root;
- chunk text by headings/functions/classes where practical, otherwise by bounded line windows;
- attach metadata: path, line start/end, trust tier, source kind, mtime, content hash, and historical/current label;
- score with keyword/BM25-style matching plus path/source boosts for Tier 0/Tier 1 and exact symbol/path matches;
- return a bounded top-k context set to the prompt.

Keep an in-process index cache keyed by file path, mtime, size, and content hash. Refresh synchronously on request when tracked metadata changes or when the caller requests refresh. Do not run a background indexer.

Alternative considered: persistent vector DB. Rejected for Phase 2 because it adds operational state, freshness risk, and deployment complexity before the corpus and use cases justify it.

### Answer contract requires citations and insufficient-evidence behavior

`POST /ai/repo/chat` request:

```json
{
  "message": "Where do detection rules live?",
  "client_history": [],
  "refresh": false
}
```

Response:

```json
{
  "status": "success",
  "answer": "...",
  "insufficient_evidence": false,
  "citations": [
    {
      "path": "engines/detection_rule_catalog.py",
      "line_start": 1,
      "line_end": 40,
      "trust_tier": 1,
      "source_kind": "source",
      "label": "current"
    }
  ],
  "retrieval": {
    "indexed_files": 123,
    "matched_chunks": 6,
    "refreshed": false,
    "excluded_matches": []
  },
  "metadata": {}
}
```

The service prompt SHALL require the model to answer only from supplied repository excerpts, cite sources by path and line range, identify uncertainty, and prefer "I do not have enough current evidence" over speculation. The service SHALL return an insufficient-evidence response without calling the gateway when retrieval finds no current allowed sources. If a model response lacks citations or cites sources not supplied to it, the service SHALL fail closed with a grounding error instead of presenting the answer as current truth.

### Prompt policy prioritizes project safety rules

Every repo-assistant prompt SHALL include a short policy preamble summarizing:

- Mac is the development/source-of-truth repository; VM is runtime/deployment only.
- Do not commit, push, deploy, access VM, mutate production, run shell, or edit files through this assistant.
- Preserve RBAC, audit logging, idempotency, protected-target checks, fail-closed guards, secret safety, and simulation-vs-real outcome distinctions.
- Current source and Tier 0 policy beat stale docs and archived specs.

Do not include full file contents for policy documents unless retrieved by the normal trust-ranked search. This keeps prompts bounded while still enforcing safety.

### Optional focused documentation corrections are allowed

Implementation MAY add narrow markers or corrections only when a currently included doc would confuse retrieval. Preferred corrections:

- add a short "Historical / do not treat as current architecture" note to stale docs;
- add/update an index entry that points to current source-of-truth docs;
- do not rewrite broad handoff documents or archive content.

Any doc correction must be listed in tasks and tested or reviewed as part of retrieval trust behavior.

### File-level implementation plan

Expected backend files:

- Create `core/ai/repo_sources.py`.
- Create `core/ai/repo_index.py`.
- Create `core/ai/repo_assistant_service.py`.
- Modify `routes/ai_routes.py`.
- Modify `siem_backend.py` only if a separate blueprint is chosen instead of extending `ai_bp`.
- Add `tests/test_repo_aware_architecture_assistant.py`.

Expected frontend/internal tool files:

- Create `frontend/src/services/repoAssistantService.js` and tests.
- Create `frontend/src/components/RepoArchitectureAssistantPanel.js` and tests.
- Modify `frontend/src/App.js` only to add a super-admin-only developer/admin panel entry.
- Reuse `AiResponsePanel`/metadata display where practical.

Expected docs:

- Optional focused stale-doc markers only where implementation proves retrieval confusion.

## Risks / Trade-offs

- [Stale docs override current behavior] -> Use trust tiers, exclude/archive rules, conflict policy, and tests that ask about known stale areas.
- [No embeddings reduces semantic recall] -> Use path/symbol boosts, heading/function chunking, multi-query keyword expansion, and cite insufficient evidence when matches are weak.
- [Repo contents expose sensitive implementation details] -> Restrict to `super_admin`, exclude secrets/runtime artifacts, and avoid analyst chat integration.
- [Freshness drift from cached index] -> Cache by mtime/size/hash and support explicit refresh; no persistent stale index.
- [Model fabricates citations] -> Validate citations against retrieved chunks before returning success.
- [Feature becomes an AI coding agent] -> Keep endpoints read-only and deny shell, file writes, DB access, commits, pushes, VM work, and deployment.
- [Prompt size grows too large] -> Apply chunk/top-k limits and return insufficient evidence rather than overstuffing prompts.

## Migration Plan

1. Implement backend repo source policy, retriever, assistant service, and thin routes in the Mac repository only.
2. Add focused backend tests for source inclusion/exclusion, stale/historical handling, retrieval freshness, citations, RBAC, gateway metadata, and read-only behavior.
3. Add the super-admin-only developer panel and focused service/component tests; run the frontend build.
4. Run Python compilation, focused tests, `git diff --check`, and `openspec validate repo-aware-architecture-assistant --strict`.
5. No VM work occurs during implementation. If backend/frontend runtime changes are later approved and deployed, VM sync will be required as a separate deployment task.

Rollback is code-only: remove the repo assistant routes/modules and optional UI entry. No database rollback is expected.

## Future Phase Dependencies

Phase 3 read-only SOC tools can reuse the trust/citation pattern for tool result provenance, but not the repo corpus. Phase 4 drafting can reuse source-cited architecture answers to inform draft explanations while still keeping draft generation separate from execution. Phase 5 approval-gated actions can reuse the safety-policy preamble and citation validation to explain why a proposed change is allowed or blocked.

## Open Questions

- Should the external Desktop AI roadmap be copied into a repository doc later if it should be queryable? Phase 2 retrieval is repository-scoped, so external Desktop files are not indexed by default.
