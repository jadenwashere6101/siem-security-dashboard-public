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
        {!items.length && !notes.length && !hypotheses.length && !tasks.length && !evidence.length ? (
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
            {notes.map((note) => <p key={note.id} style={recordStyle}>{note.body}</p>)}
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
                <strong>{hypothesis.title}</strong>
                <StatusPill status={hypothesis.status}>{hypothesis.status}</StatusPill>
                {hypothesis.body ? <p style={mutedStyle}>{hypothesis.body}</p> : null}
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
                <span>{task.title}</span>
                <StatusPill status={task.status}>{task.status}</StatusPill>
              </div>
            ))}
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
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: theme.spacing.lg, padding: theme.spacing.lg };
const cardStyle = { padding: theme.spacing.md };
const cardHeaderStyle = { display: "flex", justifyContent: "space-between", alignItems: "center", gap: theme.spacing.sm };
const cardBodyStyle = { display: "grid", gap: theme.spacing.sm, marginTop: theme.spacing.md };
const rowStyle = { display: "flex", justifyContent: "space-between", gap: theme.spacing.sm, alignItems: "center", borderTop: `1px solid ${theme.color.borderSubtle}`, paddingTop: theme.spacing.sm };
const recordStyle = { margin: 0, color: theme.color.textSoft, borderTop: `1px solid ${theme.color.borderSubtle}`, paddingTop: theme.spacing.sm };
const mutedStyle = { margin: "3px 0 0", color: theme.color.textMuted, fontSize: "12px" };
const emptyStyle = { margin: 0, padding: theme.spacing.lg, color: theme.color.textMuted, borderBottom: `1px solid ${theme.color.border}` };
const errorStyle = { margin: theme.spacing.lg, color: theme.color.dangerSoft };
const draftStyle = { display: "grid", gap: theme.spacing.sm, paddingBottom: theme.spacing.sm };
const labelStyle = { color: theme.color.textMuted, fontSize: "12px", fontWeight: 800 };
const textareaStyle = { width: "100%", boxSizing: "border-box", border: `1px solid ${theme.color.border}`, borderRadius: theme.radius.sm, backgroundColor: theme.color.bg, color: theme.color.text, padding: "8px", resize: "vertical" };
const linkButtonStyle = { border: "none", background: "transparent", color: theme.color.aiSoft, cursor: "pointer", fontWeight: 800 };

export default AnalystWorkspace;
