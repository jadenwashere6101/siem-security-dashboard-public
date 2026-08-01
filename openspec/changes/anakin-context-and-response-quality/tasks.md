## 1. OpenSpec

- [x] 1.1 Create proposal, design, spec, and tasks for `anakin-context-and-response-quality`.
- [x] 1.2 Validate the OpenSpec strictly before implementation handoff.

## 2. Backend Context Bounding

- [x] 2.1 Add compact evidence packaging helpers and metadata for included/omitted/truncated evidence.
- [x] 2.2 Bound alert, source-IP, incident, recon activity, response-registry, dashboard, and general context before prompt serialization.
- [x] 2.3 Remove raw-object and duplicate-data prompt serialization for large context types.
- [x] 2.4 Apply selected profile prompt limits consistently in explain, chat, draft, and guided investigation services.

## 3. Profile And Prompt Quality

- [x] 3.1 Reassign correlation-heavy interactive actions to `guided_analysis`.
- [x] 3.2 Preserve fast, deep briefing, and developer assistant boundaries.
- [x] 3.3 Rewrite interactive prompts to require analytical value, contradiction/uncertainty/gaps, and concrete read-only next steps.
- [x] 3.4 Prevent client model/profile/timeout/context injection from affecting backend routing.

## 4. Frontend AI Workflow

- [x] 4.1 Stop adding full visible dashboard context to entity-specific actions.
- [x] 4.2 Keep dashboard/general chat visible context bounded and intentional.
- [x] 4.3 Use stable request identity based on action, context type, mode, and entity identifier.
- [x] 4.4 Keep read-only stale responses visible with advisory stale state while preserving strict stale blocking for confirmable previews.

## 5. Tests And Acceptance Coverage

- [x] 5.1 Add authoritative in-scope action inventory/profile/bounded-context tests.
- [x] 5.2 Add oversized fixture tests proving recon/source-IP/incident/registry prompts stay within selected profile limits with accurate metadata.
- [x] 5.3 Add integration-style backend contract tests tracing route → context builder → profile → prompt → response metadata.
- [x] 5.4 Add frontend tests for payload shape and stale advisory behavior.
- [x] 5.5 Add prompt-quality tests for anti-repetition and useful-evidence requirements.

## 6. Verification

- [x] 6.1 Run Python compilation for modified modules.
- [x] 6.2 Run focused AI route/service/context/profile tests and affected regression batch.
- [x] 6.3 Run affected frontend component/service tests.
- [x] 6.4 Run frontend production build.
- [x] 6.5 Run `git diff --check`.
- [x] 6.6 Run `openspec validate anakin-context-and-response-quality --strict`.
- [x] 6.7 Run `openspec status --change anakin-context-and-response-quality`.
