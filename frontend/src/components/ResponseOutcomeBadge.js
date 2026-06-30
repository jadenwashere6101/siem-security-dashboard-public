import React from "react";

import { outcomeColor, outcomeLabel, outcomeToneStyle } from "../utils/responseOutcomeDisplay";

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

function ResponseOutcomeBadge({ outcome }) {
  const label = outcomeLabel(outcome);
  const tone = outcomeColor(outcome);

  return (
    <span
      aria-label={buildAriaLabel(outcome, label)}
      data-outcome-tone={tone}
      style={{
        ...badgeStyle,
        ...outcomeToneStyle(outcome),
      }}
    >
      {label}
    </span>
  );
}

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

export default ResponseOutcomeBadge;
