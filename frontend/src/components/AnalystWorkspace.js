import React, { useEffect, useState } from "react";

import { Button, Card, Chip, Panel, SectionHeader, StatusPill } from "./uiPrimitives";
import { theme } from "../theme";

const STATUS_OPTIONS = ["open", "investigating", "awaiting_evidence", "ready_for_review", "resolved", "closed"];
const CONFIDENCE_OPTIONS = ["low", "medium", "high"];
const DISPOSITION_OPTIONS = ["undetermined", "true_positive", "false_positive", "benign_expected", "needs_monitoring", "escalated"];
const RELATIONSHIP_OPTIONS = ["supports", "refutes", "context"];

function AnalystWorkspace({
  workspaceState,
  activeInvestigationBundle,
  activeInvestigationId,
  loading,
  error,
  onRefresh,
  onSelectInvestigation,
  onUpdateInvestigation,
  onDeleteInvestigation,
  onCreateNote,
  onCreateHypothesis,
  onCreateTask,
  onRemovePin,
  onDeleteNote,
  onDeleteHypothesis,
  onDeleteTask,
  onUpdateTask,
  onUpdateEvidence,
  onDeleteEvidence,
  onLinkEvidenceToHypothesis,
  onUnlinkEvidenceFromHypothesis,
  onOpenEvidenceSource,
  actionBusy = "",
  actionStatus = null,
}) {
  const [noteDraft, setNoteDraft] = useState("");
  const [hypothesisDraft, setHypothesisDraft] = useState("");
  const [taskDraft, setTaskDraft] = useState("");
  const [taskLinkDraft, setTaskLinkDraft] = useState({ hypothesis_id: "", evidence_reference_id: "" });
  const [relationshipDrafts, setRelationshipDrafts] = useState({});
  const [evidenceRationaleDrafts, setEvidenceRationaleDrafts] = useState({});
  const investigations = workspaceState?.investigations || [];
  const activeInvestigation =
    activeInvestigationBundle?.investigation ||
    investigations.find((item) => String(item.id) === String(activeInvestigationId)) ||
    investigations[0] ||
    null;
  const activeId = activeInvestigation?.id || activeInvestigationId || null;

  const [investigationDraft, setInvestigationDraft] = useState(() => buildInvestigationDraft(activeInvestigation));

  useEffect(() => {
    if (!workspaceState && !loading && !error) onRefresh?.();
  }, [error, loading, onRefresh, workspaceState]);

  useEffect(() => {
    setInvestigationDraft(buildInvestigationDraft(activeInvestigation));
  }, [activeInvestigation]);

  useEffect(() => {
    const nextDrafts = {};
    (activeInvestigationBundle?.evidence || []).forEach((evidence) => {
      nextDrafts[evidence.id] = evidence.rationale || "";
    });
    setEvidenceRationaleDrafts(nextDrafts);
  }, [activeInvestigationBundle?.evidence]);

  if (loading) {
    return (
      <Panel aria-label="Analyst Workspace">
        <p style={mutedStyle}>Loading investigation workspace...</p>
      </Panel>
    );
  }

  if (error) {
    return (
      <Panel aria-label="Analyst Workspace">
        <SectionHeader eyebrow="Analyst Workspace" title="Investigation workspace" />
        <p style={errorStyle}>{error}</p>
        <Button onClick={onRefresh}>Retry</Button>
      </Panel>
    );
  }

  const workspace = workspaceState?.workspace;
  const bundle = activeInvestigationBundle || {};
  const notes = bundle.notes || [];
  const hypotheses = bundle.hypotheses || [];
  const tasks = bundle.tasks || [];
  const evidence = bundle.evidence || [];
  const links = bundle.hypothesis_evidence || [];
  const sourceContext = bundle.source_context || {};
  const timeline = buildDisplayTimeline(bundle.timeline || [], sourceContext);
  const unassigned = bundle.unassigned || workspaceState || {};
  const hasInvestigations = investigations.length > 0;
  const unresolvedTasks = tasks.filter((task) => task.status !== "done");
  const caveats = buildConclusionCaveats(activeInvestigation, unresolvedTasks);

  const relationshipByHypothesis = groupRelationships(links, evidence);

  const submitNote = () => {
    if (!noteDraft.trim() || !activeId) return;
    onCreateNote?.({ investigation_id: activeId, body: noteDraft.trim() });
    setNoteDraft("");
  };

  const submitHypothesis = () => {
    if (!hypothesisDraft.trim() || !activeId) return;
    onCreateHypothesis?.({ investigation_id: activeId, title: hypothesisDraft.trim(), confidence: "medium" });
    setHypothesisDraft("");
  };

  const submitTask = () => {
    if (!taskDraft.trim() || !activeId) return;
    onCreateTask?.({
      investigation_id: activeId,
      title: taskDraft.trim(),
      hypothesis_id: taskLinkDraft.hypothesis_id ? Number(taskLinkDraft.hypothesis_id) : null,
      evidence_reference_id: taskLinkDraft.evidence_reference_id ? Number(taskLinkDraft.evidence_reference_id) : null,
    });
    setTaskDraft("");
    setTaskLinkDraft({ hypothesis_id: "", evidence_reference_id: "" });
  };

  const updateRelationshipDraft = (hypothesisId, updates) => {
    setRelationshipDrafts((current) => ({
      ...current,
      [hypothesisId]: {
        relationship_type: "supports",
        evidence_reference_id: evidence[0]?.id || "",
        rationale: "",
        ...(current[hypothesisId] || {}),
        ...updates,
      },
    }));
  };

  const submitRelationship = (hypothesisId) => {
    const draft = {
      evidence_reference_id: evidence[0]?.id || "",
      relationship_type: "supports",
      rationale: "",
      ...(relationshipDrafts[hypothesisId] || {}),
    };
    if (!activeId || !hypothesisId || !draft.evidence_reference_id) return;
    onLinkEvidenceToHypothesis?.(activeId, {
      hypothesis_id: hypothesisId,
      evidence_reference_id: Number(draft.evidence_reference_id),
      relationship_type: draft.relationship_type || "supports",
      rationale: draft.rationale || "",
    });
  };

  const saveInvestigation = () => {
    if (!activeId) return;
    onUpdateInvestigation?.(activeId, {
      status: investigationDraft.status,
      confidence: investigationDraft.confidence,
      disposition: investigationDraft.disposition,
      summary: investigationDraft.summary,
      conclusion: investigationDraft.conclusion,
    });
  };

  return (
    <div data-navigation-target="analyst-workspace" aria-label="Analyst Workspace">
      <Panel style={panelStyle}>
        <SectionHeader
          eyebrow="Analyst Workspace"
          title="Investigation workspace"
          subtitle="Private analyst context for working an investigation. These records do not mutate alerts, incidents, SOAR, detections, or response state."
          actions={<Chip tone="info">{workspace?.visibility || "private"}</Chip>}
        />
        {actionStatus?.message ? (
          <div
            role={actionStatus.type === "error" ? "alert" : "status"}
            style={actionStatus.type === "error" ? actionErrorStyle : actionStatusStyle}
          >
            {actionStatus.message}
          </div>
        ) : null}

        {!hasInvestigations ? (
          <EmptyInvestigationState />
        ) : (
          <div style={workspaceLayoutStyle}>
            <aside aria-label="Saved investigations" style={railStyle}>
              <div style={railHeaderStyle}>
                <strong>Investigations</strong>
                <Chip tone="info">{investigations.length}</Chip>
              </div>
              <div style={railListStyle}>
                {investigations.map((investigation) => (
                  <button
                    key={investigation.id}
                    type="button"
                    onClick={() => onSelectInvestigation?.(investigation.id)}
                    aria-pressed={String(activeId) === String(investigation.id)}
                    style={{
                      ...investigationButtonStyle,
                      ...(String(activeId) === String(investigation.id) ? investigationButtonActiveStyle : null),
                    }}
                  >
                    <span style={titleTextStyle}>{investigation.title || `Investigation #${investigation.id}`}</span>
                    <span style={metaLineStyle}>{formatInvestigationContext(investigation)}</span>
                    <span style={badgeRowStyle}>
                      <StatusPill status={investigation.status}>{labelize(investigation.status)}</StatusPill>
                      <Chip tone="neutral">{labelize(investigation.disposition || "undetermined")}</Chip>
                    </span>
                  </button>
                ))}
              </div>
            </aside>

            <main aria-label="Active investigation" style={activeColumnStyle}>
              <ActiveInvestigationHeader
                investigation={activeInvestigation}
                sourceContext={sourceContext}
                actionBusy={actionBusy}
                onDeleteInvestigation={onDeleteInvestigation}
              />

              <Card style={storyCardStyle}>
                <div style={storyGridStyle}>
                  <StoryBlock title="Trigger context" label="Source fact">
                    <SourceContext sourceContext={sourceContext} investigation={activeInvestigation} />
                  </StoryBlock>
                  <StoryBlock title="What happened" label="Analyst-authored">
                    <textarea
                      aria-label="Investigation summary"
                      value={investigationDraft.summary}
                      onChange={(event) => setInvestigationDraft((current) => ({ ...current, summary: event.target.value }))}
                      rows={4}
                      style={textareaStyle}
                    />
                  </StoryBlock>
                  <StoryBlock title="Current assessment" label="Analyst-authored">
                    <div style={controlGridStyle}>
                      <SelectControl label="Status" value={investigationDraft.status} options={STATUS_OPTIONS} onChange={(status) => setInvestigationDraft((current) => ({ ...current, status }))} />
                      <SelectControl label="Confidence" value={investigationDraft.confidence} options={CONFIDENCE_OPTIONS} onChange={(confidence) => setInvestigationDraft((current) => ({ ...current, confidence }))} />
                      <SelectControl label="Disposition" value={investigationDraft.disposition} options={DISPOSITION_OPTIONS} onChange={(disposition) => setInvestigationDraft((current) => ({ ...current, disposition }))} />
                    </div>
                  </StoryBlock>
                  <StoryBlock title="Conclusion" label="Analyst-authored">
                    <textarea
                      aria-label="Investigation conclusion"
                      value={investigationDraft.conclusion}
                      onChange={(event) => setInvestigationDraft((current) => ({ ...current, conclusion: event.target.value }))}
                      rows={4}
                      style={textareaStyle}
                    />
                    {caveats.length ? (
                      <ul style={caveatListStyle}>
                        {caveats.map((caveat) => <li key={caveat}>{caveat}</li>)}
                      </ul>
                    ) : null}
                  </StoryBlock>
                </div>
                <div style={formActionsStyle}>
                  <Button
                    variant="primary"
                    onClick={saveInvestigation}
                    disabled={!activeId || actionBusy === `investigation:${activeId}`}
                  >
                    Save investigation updates
                  </Button>
                </div>
              </Card>

              <div style={workGridStyle}>
                <Card style={cardStyle}>
                  <PanelHeader title="Evidence" count={evidence.length} />
                  {evidence.length ? evidence.map((item) => (
                    <div key={item.id} style={recordStyle}>
                      <div style={recordHeaderStyle}>
                        <div style={textBlockStyle}>
                          <strong>{item.label}</strong>
                          <p style={mutedStyle}>{item.referenced_object_type}:{item.referenced_object_id} • {item.source || "manual"}</p>
                        </div>
                        <Chip tone={relationshipTone(item.relationship_type)}>{labelize(item.relationship_type || "context")}</Chip>
                      </div>
                      <label style={labelStyle}>Analyst rationale</label>
                      <textarea
                        aria-label={`Rationale for ${item.label}`}
                        value={evidenceRationaleDrafts[item.id] || ""}
                        onChange={(event) => setEvidenceRationaleDrafts((current) => ({ ...current, [item.id]: event.target.value }))}
                        rows={2}
                        style={textareaStyle}
                      />
                      <div style={formActionsStyle}>
                        <Button
                          onClick={() => onUpdateEvidence?.(item.id, { rationale: evidenceRationaleDrafts[item.id] || "", relationship_type: item.relationship_type || "context" })}
                          disabled={actionBusy === `evidence:${item.id}`}
                        >
                          Save rationale
                        </Button>
                        <button type="button" onClick={() => onOpenEvidenceSource?.(item)} style={linkButtonStyle}>
                          Open source
                        </button>
                        <button type="button" onClick={() => onDeleteEvidence?.(item.id)} disabled={actionBusy === `evidence:${item.id}`} style={dangerLinkStyle}>
                          Delete
                        </button>
                      </div>
                    </div>
                  )) : <p style={mutedStyle}>Save evidence from alert, incident, source IP, or investigation surfaces to explain why it matters.</p>}
                </Card>

                <Card style={cardStyle}>
                  <PanelHeader title="Hypotheses" count={hypotheses.length} />
                  <DraftBox label="New hypothesis" value={hypothesisDraft} onChange={setHypothesisDraft} onSubmit={submitHypothesis} buttonLabel="Add hypothesis" />
                  {hypotheses.map((hypothesis) => {
                    const grouped = relationshipByHypothesis[hypothesis.id] || { supports: [], refutes: [], context: [] };
                    const draft = relationshipDrafts[hypothesis.id] || { evidence_reference_id: evidence[0]?.id || "", relationship_type: "supports", rationale: "" };
                    return (
                      <div key={hypothesis.id} style={recordStyle}>
                        <div style={recordHeaderStyle}>
                          <div style={textBlockStyle}>
                            <strong>{hypothesis.title}</strong>
                            {hypothesis.body ? <p style={mutedStyle}>{hypothesis.body}</p> : null}
                          </div>
                          <StatusPill status={hypothesis.status}>{labelize(hypothesis.status)}</StatusPill>
                          <Chip tone="neutral">{labelize(hypothesis.confidence || "medium")} confidence</Chip>
                        </div>
                        <EvidenceRelationshipGroup title="Supports" links={grouped.supports} onUnlink={onUnlinkEvidenceFromHypothesis} actionBusy={actionBusy} />
                        <EvidenceRelationshipGroup title="Refutes" links={grouped.refutes} onUnlink={onUnlinkEvidenceFromHypothesis} actionBusy={actionBusy} />
                        <EvidenceRelationshipGroup title="Context" links={grouped.context} onUnlink={onUnlinkEvidenceFromHypothesis} actionBusy={actionBusy} />
                        {evidence.length ? (
                          <div style={relationshipFormStyle}>
                            <SelectControl
                              label={`Evidence for ${hypothesis.title}`}
                              value={draft.evidence_reference_id}
                              options={evidence.map((item) => ({ value: item.id, label: item.label }))}
                              onChange={(evidence_reference_id) => updateRelationshipDraft(hypothesis.id, { evidence_reference_id })}
                            />
                            <SelectControl
                              label="Relationship"
                              value={draft.relationship_type}
                              options={RELATIONSHIP_OPTIONS}
                              onChange={(relationship_type) => updateRelationshipDraft(hypothesis.id, { relationship_type })}
                            />
                            <label style={labelStyle}>Relationship rationale</label>
                            <input
                              aria-label={`Relationship rationale for ${hypothesis.title}`}
                              value={draft.rationale}
                              onChange={(event) => updateRelationshipDraft(hypothesis.id, { rationale: event.target.value })}
                              style={inputStyle}
                            />
                            <Button onClick={() => submitRelationship(hypothesis.id)} disabled={actionBusy === "link-evidence"}>
                              Link evidence
                            </Button>
                          </div>
                        ) : null}
                        <button type="button" onClick={() => onDeleteHypothesis?.(hypothesis.id)} disabled={actionBusy === `hypothesis:${hypothesis.id}`} style={dangerLinkStyle}>
                          Delete hypothesis
                        </button>
                      </div>
                    );
                  })}
                </Card>

                <Card style={cardStyle}>
                  <PanelHeader title="Tasks" count={tasks.length} />
                  <TaskDraftBox
                    value={taskDraft}
                    onChange={setTaskDraft}
                    linkDraft={taskLinkDraft}
                    onLinkDraftChange={setTaskLinkDraft}
                    hypotheses={hypotheses}
                    evidence={evidence}
                    onSubmit={submitTask}
                  />
                  {tasks.map((task) => (
                    <div key={task.id} style={recordStyle}>
                      <div style={recordHeaderStyle}>
                        <div style={textBlockStyle}>
                          <strong>{task.title}</strong>
                          <p style={mutedStyle}>{formatTaskContext(task, hypotheses, evidence)}</p>
                        </div>
                        <StatusPill status={task.status}>{labelize(task.status)}</StatusPill>
                      </div>
                      <div style={formActionsStyle}>
                        <Button
                          onClick={() => onUpdateTask?.(task.id, { status: task.status === "done" ? "open" : "done" })}
                          disabled={actionBusy === `task:${task.id}`}
                        >
                          {task.status === "done" ? "Reopen" : "Complete"}
                        </Button>
                        <button type="button" onClick={() => onDeleteTask?.(task.id)} disabled={actionBusy === `task:${task.id}`} style={dangerLinkStyle}>
                          Delete task
                        </button>
                      </div>
                    </div>
                  ))}
                </Card>

                <Card style={cardStyle}>
                  <PanelHeader title="Investigation timeline" count={timeline.length} />
                  {timeline.length ? (
                    <ol style={timelineStyle}>
                      {timeline.map((event) => (
                        <li key={event.id} style={timelineItemStyle}>
                          <Chip tone={event.kind === "source" ? "info" : "neutral"}>{event.kind === "source" ? "Source event" : "Analyst milestone"}</Chip>
                          <strong>{event.label}</strong>
                          <span style={mutedStyle}>{formatDate(event.timestamp)} {event.detail ? `• ${event.detail}` : ""}</span>
                        </li>
                      ))}
                    </ol>
                  ) : <p style={mutedStyle}>Timeline appears as source events and analyst milestones are attached.</p>}
                </Card>
              </div>

              <Card style={cardStyle}>
                <PanelHeader title="Open questions and notes" count={notes.length + unresolvedTasks.length} />
                <DraftBox label="New note" value={noteDraft} onChange={setNoteDraft} onSubmit={submitNote} buttonLabel="Add note" />
                {notes.map((note) => (
                  <div key={note.id} style={recordHeaderStyle}>
                    <p style={recordTextStyle}>{note.body}</p>
                    <button type="button" onClick={() => onDeleteNote?.(note.id)} disabled={actionBusy === `note:${note.id}`} style={dangerLinkStyle}>
                      Delete note
                    </button>
                  </div>
                ))}
              </Card>

              <UnassignedContent
                unassigned={unassigned}
                onRemovePin={onRemovePin}
                onDeleteNote={onDeleteNote}
                onDeleteHypothesis={onDeleteHypothesis}
                onDeleteTask={onDeleteTask}
                onDeleteEvidence={onDeleteEvidence}
                actionBusy={actionBusy}
              />
            </main>
          </div>
        )}
      </Panel>
    </div>
  );
}

function ActiveInvestigationHeader({ investigation, sourceContext, actionBusy, onDeleteInvestigation }) {
  if (!investigation) return null;
  return (
    <Card style={activeHeaderStyle}>
      <div style={activeTitleRowStyle}>
        <div style={textBlockStyle}>
          <p style={eyebrowStyle}>Active investigation</p>
          <h3 style={activeTitleStyle}>{investigation.title || `Investigation #${investigation.id}`}</h3>
          <p style={mutedStyle}>{formatInvestigationContext(investigation)}</p>
        </div>
        <div style={badgeRowStyle}>
          <StatusPill status={investigation.status}>{labelize(investigation.status)}</StatusPill>
          <Chip tone="neutral">{labelize(investigation.confidence || "medium")} confidence</Chip>
          <Chip tone="neutral">{labelize(investigation.disposition || "undetermined")}</Chip>
        </div>
      </div>
      <div style={contextGridStyle}>
        <ContextStat label="Linked alert" value={sourceContext?.alert?.id || investigation.linked_alert_id || "None"} />
        <ContextStat label="Linked incident" value={sourceContext?.incident?.id || investigation.linked_incident_id || "None"} />
        <ContextStat label="Source IP" value={sourceContext?.source_ip || investigation.linked_source_ip || "None"} />
        <ContextStat label="Last activity" value={formatDate(investigation.last_activity_at || investigation.updated_at)} />
      </div>
      <div style={formActionsStyle}>
        <button
          type="button"
          onClick={() => onDeleteInvestigation?.(investigation.id)}
          disabled={actionBusy === `investigation:${investigation.id}`}
          style={dangerLinkStyle}
        >
          Delete investigation
        </button>
      </div>
    </Card>
  );
}

function SourceContext({ sourceContext, investigation }) {
  const alert = sourceContext?.alert;
  const incident = sourceContext?.incident;
  const partial = sourceContext?.partial || [];
  if (!alert && !incident && !sourceContext?.source_ip && !investigation?.linked_source_ip) {
    return <p style={mutedStyle}>No linked source context is available for this investigation.</p>;
  }
  return (
    <div style={sourceContextStyle}>
      {alert ? (
        <p style={recordTextStyle}>
          Alert #{alert.id}: {alert.alert_type || "alert"} with {alert.severity || "unknown"} severity from {alert.source_ip || "unknown source"}.
        </p>
      ) : null}
      {incident ? (
        <p style={recordTextStyle}>
          Incident #{incident.id}: {incident.title || "incident"} is {incident.status || "unknown"} at {incident.severity || incident.priority || "unknown"} priority.
        </p>
      ) : null}
      {(sourceContext?.source_ip || investigation?.linked_source_ip) ? (
        <p style={recordTextStyle}>Source IP: {sourceContext?.source_ip || investigation.linked_source_ip}</p>
      ) : null}
      {partial.length ? <p style={mutedStyle}>{partial.join("; ")}</p> : null}
    </div>
  );
}

function StoryBlock({ title, label, children }) {
  return (
    <section style={storyBlockStyle}>
      <div style={storyHeaderStyle}>
        <h4 style={sectionTitleStyle}>{title}</h4>
        <Chip tone={label === "Source fact" ? "info" : "neutral"}>{label}</Chip>
      </div>
      {children}
    </section>
  );
}

function PanelHeader({ title, count }) {
  return (
    <div style={panelHeaderStyle}>
      <h4 style={sectionTitleStyle}>{title}</h4>
      <Chip tone={count ? "info" : "neutral"}>{count}</Chip>
    </div>
  );
}

function SelectControl({ label, value, options, onChange }) {
  const normalizedOptions = options.map((option) => (
    typeof option === "object" ? option : { value: option, label: labelize(option) }
  ));
  return (
    <label style={selectLabelStyle}>
      <span style={labelStyle}>{label}</span>
      <select aria-label={label} value={value || ""} onChange={(event) => onChange(event.target.value)} style={selectStyle}>
        {normalizedOptions.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </label>
  );
}

function DraftBox({ label, value, onChange, onSubmit, buttonLabel }) {
  return (
    <div style={draftStyle}>
      <label style={labelStyle}>{label}</label>
      <textarea aria-label={label} value={value} onChange={(event) => onChange(event.target.value)} rows={2} style={textareaStyle} />
      <Button onClick={onSubmit} disabled={!value.trim()}>{buttonLabel}</Button>
    </div>
  );
}

function TaskDraftBox({ value, onChange, linkDraft, onLinkDraftChange, hypotheses, evidence, onSubmit }) {
  return (
    <div style={draftStyle}>
      <label style={labelStyle}>New task</label>
      <textarea aria-label="New task" value={value} onChange={(event) => onChange(event.target.value)} rows={2} style={textareaStyle} />
      <div style={controlGridStyle}>
        <SelectControl
          label="Task hypothesis"
          value={linkDraft.hypothesis_id}
          options={[{ value: "", label: "No hypothesis" }, ...hypotheses.map((item) => ({ value: item.id, label: item.title }))]}
          onChange={(hypothesis_id) => onLinkDraftChange((current) => ({ ...current, hypothesis_id }))}
        />
        <SelectControl
          label="Task evidence"
          value={linkDraft.evidence_reference_id}
          options={[{ value: "", label: "No evidence" }, ...evidence.map((item) => ({ value: item.id, label: item.label }))]}
          onChange={(evidence_reference_id) => onLinkDraftChange((current) => ({ ...current, evidence_reference_id }))}
        />
      </div>
      <Button onClick={onSubmit} disabled={!value.trim()}>Add task</Button>
    </div>
  );
}

function EvidenceRelationshipGroup({ title, links, onUnlink, actionBusy }) {
  if (!links.length) {
    return <p style={mutedStyle}>{title}: none linked.</p>;
  }
  return (
    <div style={relationshipGroupStyle}>
      <strong>{title}</strong>
      {links.map((link) => (
        <div key={link.id} style={relationshipRowStyle}>
          <span style={recordTextStyle}>{link.evidence?.label || `Evidence #${link.evidence_reference_id}`}</span>
          <button
            type="button"
            onClick={() => onUnlink?.(link.id)}
            disabled={actionBusy === `hypothesis-evidence:${link.id}`}
            style={linkButtonStyle}
          >
            Unlink
          </button>
        </div>
      ))}
    </div>
  );
}

function UnassignedContent({ unassigned, onRemovePin, onDeleteNote, onDeleteHypothesis, onDeleteTask, onDeleteEvidence, actionBusy }) {
  const items = unassigned?.items || [];
  const notes = unassigned?.notes || [];
  const hypotheses = unassigned?.hypotheses || [];
  const tasks = unassigned?.tasks || [];
  const evidence = unassigned?.evidence || [];
  const count = items.length + notes.length + hypotheses.length + tasks.length + evidence.length;
  if (!count) return null;
  return (
    <Card style={secondaryCardStyle}>
      <PanelHeader title="Unassigned workspace content" count={count} />
      <p style={mutedStyle}>Legacy or manually saved items remain private and discoverable, but active investigations should drive new work.</p>
      <div style={legacyGridStyle}>
        {items.map((item) => (
          <div key={`pin-${item.id}`} style={compactRecordStyle}>
            <span style={recordTextStyle}>Pin: {item.label || item.referenced_object_id}</span>
            <button type="button" onClick={() => onRemovePin?.(item.id)} disabled={actionBusy === `pin:${item.id}`} style={linkButtonStyle}>Remove</button>
          </div>
        ))}
        {notes.map((note) => (
          <div key={`note-${note.id}`} style={compactRecordStyle}>
            <span style={recordTextStyle}>Note: {note.body}</span>
            <button type="button" onClick={() => onDeleteNote?.(note.id)} disabled={actionBusy === `note:${note.id}`} style={linkButtonStyle}>Delete</button>
          </div>
        ))}
        {hypotheses.map((hypothesis) => (
          <div key={`hypothesis-${hypothesis.id}`} style={compactRecordStyle}>
            <span style={recordTextStyle}>Hypothesis: {hypothesis.title}</span>
            <button type="button" onClick={() => onDeleteHypothesis?.(hypothesis.id)} disabled={actionBusy === `hypothesis:${hypothesis.id}`} style={linkButtonStyle}>Delete</button>
          </div>
        ))}
        {tasks.map((task) => (
          <div key={`task-${task.id}`} style={compactRecordStyle}>
            <span style={recordTextStyle}>Task: {task.title}</span>
            <button type="button" onClick={() => onDeleteTask?.(task.id)} disabled={actionBusy === `task:${task.id}`} style={linkButtonStyle}>Delete</button>
          </div>
        ))}
        {evidence.map((item) => (
          <div key={`evidence-${item.id}`} style={compactRecordStyle}>
            <span style={recordTextStyle}>Evidence: {item.label}</span>
            <button type="button" onClick={() => onDeleteEvidence?.(item.id)} disabled={actionBusy === `evidence:${item.id}`} style={linkButtonStyle}>Delete</button>
          </div>
        ))}
      </div>
    </Card>
  );
}

function EmptyInvestigationState() {
  return (
    <div style={emptyStateStyle}>
      <h3 style={activeTitleStyle}>Start from an alert, incident, or source context</h3>
      <p style={mutedStyle}>
        Saved investigations appear here as active workspaces with evidence, hypotheses, tasks, notes, a timeline, and a conclusion.
      </p>
    </div>
  );
}

function ContextStat({ label, value }) {
  return (
    <div style={contextStatStyle}>
      <span style={labelStyle}>{label}</span>
      <strong style={contextValueStyle}>{value}</strong>
    </div>
  );
}

function buildInvestigationDraft(investigation) {
  return {
    status: investigation?.status || "open",
    confidence: investigation?.confidence || "medium",
    disposition: investigation?.disposition || "undetermined",
    summary: investigation?.summary || "",
    conclusion: investigation?.conclusion || "",
  };
}

function buildDisplayTimeline(timeline, sourceContext) {
  const sourceEvents = [];
  if (sourceContext?.alert) {
    sourceEvents.push({
      id: `source-alert-${sourceContext.alert.id}`,
      kind: "source",
      label: `Alert #${sourceContext.alert.id}`,
      timestamp: sourceContext.alert.created_at,
      detail: sourceContext.alert.message || sourceContext.alert.alert_type || "Linked alert",
    });
  }
  if (sourceContext?.incident) {
    sourceEvents.push({
      id: `source-incident-${sourceContext.incident.id}`,
      kind: "source",
      label: `Incident #${sourceContext.incident.id}`,
      timestamp: sourceContext.incident.created_at,
      detail: sourceContext.incident.title || "Linked incident",
    });
  }
  return [...sourceEvents, ...timeline].sort((a, b) => String(a.timestamp || "").localeCompare(String(b.timestamp || "")));
}

function buildConclusionCaveats(investigation, unresolvedTasks) {
  const caveats = [];
  if ((investigation?.disposition || "undetermined") === "undetermined") caveats.push("Disposition is still undetermined.");
  if ((investigation?.confidence || "medium") === "low") caveats.push("Confidence is low.");
  if (unresolvedTasks.length) caveats.push(`${unresolvedTasks.length} task${unresolvedTasks.length === 1 ? "" : "s"} still open.`);
  return caveats;
}

function groupRelationships(links, evidence) {
  const evidenceById = new Map(evidence.map((item) => [Number(item.id), item]));
  return links.reduce((acc, link) => {
    const hypothesisId = Number(link.hypothesis_id);
    if (!acc[hypothesisId]) acc[hypothesisId] = { supports: [], refutes: [], context: [] };
    const relationship = link.relationship_type || "context";
    const bucket = acc[hypothesisId][relationship] || acc[hypothesisId].context;
    bucket.push({ ...link, evidence: evidenceById.get(Number(link.evidence_reference_id)) });
    return acc;
  }, {});
}

function formatTaskContext(task, hypotheses, evidence) {
  const parts = [];
  const hypothesis = hypotheses.find((item) => Number(item.id) === Number(task.hypothesis_id));
  const evidenceItem = evidence.find((item) => Number(item.id) === Number(task.evidence_reference_id));
  if (hypothesis) parts.push(`hypothesis: ${hypothesis.title}`);
  if (evidenceItem) parts.push(`evidence: ${evidenceItem.label}`);
  return parts.join(" • ") || "Investigation task";
}

function formatInvestigationContext(investigation) {
  if (!investigation) return "";
  return [
    investigation.linked_alert_id ? `alert:${investigation.linked_alert_id}` : "",
    investigation.linked_incident_id ? `incident:${investigation.linked_incident_id}` : "",
    investigation.linked_source_ip ? `source:${investigation.linked_source_ip}` : "",
  ].filter(Boolean).join(" • ") || "private investigation";
}

function formatDate(value) {
  if (!value) return "Not recorded";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return String(value);
  return date.toLocaleString();
}

function labelize(value) {
  return String(value || "unknown").replaceAll("_", " ");
}

function relationshipTone(value) {
  if (value === "supports") return "success";
  if (value === "refutes") return "danger";
  return "neutral";
}

const panelStyle = { padding: 0, overflow: "hidden" };
const workspaceLayoutStyle = {
  display: "grid",
  gridTemplateColumns: "minmax(220px, 300px) minmax(0, 1fr)",
  gap: theme.spacing.lg,
  padding: theme.spacing.lg,
  minWidth: 0,
};
const railStyle = {
  display: "grid",
  alignContent: "start",
  gap: theme.spacing.md,
  minWidth: 0,
};
const railHeaderStyle = { display: "flex", justifyContent: "space-between", gap: theme.spacing.sm, alignItems: "center" };
const railListStyle = { display: "grid", gap: theme.spacing.sm };
const investigationButtonStyle = {
  width: "100%",
  display: "grid",
  gap: "7px",
  textAlign: "left",
  border: `1px solid ${theme.color.border}`,
  borderRadius: theme.radius.md,
  background: theme.color.bgRaised,
  color: theme.color.text,
  padding: theme.spacing.md,
  cursor: "pointer",
  minWidth: 0,
};
const investigationButtonActiveStyle = {
  borderColor: theme.color.ai,
  boxShadow: "inset 3px 0 0 rgba(56, 189, 248, 0.9)",
};
const activeColumnStyle = { display: "grid", gap: theme.spacing.lg, minWidth: 0 };
const activeHeaderStyle = { padding: theme.spacing.lg, minWidth: 0 };
const activeTitleRowStyle = { display: "flex", justifyContent: "space-between", alignItems: "flex-start", gap: theme.spacing.md, flexWrap: "wrap", minWidth: 0 };
const activeTitleStyle = { margin: 0, color: theme.color.text, fontSize: "20px", lineHeight: 1.2, overflowWrap: "anywhere" };
const titleTextStyle = { color: theme.color.text, fontWeight: 800, overflowWrap: "anywhere", wordBreak: "break-word" };
const badgeRowStyle = { display: "flex", gap: theme.spacing.xs, flexWrap: "wrap", alignItems: "center" };
const contextGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))", gap: theme.spacing.sm, marginTop: theme.spacing.md, minWidth: 0 };
const contextStatStyle = { borderTop: `1px solid ${theme.color.borderSubtle}`, paddingTop: theme.spacing.sm, minWidth: 0 };
const contextValueStyle = { display: "block", marginTop: 3, overflowWrap: "anywhere", wordBreak: "break-word" };
const storyCardStyle = { padding: theme.spacing.lg, minWidth: 0 };
const storyGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(280px, 100%), 1fr))", gap: theme.spacing.md, minWidth: 0 };
const storyBlockStyle = { display: "grid", alignContent: "start", gap: theme.spacing.sm, minWidth: 0 };
const storyHeaderStyle = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: theme.spacing.sm, flexWrap: "wrap", minWidth: 0 };
const sourceContextStyle = { display: "grid", gap: theme.spacing.xs, minWidth: 0 };
const workGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(360px, 100%), 1fr))", gap: theme.spacing.lg, minWidth: 0 };
const cardStyle = { padding: theme.spacing.md, minWidth: 0 };
const secondaryCardStyle = { padding: theme.spacing.md, minWidth: 0, opacity: 0.92 };
const panelHeaderStyle = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: theme.spacing.sm, marginBottom: theme.spacing.md, minWidth: 0 };
const recordStyle = { display: "grid", gap: theme.spacing.sm, borderTop: `1px solid ${theme.color.borderSubtle}`, paddingTop: theme.spacing.sm, marginTop: theme.spacing.sm, minWidth: 0 };
const compactRecordStyle = { display: "flex", justifyContent: "space-between", gap: theme.spacing.sm, alignItems: "center", borderTop: `1px solid ${theme.color.borderSubtle}`, paddingTop: theme.spacing.sm, minWidth: 0, flexWrap: "wrap" };
const recordHeaderStyle = { display: "flex", justifyContent: "space-between", gap: theme.spacing.sm, alignItems: "flex-start", flexWrap: "wrap", minWidth: 0 };
const textBlockStyle = { minWidth: 0, flex: "1 1 200px", overflowWrap: "anywhere", wordBreak: "break-word" };
const recordTextStyle = { margin: 0, minWidth: 0, flex: "1 1 200px", color: theme.color.textSoft, overflowWrap: "anywhere", wordBreak: "break-word" };
const mutedStyle = { margin: "3px 0 0", color: theme.color.textMuted, fontSize: "12px", overflowWrap: "anywhere", wordBreak: "break-word" };
const metaLineStyle = { color: theme.color.textMuted, fontSize: "12px", overflowWrap: "anywhere", wordBreak: "break-word" };
const errorStyle = { margin: theme.spacing.lg, color: theme.color.dangerSoft };
const actionStatusStyle = { margin: theme.spacing.lg, color: theme.color.successSoft, fontSize: "12px", fontWeight: 800, overflowWrap: "anywhere" };
const actionErrorStyle = { ...actionStatusStyle, color: theme.color.dangerSoft };
const eyebrowStyle = { margin: "0 0 6px", color: theme.color.textMuted, ...theme.typography.label };
const sectionTitleStyle = { margin: 0, color: theme.color.text, fontSize: "15px", lineHeight: 1.25, overflowWrap: "anywhere" };
const formActionsStyle = { display: "flex", gap: theme.spacing.sm, alignItems: "center", flexWrap: "wrap", marginTop: theme.spacing.sm };
const draftStyle = { display: "grid", gap: theme.spacing.sm, marginBottom: theme.spacing.sm };
const labelStyle = { color: theme.color.textMuted, fontSize: "12px", fontWeight: 800 };
const selectLabelStyle = { display: "grid", gap: "5px", minWidth: 0 };
const selectStyle = { width: "100%", boxSizing: "border-box", border: `1px solid ${theme.color.border}`, borderRadius: theme.radius.sm, backgroundColor: theme.color.bg, color: theme.color.text, padding: "8px", minWidth: 0 };
const inputStyle = { width: "100%", boxSizing: "border-box", border: `1px solid ${theme.color.border}`, borderRadius: theme.radius.sm, backgroundColor: theme.color.bg, color: theme.color.text, padding: "8px", minWidth: 0 };
const textareaStyle = { width: "100%", boxSizing: "border-box", border: `1px solid ${theme.color.border}`, borderRadius: theme.radius.sm, backgroundColor: theme.color.bg, color: theme.color.text, padding: "8px", resize: "vertical", minWidth: 0 };
const controlGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))", gap: theme.spacing.sm, minWidth: 0 };
const caveatListStyle = { margin: `${theme.spacing.sm}px 0 0`, paddingLeft: "18px", color: theme.color.reviewSoft, fontSize: "12px" };
const linkButtonStyle = { border: "none", background: "transparent", color: theme.color.aiSoft, cursor: "pointer", fontWeight: 800, padding: 0 };
const dangerLinkStyle = { ...linkButtonStyle, color: theme.color.dangerSoft };
const relationshipFormStyle = { display: "grid", gap: theme.spacing.sm, marginTop: theme.spacing.sm, paddingTop: theme.spacing.sm, borderTop: `1px solid ${theme.color.borderSubtle}`, minWidth: 0 };
const relationshipGroupStyle = { display: "grid", gap: "5px", minWidth: 0 };
const relationshipRowStyle = { display: "flex", justifyContent: "space-between", gap: theme.spacing.sm, alignItems: "center", flexWrap: "wrap", minWidth: 0 };
const timelineStyle = { display: "grid", gap: theme.spacing.sm, listStyle: "none", padding: 0, margin: 0 };
const timelineItemStyle = { display: "grid", gap: "5px", borderTop: `1px solid ${theme.color.borderSubtle}`, paddingTop: theme.spacing.sm, minWidth: 0 };
const legacyGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(260px, 100%), 1fr))", gap: theme.spacing.sm, marginTop: theme.spacing.sm, minWidth: 0 };
const emptyStateStyle = { padding: theme.spacing.xl, display: "grid", gap: theme.spacing.sm, minWidth: 0 };

export default AnalystWorkspace;
