## ADDED Requirements

### Requirement: Repo-aware assistant is read-only and developer-scoped
The system SHALL provide a repo-aware architecture assistant for internal development questions and SHALL NOT expose it through analyst SIEM chat, mutate files, execute shell commands, access the database, commit, push, deploy, access the VM, or modify production/runtime state.

#### Scenario: Super administrator asks a repository question
- **WHEN** a super administrator submits a valid repo-assistant question
- **THEN** the system retrieves allowed repository context, calls the Phase 1A AI gateway, and returns a source-cited answer with standard AI metadata

#### Scenario: Analyst chat does not access repository corpus
- **WHEN** an analyst uses the Phase 1B floating SIEM chat
- **THEN** the request is grounded only in SIEM visible/context-builder data and does not query repository source, specs, schemas, tests, or internal docs

#### Scenario: Assistant performs no repo mutation
- **WHEN** a repo-assistant request is handled
- **THEN** the backend does not write files, run shell commands, call database connections, commit, push, deploy, access the VM, or invoke production mutation paths

### Requirement: Repo assistant access is restricted to super administrators
The system SHALL protect repo-assistant routes and UI with existing authentication and super-admin authorization patterns.

#### Scenario: Super administrator can access repo assistant
- **WHEN** an authenticated super administrator opens the developer assistant panel or calls the repo-assistant route
- **THEN** the UI and backend allow the read-only request

#### Scenario: Analyst is rejected
- **WHEN** an authenticated analyst attempts to access the repo-assistant route or panel
- **THEN** existing authorization behavior rejects or hides the capability

#### Scenario: Viewer or unauthenticated user is rejected
- **WHEN** a viewer or unauthenticated user attempts to access the repo-assistant route or panel
- **THEN** existing authentication or authorization behavior rejects or hides the capability

### Requirement: Canonical repository source hierarchy
The system SHALL apply explicit repository source trust tiers before retrieving context for answers.

#### Scenario: Policy source wins over conflicting sources
- **WHEN** `AGENTS.md`, `docs/mac-vm-source-of-truth-policy.md`, `openspec/config.yaml`, or `openspec/spec-index.md` conflicts with lower-tier docs
- **THEN** the assistant treats the Tier 0 policy source as authoritative and explains the conflict with citations

#### Scenario: Current source wins for implemented behavior
- **WHEN** current source code conflicts with planning docs or handoffs about implemented behavior
- **THEN** the assistant treats current tracked source and focused tests as stronger evidence for what the application currently does

#### Scenario: Active specs win over archived specs
- **WHEN** active or accepted OpenSpec content conflicts with archived OpenSpec content
- **THEN** the assistant treats active changes and `openspec/specs/` as current requirements and labels archived content as historical

### Requirement: Repository source inclusion and exclusion policy
The system SHALL retrieve only allowlisted repository files and SHALL exclude generated, secret-bearing, runtime, cache, build, and unsafe paths.

#### Scenario: Current implementation files are eligible
- **WHEN** a repo-assistant question matches current source code, migrations, schema, tests, active specs, accepted specs, or current docs
- **THEN** the retriever may include bounded chunks from those files with path, line, trust-tier, and source-kind metadata

#### Scenario: Secret and runtime files are excluded
- **WHEN** files such as `.env`, private keys, logs, runtime artifacts, `.git`, caches, `node_modules`, or `frontend/build` match a query
- **THEN** the retriever excludes them and never sends their contents to the AI gateway

#### Scenario: Generated Sonar exports are excluded by default
- **WHEN** a repo-assistant query matches generated Sonar JSON, CSV, or large report export files
- **THEN** the retriever excludes them from normal architecture answers unless a future dedicated Sonar-analysis change explicitly allows them

### Requirement: Historical and stale content is labeled or excluded
The system SHALL prevent obsolete handoff docs, archived OpenSpecs, and historical notes from being presented as current truth.

#### Scenario: Historical context is explicitly requested
- **WHEN** a super administrator explicitly asks for historical context
- **THEN** the assistant may retrieve historical or archived sources but labels them as historical and does not use them to override current sources

#### Scenario: Historical context is not requested
- **WHEN** a normal current-architecture question matches both current and historical sources
- **THEN** the assistant prioritizes current sources and either excludes historical sources or identifies them only as lower-trust background

#### Scenario: Stale current doc would confuse retrieval
- **WHEN** an included current doc is proven to contain stale guidance that would mislead repo retrieval
- **THEN** implementation may add a narrow historical/stale marker or index correction without rewriting unrelated documentation

### Requirement: Retrieval does not require fine-tuning or persistent vector storage
The system SHALL implement deterministic repository retrieval without fine-tuning, embeddings services, persistent vector databases, schema migrations, or background index jobs.

#### Scenario: Query retrieves bounded chunks
- **WHEN** a repo-assistant question is submitted
- **THEN** the retriever scans or refreshes the allowlisted index, scores bounded chunks using deterministic lexical/path/symbol matching, and returns a limited context set

#### Scenario: Index refresh is on-demand
- **WHEN** indexed file metadata changes or the request asks for refresh
- **THEN** the retriever refreshes affected file chunks synchronously and records refresh metadata in the response

#### Scenario: No background indexing runs
- **WHEN** the backend application starts
- **THEN** the repo assistant does not start recurring background indexing or make AI provider calls

### Requirement: Source citations and freshness metadata
The system SHALL return citations and retrieval freshness metadata for every successful repo-assistant answer.

#### Scenario: Answer includes citations
- **WHEN** the assistant returns a successful answer
- **THEN** the response includes citations with repository path, line start, line end, trust tier, source kind, and current-or-historical label

#### Scenario: Retrieval metadata is returned
- **WHEN** a repo-assistant response is returned
- **THEN** the response includes retrieval metadata such as indexed file count, matched chunk count, refresh state, and excluded-match summaries without exposing excluded file contents

#### Scenario: Local provider metadata is preserved
- **WHEN** the Phase 1A gateway handles the repo-assistant prompt with a local provider
- **THEN** the response preserves metadata showing provider, model, latency, local request state, `paid_request=false`, and zero estimated API cost

### Requirement: Grounded insufficient-evidence behavior
The system SHALL refuse or fail closed when allowed current sources do not provide enough evidence for an answer.

#### Scenario: No allowed evidence is found
- **WHEN** retrieval finds no allowed current repository sources relevant to the question
- **THEN** the service returns `insufficient_evidence=true` without calling the AI gateway

#### Scenario: Model answer lacks valid citations
- **WHEN** the AI gateway returns answer text without citations that match the retrieved source set
- **THEN** the service returns a grounding failure or insufficient-evidence response instead of presenting the uncited answer as current truth

#### Scenario: Conflicting evidence is found
- **WHEN** retrieved sources disagree about the answer
- **THEN** the assistant identifies the conflict, cites both sides, and applies trust-tier rules rather than silently choosing stale or lower-trust evidence

### Requirement: Prompt and logging remain secret-safe
The system SHALL redact sensitive values, exclude secret-bearing files, and avoid logging prompt text, chat history, retrieved file contents, credentials, or credential-bearing URLs.

#### Scenario: Sensitive file is matched by query
- **WHEN** a query matches a path or key that appears secret-bearing
- **THEN** the retriever excludes the file or redacts the value before prompt construction

#### Scenario: Repo-assistant request is logged
- **WHEN** the backend logs a repo-assistant request or failure
- **THEN** logs contain only safe metadata such as actor, route, status, retrieval counts, and error code, not prompt text, retrieved chunks, secrets, or full file contents

### Requirement: Developer UI is separate from analyst AI surfaces
The frontend SHALL provide a separate super-admin-only developer panel for repo-aware architecture questions and SHALL NOT add repo-aware behavior to contextual analyst AI buttons or the floating SIEM chat.

#### Scenario: Super admin sees developer panel
- **WHEN** a super administrator is authenticated
- **THEN** the UI exposes a clearly labeled repo-aware architecture assistant surface separate from analyst investigation screens

#### Scenario: Analyst AI surfaces remain SIEM-focused
- **WHEN** an analyst uses dashboard, alert, incident, source-IP, recon, response-registry, or floating SIEM AI controls
- **THEN** those controls continue to call Phase 1B SIEM explanation/chat contracts and do not retrieve repository files

#### Scenario: Developer panel shows citations and metadata
- **WHEN** a repo-assistant answer is displayed
- **THEN** the UI shows answer text, citations, trust/freshness labels, provider/model/latency/cost metadata, loading state, retry, cancellation, and safe failure states

### Requirement: Phase 2 excludes code changes by AI and autonomous assistance
The repo-aware assistant SHALL answer and explain only; it SHALL NOT generate executable tools that change the repository or act autonomously.

#### Scenario: User asks assistant to modify code
- **WHEN** a repo-assistant question asks it to edit files, commit, push, deploy, run commands, or access the VM
- **THEN** the assistant refuses within the repo-assistant response and may explain which manual/OpenSpec workflow should be used instead

#### Scenario: User asks where to implement a change
- **WHEN** a repo-assistant question asks which files or policies are relevant to a proposed change
- **THEN** the assistant may cite current files and policies and recommend investigation areas without modifying anything
