import React, { useEffect, useState } from "react";

import { Button, Card, Chip, Panel, SectionHeader, StatusPill } from "./uiPrimitives";
import { theme } from "../theme";

function AnalystWorkspace({
  workspaceState,
  loading,
  error,
  onRefresh,
  onCreateNote,
  onCreateHypothesis,
  onCreateTask,
  onRemovePin,
  onDeleteNote,
  onDeleteHypothesis,
  onDeleteTask,
  actionBusy = "",
  actionStatus = null,
}) {
  const [noteDraft, setNoteDraft] = useState("");
  const [hypothesisDraft, setHypothesisDraft] = useState("");
  const [taskDraft, setTaskDraft] = useState("");

  useEffect(() => {
    if (!workspaceState && !loading && !error) onRefresh?.();
  }, [error, loading, onRefresh, workspaceState]);

  if (loading) return <Panel aria-label="Analyst Workspace"><p style={mutedStyle}>Loading private workspace...</p></Panel>;
  if (error) {
    return (
      <Panel aria-label="Analyst Workspace">
        <SectionHeader eyebrow="Analyst Workspace" title="Private investigation notebook" />
        <p style={errorStyle}>{error}</p>
        <Button onClick={onRefresh}>Retry</Button>
      </Panel>
    );
  }

  const workspace = workspaceState?.workspace;
  const items = workspaceState?.items || [];
  const notes = workspaceState?.notes || [];
  const hypotheses = workspaceState?.hypotheses || [];
  const tasks = workspaceState?.tasks || [];
  const evidence = workspaceState?.evidence || [];
  const investigations = workspaceState?.investigations || [];

  const submitNote = () => {
    if (!noteDraft.trim()) return;
    onCreateNote?.(noteDraft.trim());
    setNoteDraft("");
  };
  const submitHypothesis = () => {
    if (!hypothesisDraft.trim()) return;
    onCreateHypothesis?.(hypothesisDraft.trim());
    setHypothesisDraft("");
  };
  const submitTask = () => {
    if (!taskDraft.trim()) return;
    onCreateTask?.(taskDraft.trim());
    setTaskDraft("");
  };

  return (
    <div data-navigation-target="analyst-workspace" aria-label="Analyst Workspace">
      <Panel style={panelStyle}>
        <SectionHeader
          eyebrow="Analyst Workspace"
          title="Private investigation notebook"
          subtitle="Manual pins, notes, hypotheses, tasks, and evidence. Nothing here mutates system data."
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
        {!items.length && !notes.length && !hypotheses.length && !tasks.length && !evidence.length && !investigations.length ? (
          <p style={emptyStyle}>Nothing has been added. Workspace content is never automatically populated.</p>
        ) : null}
        <div style={gridStyle}>
          <WorkspaceCard title="Pinned objects" count={items.length}>
            {items.length ? items.map((item) => (
              <div key={item.id} style={rowStyle}>
                <div>
                  <strong>{item.label || item.referenced_object_id}</strong>
                  <p style={mutedStyle}>{item.item_type} • {item.referenced_object_type}:{item.referenced_object_id}</p>
                </div>
                <button type="button" onClick={() => onRemovePin?.(item.id)} style={linkButtonStyle}>
                  Remove
                </button>
              </div>
            )) : <p style={mutedStyle}>Pin alerts, incidents, recon items, source IPs, investigations, or evidence manually.</p>}
          </WorkspaceCard>

          <WorkspaceCard title="Notes" count={notes.length}>
            <DraftBox
              label="New note"
              value={noteDraft}
              onChange={setNoteDraft}
              onSubmit={submitNote}
              buttonLabel="Add note"
            />
            {notes.map((note) => (
              <div key={note.id} style={rowStyle}>
                <p style={recordTextStyle}>{note.body}</p>
                <button
                  type="button"
                  onClick={() => onDeleteNote?.(note.id)}
                  disabled={actionBusy === `note:${note.id}`}
                  style={linkButtonStyle}
                >
                  Delete
                </button>
              </div>
            ))}
          </WorkspaceCard>

          <WorkspaceCard title="Hypotheses" count={hypotheses.length}>
            <DraftBox
              label="New hypothesis"
              value={hypothesisDraft}
              onChange={setHypothesisDraft}
              onSubmit={submitHypothesis}
              buttonLabel="Add hypothesis"
            />
            {hypotheses.map((hypothesis) => (
              <div key={hypothesis.id} style={recordStyle}>
                <div style={rowStyle}>
                  <div style={textBlockStyle}>
                    <strong>{hypothesis.title}</strong>
                    {hypothesis.body ? <p style={mutedStyle}>{hypothesis.body}</p> : null}
                  </div>
                  <StatusPill status={hypothesis.status}>{hypothesis.status}</StatusPill>
                  <button
                    type="button"
                    onClick={() => onDeleteHypothesis?.(hypothesis.id)}
                    disabled={actionBusy === `hypothesis:${hypothesis.id}`}
                    style={linkButtonStyle}
                  >
                    Delete
                  </button>
                </div>
              </div>
            ))}
          </WorkspaceCard>

          <WorkspaceCard title="Tasks" count={tasks.length}>
            <DraftBox
              label="New task"
              value={taskDraft}
              onChange={setTaskDraft}
              onSubmit={submitTask}
              buttonLabel="Add task"
            />
            {tasks.map((task) => (
              <div key={task.id} style={rowStyle}>
                <span style={recordTextStyle}>{task.title}</span>
                <StatusPill status={task.status}>{task.status}</StatusPill>
                <button
                  type="button"
                  onClick={() => onDeleteTask?.(task.id)}
                  disabled={actionBusy === `task:${task.id}`}
                  style={linkButtonStyle}
                >
                  Delete
                </button>
              </div>
            ))}
          </WorkspaceCard>

          <WorkspaceCard title="Saved investigations" count={investigations.length}>
            {investigations.length ? investigations.map((investigation) => (
              <div key={investigation.id} style={recordStyle}>
                <div style={rowStyle}>
                  <div style={textBlockStyle}>
                    <strong>{investigation.title || `Investigation #${investigation.id}`}</strong>
                    <p style={mutedStyle}>
                      {[
                        investigation.linked_alert_id ? `alert:${investigation.linked_alert_id}` : "",
                        investigation.linked_incident_id ? `incident:${investigation.linked_incident_id}` : "",
                        investigation.linked_source_ip ? `source:${investigation.linked_source_ip}` : "",
                      ].filter(Boolean).join(" • ") || "private investigation"}
                    </p>
                  </div>
                  <StatusPill status={investigation.status}>{investigation.status}</StatusPill>
                </div>
              </div>
            )) : <p style={mutedStyle}>Saved investigations from the drawer appear here.</p>}
          </WorkspaceCard>

          <WorkspaceCard title="Evidence references" count={evidence.length}>
            {evidence.length ? evidence.map((item) => (
              <p key={item.id} style={recordStyle}>{item.label} <span style={mutedStyle}>{item.referenced_object_type}:{item.referenced_object_id}</span></p>
            )) : <p style={mutedStyle}>Save evidence links from the investigation drawer or scoped surfaces.</p>}
          </WorkspaceCard>
        </div>
      </Panel>
    </div>
  );
}

function WorkspaceCard({ title, count, children }) {
  return (
    <Card style={cardStyle}>
      <div style={cardHeaderStyle}>
        <strong>{title}</strong>
        <Chip tone={count ? "info" : "neutral"}>{count}</Chip>
      </div>
      <div style={cardBodyStyle}>{children}</div>
    </Card>
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

const panelStyle = { padding: 0 };
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(min(260px, 100%), 1fr))", gap: theme.spacing.lg, padding: theme.spacing.lg, minWidth: 0 };
const cardStyle = { padding: theme.spacing.md, minWidth: 0 };
const cardHeaderStyle = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: theme.spacing.sm, minWidth: 0 };
const cardBodyStyle = { display: "grid", gap: theme.spacing.sm, marginTop: theme.spacing.md };
const rowStyle = { display: "flex", justifyContent: "space-between", gap: theme.spacing.sm, alignItems: "center", borderTop: `1px solid ${theme.color.borderSubtle}`, paddingTop: theme.spacing.sm, minWidth: 0, flexWrap: "wrap" };
const recordStyle = { margin: 0, color: theme.color.textSoft, borderTop: `1px solid ${theme.color.borderSubtle}`, paddingTop: theme.spacing.sm, minWidth: 0, overflowWrap: "anywhere" };
const recordTextStyle = { margin: 0, minWidth: 0, flex: "1 1 180px", color: theme.color.textSoft, overflowWrap: "anywhere", wordBreak: "break-word" };
const textBlockStyle = { minWidth: 0, flex: "1 1 180px", overflowWrap: "anywhere", wordBreak: "break-word" };
const mutedStyle = { margin: "3px 0 0", color: theme.color.textMuted, fontSize: "12px", overflowWrap: "anywhere", wordBreak: "break-word" };
const emptyStyle = { margin: 0, padding: theme.spacing.lg, color: theme.color.textMuted, borderBottom: `1px solid ${theme.color.border}` };
const errorStyle = { margin: theme.spacing.lg, color: theme.color.dangerSoft };
const actionStatusStyle = { margin: theme.spacing.lg, color: theme.color.successSoft, fontSize: "12px", fontWeight: 800, overflowWrap: "anywhere" };
const actionErrorStyle = { ...actionStatusStyle, color: theme.color.dangerSoft };
const draftStyle = { display: "grid", gap: theme.spacing.sm, paddingBottom: theme.spacing.sm };
const labelStyle = { color: theme.color.textMuted, fontSize: "12px", fontWeight: 800 };
const textareaStyle = { width: "100%", boxSizing: "border-box", border: `1px solid ${theme.color.border}`, borderRadius: theme.radius.sm, backgroundColor: theme.color.bg, color: theme.color.text, padding: "8px", resize: "vertical" };
const linkButtonStyle = { border: "none", background: "transparent", color: theme.color.aiSoft, cursor: "pointer", fontWeight: 800 };

export default AnalystWorkspace;
