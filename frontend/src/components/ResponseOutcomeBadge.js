import React from "react";

import {
  buildOutcomeEvidenceLines,
  outcomeColor,
  outcomeEvidenceQuality,
  outcomeLabel,
  outcomeToneStyle,
} from "../utils/responseOutcomeDisplay";

function buildAriaLabel(outcome, label) {
  if (!outcome) {
    return `Response outcome: ${label}; no canonical outcome recorded`;
  }

  return [
    `Response outcome: ${label}`,
    `mode ${outcome.execution_mode || "unknown"}`,
    `state ${outcome.execution_state || "unknown"}`,
  ].join("; ");
}

function ResponseOutcomeBadge({ outcome, expandable = true }) {
  const label = outcomeLabel(outcome);
  const tone = outcomeColor(outcome);
  const quality = outcomeEvidenceQuality(outcome);
  const badge = (
    <span
      aria-label={buildAriaLabel(outcome, label)}
      data-outcome-tone={tone}
      data-outcome-quality={quality}
      style={{
        ...badgeStyle,
        ...outcomeToneStyle(outcome),
      }}
    >
      {label}
    </span>
  );

  if (!expandable) {
    return badge;
  }

  const evidenceLines = buildOutcomeEvidenceLines(outcome);

  return (
    <details style={detailsStyle}>
      <summary style={summaryStyle} aria-label={`${label} outcome evidence`}>
        {badge}
        <span style={hintStyle}>Evidence</span>
      </summary>
      <ul aria-label="Canonical outcome evidence" style={evidenceListStyle}>
        {evidenceLines.map((line) => (
          <li key={line}>{line}</li>
        ))}
      </ul>
    </details>
  );
}

const detailsStyle = {
  display: "inline-block",
  maxWidth: "100%",
  verticalAlign: "middle",
};

const summaryStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  cursor: "pointer",
  listStyle: "none",
};

const hintStyle = {
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "600",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const badgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  minHeight: "22px",
  padding: "3px 8px",
  borderRadius: "999px",
  fontSize: "11px",
  fontWeight: "700",
  lineHeight: 1.2,
  whiteSpace: "nowrap",
};

const evidenceListStyle = {
  margin: "6px 0 0",
  paddingLeft: "16px",
  color: "#c9d1d9",
  fontSize: "11px",
  lineHeight: 1.45,
  maxWidth: "320px",
};

export default ResponseOutcomeBadge;
