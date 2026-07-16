## Context

The repo already contains several useful ingredients for this change:

- alert Severity remains the main danger signal;
- source-IP context already provides historical alert, incident, queue, blocklist, reputation, execution, and outcome context;
- recon activities already exist for distributed pfSense reconnaissance;
- incidents already support timeline, linked alerts, and status transitions;
- analyst-facing rule metadata already includes investigation guidance.

The problem is that these ingredients do not yet combine into one clear analyst-priority model. Severity still does too much work. Returning-attacker evidence is visible but not organized as investigation context. Campaign evidence exists only in narrow forms. Recon Activities are present but still secondary. Many labels still force analysts to translate security shorthand instead of understanding the operational meaning at first glance.

This change is intentionally about investigation quality, prioritization, and wording clarity. It must not expand alert volume just to surface more intelligence.

## Goals / Non-Goals

**Goals**

- Define an explainable Investigation Value model that answers "Why should I investigate this first?"
- Keep Severity as the danger signal and avoid turning Investigation Value into a disguised replacement for Severity.
- Make campaign intelligence target-centered and durable enough to become an investigation object.
- Treat returning attackers as investigation context, not as standalone alerts.
- Redesign incident ownership, merging, and closure so analysts receive fewer, smarter cases.
- Make Recon Activities naturally discoverable and useful in normal analyst workflow.
- Make Port Scan and Allow After Deny understandable at a glance through better explanation, not detector proliferation.
- Apply a repo-wide wording rule for scoped affected analyst surfaces: if an analyst cannot understand it at a glance, reword it in plain English without expanding the UI into long prose.

**Non-Goals**

- No new family of repeat-IP alerts.
- No broad UI redesign, shell redesign, or dashboard rebuild.
- No threat-intelligence platform replacement.
- No complex AI-generated explanations, opaque scoring, or unexplained confidence numbers.
- No implementation, deployment, commit, or VM work in this spec-authoring step.

## Design Principles

### 1. At-a-glance understanding is mandatory

Every new score, badge, label, campaign indicator, or workflow hint must be understandable at a glance. The system should prefer short plain-English explanations over security shorthand. "Port Scan / Medium" is insufficient if the analyst still cannot tell whether it is routine background noise, persistent recon, progression-backed behavior, or a campaign member.

This does not justify adding paragraphs everywhere. It justifies rewording unclear UI and metadata wherever the scoped implementation touches analyst-facing surfaces.

### 2. No mysterious numbers

Investigation Value and any separate analyst confidence indicator must expose the reasons behind their state. The system must not emit unexplained scores, AI labels, or urgency badges with no visible basis.

### 3. Existing alerts should become smarter before the system creates more alerts

The default design response to missing context must be enrichment, ranking, linkage, aggregation, or wording improvement. New alert creation requires stronger justification than new investigation context.

### 4. Campaign evidence should center on the target, not only the source

Returning IPs matter, but repeated destination targeting, repeated services, recurrence across days, progression, and campaign membership matter more operationally. The campaign object should explain what the environment is receiving, not just who sent one event.

## Architecture

### Logical Model

The proposed architecture adds a lightweight investigation-intelligence layer on top of existing alerts, incidents, source-IP context, and recon activities.

```text
Events / Alerts / Correlation
          |
          v
Existing alert + context + incident + recon objects
          |
          +--> Investigation Value model
          |
          +--> Campaign intelligence model
          |
          +--> Returning-attacker context model
          |
          +--> Incident intelligence model
          |
          +--> Plain-English analyst presentation model
```

### Data Responsibilities

- **Severity** remains a detector-authored risk or danger label.
- **Investigation Value** becomes an analyst-priority model derived from explainable factors.
- **Analyst confidence** remains optional and only exists if it improves comprehension more than it adds complexity.
- **Campaign intelligence** links related activity into a target-centered object with visible evidence.
- **Returning-attacker context** summarizes prior behavior and prior analyst interaction without becoming an alert on its own.
- **Incident intelligence** decides whether an investigation should become a case, merge into a case, stay aggregate-owned, or auto-close.

### Suggested additive components for later implementation

- Investigation-priority evaluator in `core/` or `engines/`
- Campaign or target-activity persistence/read model extending the existing recon-activity and source-IP patterns
- Additive incident-intelligence policy helper near `core/incident_store.py`
- Additive analyst-facing projection helpers for plain-English labels, badge reasons, and "why this deserves attention" summaries

## Decisions

### 1. Investigation Value remains separate from Severity

Severity answers "How dangerous is this?" Investigation Value answers "Why should I investigate this first?" The model should consume Severity as one input, not inherit it as the full answer.

Recommended Investigation Value factors:

- progression
- persistence
- campaign evidence
- recurrence across days
- repeated destination targeting
- repeated services
- corroboration
- destination importance
- response history
- campaign membership
- repeated analyst interest when already recorded in the product

The value should change as evidence accumulates. It should not be a static one-time label.

### 2. Analyst confidence is optional and must earn its place

The spec should allow a separate analyst confidence signal only if it explains something different from Severity and Investigation Value. The most defensible use is confidence in the interpretation of the investigative story, not confidence that "the detector fired."

If included, confidence must be reason-based, such as:

- high because progression and corroboration are present
- medium because recurrence exists but coordination is not established
- low because the activity is routine commodity recon with little destination-specific evidence

If that distinction cannot be made cleaner than the existing fields, the system should omit analyst confidence entirely.

### 3. Campaigns become durable investigation objects

Campaigns should not be inferred only from one IP reappearing. They should become durable investigation objects centered on:

- shared protected target or target range
- repeated services
- recurrence across multiple days
- progression
- repeated timing patterns or beacon-like cadence
- subnet or ASN relationships when they materially help
- rotating attacker infrastructure

The campaign object should expose both current evidence and why the system believes those activities belong together.

### 4. Returning attackers become context, not alerts

Returning attackers should enrich alerts, campaigns, recon activities, and incidents through fields such as:

- first seen
- last seen
- days observed
- prior incidents
- prior responses
- prior campaign membership
- repeated destination targeting
- repeated services

This context should raise Investigation Value when appropriate, but should not produce a new standalone "returning IP" alert.

### 5. Incident ownership must become more selective

The incident system should distinguish:

- source-specific progression that deserves a case;
- campaign-level activity that deserves one aggregate or campaign-owned case;
- commodity background recon that should remain visible without becoming a case;
- stale or unprogressed investigations that should auto-close or remain out of incident scope.

The current `HIGH -> P2`, `CRITICAL -> P1` mapping is too coarse for analyst workflow and should be replaced by a smarter priority model while preserving understandable P-levels.

### 6. Recon Activities become first-class workflow objects

Recon Activities should no longer feel like a side surface. Analysts should be able to discover them naturally from alerts, incidents, source-IP context, and SOC operational views. They should carry campaign relationships, history, and plain-English summaries that explain whether the activity is routine, persistent, coordinated, progression-backed, or still unproven.

### 7. Port Scan explanation is a workflow problem, not a detector problem

The detector can remain. The analyst-facing experience should change to answer questions like:

- Is this routine internet recon?
- Is the source persistent?
- Is the same destination or service being revisited?
- Is there any progression?
- Is this part of a broader campaign?
- Is this likely background noise or something that deserves review now?

### 8. Allow After Deny should enrich campaign understanding before it creates new alerts

Allow After Deny already represents stronger source-specific progression. The next improvement should focus on whether the same destination was probed or denied by multiple unrelated IPs before a later allow. That evidence should strengthen campaign or incident context first. Additional alerts should only be proposed if enrichment proves insufficient.

## Proposed Capability Boundaries

### Capability 1: Investigation Value And Confidence

Defines explainable analyst-priority modeling and optional analyst-confidence modeling.

### Capability 2: Campaign Intelligence And Returning Attackers

Defines target-centered campaign tracking, returning-attacker context, and cross-day recurrence patterns without alert multiplication.

### Capability 3: Incident Intelligence And Recon Workflow

Defines smarter incident ownership, merging, closure, and first-class Recon Activity workflow behavior.

### Capability 4: Port Scan And Allow After Deny Experience

Defines analyst-facing explanation, disposition wording, and campaign enrichment around Port Scan and Allow After Deny.

## Expected Files For A Later Implementation

- `core/incident_store.py`
- `core/recon_activity_store.py`
- `core/pfsense_recon.py`
- `routes/incident_routes.py`
- `routes/alerts_events_routes.py`
- `routes/source_ip_context_routes.py`
- `engines/detection_rule_catalog.py`
- `engines/severity_response_matrix.py`
- `frontend/src/components/AlertsTable.js`
- `frontend/src/components/AlertDetailsPanel.js`
- `frontend/src/components/IncidentsPanel.js`
- `frontend/src/components/SocCommandCenter.js`
- `frontend/src/components/SourceIpContext.js`
- `frontend/src/services/reconActivityService.js`
- `frontend/src/services/sourceIpContextService.js`
- focused tests in `tests/` and `frontend/src/**/*.test.js`

The exact implementation file set may narrow or expand slightly, but the later implementation should stay within these investigation-intelligence surfaces.

## Implementation Phases

### Phase 1: Investigation-priority foundation

Define the Investigation Value model, optional analyst confidence model, reasoning exposure contract, and plain-English presentation rules.

### Phase 2: Campaign and returning-attacker intelligence

Add target-centered campaign evidence, recurrence tracking, returning-attacker context, and campaign membership exposure.

### Phase 3: Incident intelligence

Refine incident creation, merging, aggregate ownership, P-level assignment, and auto-closure behavior.

### Phase 4: Recon workflow and analyst-language pass

Promote Recon Activities in workflow, improve Port Scan and Allow After Deny explanation, and reword scoped unclear labels so analysts can understand them at a glance.

## Risks / Trade-offs

- **[Investigation Value duplicates Severity]** → Keep separate questions and visible reasons; do not let Severity silently dominate the model.
- **[Campaign logic becomes overbuilt]** → Reuse existing recon and source-context patterns; avoid a generic threat-intel platform.
- **[Analyst confidence becomes another opaque number]** → Make it optional and drop it if it does not remain explainable.
- **[Plain-English wording becomes too verbose]** → Require short, direct phrasing and avoid adding paragraphs where a reworded label is enough.
- **[Incident complexity grows faster than analyst value]** → Prioritize fewer, smarter cases and additive policy logic instead of a new case-management system.
- **[New context still increases alert noise indirectly]** → Prefer enrichment on existing objects and aggregate ownership over creating new alerts.

## Validation Plan

- `openspec validate analyst-investigation-intelligence --strict`
- Ensure every capability spec exposes explainable reasoning rather than opaque scoring.
- Verify the tasks stay within investigation-quality scope and do not introduce detector-expansion work by default.
- During a later implementation pass, require focused regression tests for any changed scoring, routing, read models, and wording-sensitive UI projections.
- During a later implementation pass, require `git diff --check` before handoff.

## Success Criteria

- Analysts can distinguish danger from urgency because Severity and Investigation Value answer different questions.
- Returning-attacker context improves analyst decisions without creating repeat-IP alert spam.
- Campaigns become explainable investigation objects centered on target evidence and recurrence.
- Incident volume and P2 inflation decrease while genuinely actionable work becomes more visible.
- Recon Activities become discoverable and useful as normal analyst workflow objects.
- Port Scan and Allow After Deny become understandable at a glance through clearer explanation and visible reasoning.
- Scoped UI and wording touched by this change can be understood at a glance without documentation and without adding long explanatory paragraphs.

