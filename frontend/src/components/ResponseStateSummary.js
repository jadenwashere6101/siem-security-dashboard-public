import React from "react";
import {
  dispositionSummaryLabel,
  summarizeAlertResponseState,
} from "../utils/responseStateLabels";

const wrapStyle = {
  display: "flex",
  flexWrap: "wrap",
  alignItems: "center",
  gap: "8px",
  marginTop: "8px",
  marginBottom: "8px",
  fontSize: "12px",
};

const chipStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  padding: "4px 8px",
  borderRadius: "999px",
  border: "1px solid #30363d",
  background: "#161b22",
  color: "#c9d1d9",
};

const linkStyle = {
  background: "transparent",
  border: "1px solid #388bfd",
  color: "#58a6ff",
  borderRadius: "6px",
  padding: "4px 8px",
  cursor: "pointer",
  fontSize: "12px",
};

/**
 * Compact cross-workspace response summary with optional Registry deep link.
 */
function ResponseStateSummary({
  alert = null,
  disposition = null,
  lastAction = null,
  compact = false,
  onOpenRegistry = null,
  openLabel = "Open in Response Registry",
}) {
  const fromAlert = summarizeAlertResponseState(alert);
  const label =
    dispositionSummaryLabel(disposition) ||
    fromAlert.label ||
    (lastAction ? String(lastAction) : "No response recorded");
  const detail = fromAlert.detail;

  return (
    <div
      style={wrapStyle}
      data-testid="response-state-summary"
      aria-label="Response state summary"
    >
      <span style={chipStyle}>
        <strong>Response:</strong> {label}
        {!compact && detail ? <span style={{ color: "#8b949e" }}>· {detail}</span> : null}
      </span>
      {typeof onOpenRegistry === "function" ? (
        <button type="button" onClick={onOpenRegistry} style={linkStyle}>
          {openLabel}
        </button>
      ) : null}
    </div>
  );
}

export default ResponseStateSummary;
