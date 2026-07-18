import React from "react";
import { providerCostLabel, providerStatusLabel, sourceCountLabel, toolUsageLabel } from "../utils/aiDisplay";

function AiResponsePanel({
  state,
  onDismiss,
  onRetry,
  onCancel,
}) {
  if (!state || state.status === "idle") return null;
  const busy = state.status === "loading";
  const response = state.response || {};
  const metadata = response.metadata;
  const context = response.context;
  const tools = response.tools;
  const toolCalls = Array.isArray(tools?.calls) ? tools.calls : [];

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-label="AI assistant response"
      style={panelStyle}
    >
      <div style={headerStyle}>
        <div>
          <p style={eyebrowStyle}>Read-only AI assistant</p>
          <h2 style={titleStyle}>{state.title || "SIEM AI"}</h2>
        </div>
        <button type="button" onClick={onDismiss} aria-label="Dismiss AI response" style={iconButtonStyle}>
          ×
        </button>
      </div>

      {busy ? (
        <div style={bodyStyle}>
          <p style={mutedStyle}>Analyzing current SIEM context...</p>
          <button type="button" onClick={onCancel} style={secondaryButtonStyle}>Cancel</button>
        </div>
      ) : null}

      {state.status === "error" ? (
        <div style={bodyStyle}>
          <p style={errorStyle}>{state.error || "AI request failed."}</p>
          <button type="button" onClick={onRetry} style={primaryButtonStyle}>Retry</button>
        </div>
      ) : null}

      {state.status === "success" ? (
        <div style={bodyStyle}>
          {response.insufficient_context ? (
            <p style={warningStyle}>{response.error || "There was not enough SIEM context to answer safely."}</p>
          ) : null}
          <div style={answerStyle}>{response.answer || response.error || "No AI answer was returned."}</div>
          {state.stale ? (
            <p style={warningStyle}>This answer may be stale because the visible SIEM context changed.</p>
          ) : null}
          <div style={metadataStyle}>
            <span>{providerStatusLabel(metadata)}</span>
            <span>{providerCostLabel(metadata)}</span>
            <span>{sourceCountLabel(context)}</span>
            <span>{toolUsageLabel(tools)}</span>
          </div>
          {tools?.used ? (
            <div style={toolBoxStyle} aria-label="Read-only AI tool evidence">
              <p style={toolTitleStyle}>Read-only investigation evidence</p>
              {toolCalls.length ? (
                <ul style={toolListStyle}>
                  {toolCalls.map((call, index) => (
                    <li key={`${call.tool_name || "tool"}-${index}`} style={toolItemStyle}>
                      <strong>{call.tool_name || "unknown_tool"}</strong>
                      <span>{call.status || "unknown"}</span>
                      <span>{Array.isArray(call.sources) ? call.sources.length : 0} sources</span>
                      {call.truncated ? <span>truncated</span> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={mutedStyle}>No read-tool evidence was returned.</p>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}

const panelStyle = {
  position: "fixed",
  right: "18px",
  bottom: "88px",
  width: "min(440px, calc(100vw - 28px))",
  maxHeight: "70vh",
  overflowY: "auto",
  zIndex: 9997,
  border: "1px solid rgba(125, 211, 252, 0.35)",
  borderRadius: "18px",
  background: "linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(2, 6, 23, 0.98))",
  color: "#e2e8f0",
  boxShadow: "0 24px 80px rgba(0, 0, 0, 0.45)",
};

const headerStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  padding: "16px 18px",
  borderBottom: "1px solid rgba(148, 163, 184, 0.2)",
};

const eyebrowStyle = { margin: 0, color: "#67e8f9", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" };
const titleStyle = { margin: "4px 0 0", fontSize: "18px" };
const iconButtonStyle = { background: "transparent", color: "#e2e8f0", border: "none", fontSize: "24px", cursor: "pointer" };
const bodyStyle = { padding: "16px 18px" };
const mutedStyle = { margin: 0, color: "#94a3b8" };
const errorStyle = { margin: "0 0 12px", color: "#fca5a5" };
const warningStyle = { margin: "0 0 12px", color: "#fde68a" };
const answerStyle = { whiteSpace: "pre-wrap", lineHeight: 1.6, fontSize: "14px" };
const metadataStyle = { display: "grid", gap: "4px", marginTop: "14px", color: "#94a3b8", fontSize: "12px" };
const primaryButtonStyle = { border: "none", borderRadius: "8px", padding: "8px 12px", background: "#0ea5e9", color: "#fff", cursor: "pointer" };
const secondaryButtonStyle = { ...primaryButtonStyle, background: "#334155" };
const toolBoxStyle = { marginTop: "14px", border: "1px solid rgba(148, 163, 184, 0.22)", borderRadius: "12px", padding: "12px", background: "rgba(15, 23, 42, 0.68)" };
const toolTitleStyle = { margin: "0 0 8px", color: "#bae6fd", fontSize: "12px", fontWeight: 800 };
const toolListStyle = { listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "8px" };
const toolItemStyle = { display: "flex", flexWrap: "wrap", gap: "8px", justifyContent: "space-between", color: "#cbd5e1", fontSize: "12px" };

export default AiResponsePanel;
