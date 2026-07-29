import React, { useEffect, useMemo, useRef } from "react";

import { Button, Card, Chip, Panel, SectionHeader, StatusPill } from "./uiPrimitives";
import ThreatStoryView from "./ThreatStoryView";
import { theme } from "../theme";
import { buildDrawerSections, buildInvestigationContext } from "../utils/investigationWorkflow";

function InvestigationDrawer({
  open,
  onClose,
  alert,
  incident = null,
  timeline = [],
  workspace = null,
  observations = [],
  onPinAlert,
  onSaveEvidence,
  onCreateInvestigation,
}) {
  const closeButtonRef = useRef(null);
  const priorFocusRef = useRef(null);
  const context = useMemo(
    () => buildInvestigationContext({ alert, incident, timeline, workspace, observations }),
    [alert, incident, observations, timeline, workspace]
  );
  const sections = useMemo(() => buildDrawerSections(context), [context]);

  useEffect(() => {
    if (!open) return undefined;
    priorFocusRef.current = document.activeElement;
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        event.preventDefault();
        onClose?.();
        window.requestAnimationFrame?.(() => priorFocusRef.current?.focus?.());
      }
    };
    window.addEventListener("keydown", onKeyDown);
    window.requestAnimationFrame?.(() => closeButtonRef.current?.focus());
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  const handleClose = () => {
    onClose?.();
    window.requestAnimationFrame?.(() => priorFocusRef.current?.focus?.());
  };

  return (
    <div role="presentation" style={backdropStyle} onMouseDown={handleClose}>
      <aside
        role="dialog"
        aria-modal="true"
        aria-label="Investigation Drawer"
        style={drawerStyle}
        onMouseDown={(event) => event.stopPropagation()}
      >
        <Panel style={panelStyle}>
          <SectionHeader
            eyebrow="Investigation"
            title={alert ? `Alert #${alert.id ?? alert.alert_id}` : "Focused investigation"}
            subtitle="Private investigation context. Workspace notes and pins do not mutate system records."
            actions={
              <button ref={closeButtonRef} type="button" aria-label="Close investigation drawer" onClick={handleClose} style={closeStyle}>
                x
              </button>
            }
          />
          <div style={actionsStyle}>
            {alert ? (
              <Button
                variant="secondary"
                onClick={() => onPinAlert?.(alert)}
                aria-label="Pin alert to analyst workspace"
              >
                Pin alert
              </Button>
            ) : null}
            {alert ? (
              <Button
                variant="secondary"
                onClick={() => onSaveEvidence?.(alert)}
                aria-label="Save alert evidence reference"
              >
                Save evidence
              </Button>
            ) : null}
            <Button
              variant="primary"
              onClick={() => onCreateInvestigation?.(context)}
              aria-label="Save investigation state"
            >
              Save investigation
            </Button>
          </div>
          <div style={sectionGridStyle}>
            {sections.map((section) => (
              <Card key={section.id} style={sectionCardStyle} aria-label={section.title}>
                <div style={sectionTitleStyle}>
                  <strong>{section.title}</strong>
                  <StatusPill status={section.status}>{section.status}</StatusPill>
                </div>
                <p style={valueStyle}>{section.value}</p>
                <p style={detailStyle}>{section.detail}</p>
              </Card>
            ))}
          </div>
          <div style={evidenceStyle} aria-label="Evidence links">
            <div style={sectionTitleStyle}>
              <strong>Evidence links</strong>
              <Chip tone={workspace?.evidence?.length ? "info" : "neutral"}>
                {workspace?.evidence?.length ? `${workspace.evidence.length} saved` : "none saved"}
              </Chip>
            </div>
            {workspace?.evidence?.length ? (
              <ul style={listStyle}>
                {workspace.evidence.map((item) => (
                  <li key={item.id}>{item.label} ({item.referenced_object_type}:{item.referenced_object_id})</li>
                ))}
              </ul>
            ) : (
              <p style={detailStyle}>No private evidence references have been saved for this workspace yet.</p>
            )}
          </div>
          <ThreatStoryView context={context} />
        </Panel>
      </aside>
    </div>
  );
}

const backdropStyle = {
  position: "fixed",
  inset: 0,
  zIndex: 9997,
  backgroundColor: "rgba(13, 17, 23, 0.64)",
  display: "flex",
  justifyContent: "flex-end",
};
const drawerStyle = {
  width: "min(880px, 100vw)",
  height: "100vh",
  overflowY: "auto",
  backgroundColor: theme.color.bg,
  boxShadow: theme.shadow.overlay,
};
const panelStyle = { minHeight: "100%", borderRadius: 0, border: "none", padding: 0 };
const closeStyle = { border: "none", background: "transparent", color: theme.color.text, fontSize: "20px", cursor: "pointer" };
const actionsStyle = { display: "flex", gap: theme.spacing.sm, flexWrap: "wrap", padding: theme.spacing.lg, borderBottom: `1px solid ${theme.color.border}` };
const sectionGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(210px, 1fr))", gap: theme.spacing.md, padding: theme.spacing.lg };
const sectionCardStyle = { padding: theme.spacing.md };
const sectionTitleStyle = { display: "flex", justifyContent: "space-between", gap: theme.spacing.sm, alignItems: "center", color: theme.color.text };
const valueStyle = { margin: "10px 0 4px", color: theme.color.text, fontWeight: 800 };
const detailStyle = { margin: 0, color: theme.color.textMuted, fontSize: "12px", lineHeight: 1.45 };
const evidenceStyle = { margin: `0 ${theme.spacing.lg}px ${theme.spacing.lg}px`, border: `1px solid ${theme.color.border}`, borderRadius: theme.radius.sm, padding: theme.spacing.md, backgroundColor: theme.color.bg };
const listStyle = { margin: "10px 0 0", color: theme.color.textSoft, paddingLeft: "20px" };

export default InvestigationDrawer;
