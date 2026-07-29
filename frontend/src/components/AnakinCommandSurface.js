import React, { useEffect, useMemo, useRef, useState } from "react";

import { theme } from "../theme";
import { Button, Chip, Panel, SectionHeader } from "./uiPrimitives";

function AnakinCommandSurface({
  commands = [],
  context,
  onExecute,
  disabled = false,
  status = "idle",
  triggerAriaLabel = "Ask Anakin",
}) {
  const [open, setOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const toggleRef = useRef(null);
  const panelRef = useRef(null);
  const availableCommands = useMemo(() => commands.filter((command) => !command.disabled), [commands]);

  useEffect(() => {
    if (!open) return undefined;
    const onKeyDown = (event) => {
      if (event.key === "Escape") {
        setOpen(false);
        window.requestAnimationFrame?.(() => toggleRef.current?.focus());
      }
    };
    window.addEventListener("keydown", onKeyDown);
    window.requestAnimationFrame?.(() => panelRef.current?.focus());
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [open]);

  const execute = (command) => {
    if (typeof onExecute !== "function" || command.disabled) return;
    onExecute(command, { question });
    if (command.intent === "ask") setQuestion("");
  };

  return (
    <div style={containerStyle}>
      <button
        type="button"
        ref={toggleRef}
        onClick={() => setOpen((current) => !current)}
        disabled={disabled}
        aria-label={triggerAriaLabel}
        aria-expanded={open}
        aria-controls="anakin-command-surface"
        style={triggerStyle(disabled)}
      >
        Ask Anakin
      </button>
      {open ? (
        <div
          id="anakin-command-surface"
          ref={panelRef}
          tabIndex={-1}
          role="dialog"
          aria-label="Anakin command surface"
          style={overlayStyle}
        >
          <Panel style={panelStyle}>
            <SectionHeader
              eyebrow="Anakin"
              title="Analyst command surface"
              subtitle="Run read-only AI commands using the current workspace context."
              actions={
                <button type="button" onClick={() => setOpen(false)} aria-label="Close Anakin command surface" style={closeStyle}>
                  x
                </button>
              }
            />
            <div style={bodyStyle}>
              <div style={contextStyle}>
                <Chip tone="info">{context?.workspace?.activeSection || "workspace"}</Chip>
                {status === "loading" ? <Chip tone="warning">Anakin running</Chip> : null}
              </div>
              <form
                onSubmit={(event) => {
                  event.preventDefault();
                  const ask = availableCommands.find((command) => command.intent === "ask");
                  if (ask) execute(ask);
                }}
                style={askStyle}
              >
                <label style={labelStyle} htmlFor="anakin-command-question">Ask Anakin</label>
                <textarea
                  id="anakin-command-question"
                  value={question}
                  onChange={(event) => setQuestion(event.target.value)}
                  placeholder="Ask a read-only question about this workspace..."
                  rows={3}
                  style={textareaStyle}
                />
                <Button
                  variant="primary"
                  disabled={disabled || !question.trim()}
                  type="submit"
                  aria-label="Submit Ask Anakin question"
                >
                  Ask Anakin
                </Button>
              </form>
              <div style={commandGridStyle}>
                {availableCommands.map((command) => (
                  <button
                    key={command.id}
                    type="button"
                    aria-label={command.label}
                    onClick={() => execute(command)}
                    disabled={disabled}
                    style={commandButtonStyle}
                  >
                    <span style={commandLabelStyle}>{command.label}</span>
                    <span style={commandDescriptionStyle}>{command.description}</span>
                  </button>
                ))}
              </div>
            </div>
          </Panel>
        </div>
      ) : null}
    </div>
  );
}

const containerStyle = {
  position: "fixed",
  right: "18px",
  bottom: "18px",
  zIndex: 9995,
};

const triggerStyle = (disabled) => ({
  border: `1px solid ${theme.color.aiBorder}`,
  borderRadius: "999px",
  padding: "12px 16px",
  background: disabled ? theme.color.bgRaised : "linear-gradient(135deg, #0f766e, #0ea5e9)",
  color: disabled ? theme.color.textMuted : "#fff",
  fontWeight: 800,
  cursor: disabled ? "not-allowed" : "pointer",
  boxShadow: disabled ? "none" : "0 18px 40px rgba(14, 165, 233, 0.26)",
});

const overlayStyle = {
  position: "fixed",
  inset: "auto 18px 76px auto",
  width: "min(540px, calc(100vw - 32px))",
  maxHeight: "min(720px, calc(100vh - 96px))",
  overflowY: "auto",
};

const panelStyle = {
  padding: 0,
  borderColor: theme.color.aiBorder,
  boxShadow: theme.shadow.overlay,
};

const bodyStyle = { padding: theme.spacing.lg, display: "grid", gap: theme.spacing.lg };
const contextStyle = { display: "flex", gap: theme.spacing.sm, flexWrap: "wrap" };
const askStyle = { display: "grid", gap: theme.spacing.sm };
const labelStyle = { color: theme.color.text, fontSize: "12px", fontWeight: 800 };
const textareaStyle = {
  width: "100%",
  boxSizing: "border-box",
  border: `1px solid ${theme.color.border}`,
  borderRadius: theme.radius.sm,
  backgroundColor: theme.color.bg,
  color: theme.color.text,
  padding: "10px",
  resize: "vertical",
};
const commandGridStyle = { display: "grid", gap: theme.spacing.sm, gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))" };
const commandButtonStyle = {
  textAlign: "left",
  border: `1px solid ${theme.color.border}`,
  borderRadius: theme.radius.sm,
  backgroundColor: theme.color.bg,
  color: theme.color.text,
  padding: "11px",
  cursor: "pointer",
};
const commandLabelStyle = { display: "block", fontWeight: 900, marginBottom: "4px" };
const commandDescriptionStyle = { display: "block", color: theme.color.textMuted, fontSize: "12px", lineHeight: 1.4 };
const closeStyle = { border: "none", background: "transparent", color: theme.color.text, fontSize: "18px", cursor: "pointer" };

export default AnakinCommandSurface;
