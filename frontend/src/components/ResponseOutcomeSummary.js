import React from "react";

import ResponseOutcomeBadge from "./ResponseOutcomeBadge";
import {
  formatExecutionClauses,
  formatOutcomeStatus,
  formatOutcomeValue,
  outcomeEvidenceQuality,
  outcomeEvidenceQualityMessage,
  reasonCodeExplanation,
  relatedOutcomeIds,
} from "../utils/responseOutcomeDisplay";

function ResponseOutcomeSummary({
  outcome,
  showRelated = false,
  onOpenRelated = null,
}) {
  // Compatibility inference belongs in backend resolve_*_outcome helpers and API
  // response_outcome payloads; this component renders null as canonical no-history.
  if (!outcome) {
    return (
      <section aria-label="Response outcome summary" style={summaryStyle}>
        <p style={emptyTextStyle}>No response outcome recorded.</p>
        <p style={qualityTextStyle}>
          Not recorded — insufficient canonical evidence; not inferred as real execution.
        </p>
      </section>
    );
  }

  const reasonExplanation = reasonCodeExplanation(outcome.reason_code);
  const relatedIds = relatedOutcomeIds(outcome);
  const quality = outcomeEvidenceQuality(outcome);
  const qualityMessage = outcomeEvidenceQualityMessage(outcome);

  return (
    <section aria-label="Response outcome summary" style={summaryStyle}>
      <div style={summaryHeaderStyle}>
        <ResponseOutcomeBadge outcome={outcome} expandable={false} />
        <span style={summaryStatusStyle}>{formatOutcomeStatus(outcome)}</span>
      </div>

      {qualityMessage ? (
        <p
          role={quality === "contradiction" ? "status" : undefined}
          data-outcome-quality={quality}
          style={qualityTextStyle}
        >
          {qualityMessage}
        </p>
      ) : null}

      <dl style={definitionListStyle}>
        <div style={definitionRowStyle}>
          <dt style={termStyle}>Execution mode</dt>
          <dd style={descriptionStyle}>{formatOutcomeValue(outcome.execution_mode, "Unknown")}</dd>
        </div>
        <div style={definitionRowStyle}>
          <dt style={termStyle}>Execution state</dt>
          <dd style={descriptionStyle}>{formatOutcomeValue(outcome.execution_state, "Unknown")}</dd>
        </div>
        <div style={definitionRowStyle}>
          <dt style={termStyle}>Selected action</dt>
          <dd style={descriptionStyle}>{formatOutcomeValue(outcome.selected_action, "None selected")}</dd>
        </div>
        <div style={definitionRowStyle}>
          <dt style={termStyle}>Decision source</dt>
          <dd style={descriptionStyle}>{formatOutcomeValue(outcome.decision_source)}</dd>
        </div>
        {outcome.execution_actor ? (
          <div style={definitionRowStyle}>
            <dt style={termStyle}>Execution actor</dt>
            <dd style={descriptionStyle}>{formatOutcomeValue(outcome.execution_actor)}</dd>
          </div>
        ) : null}
        <div style={definitionRowStyle}>
          <dt style={termStyle}>Outcome summary</dt>
          <dd style={descriptionStyle}>
            {outcome.outcome_summary || formatOutcomeStatus(outcome)}
          </dd>
        </div>
        {reasonExplanation ? (
          <div style={definitionRowStyle}>
            <dt style={termStyle}>Reason</dt>
            <dd style={descriptionStyle}>{reasonExplanation}</dd>
          </div>
        ) : null}
      </dl>

      <ul aria-label="Execution evidence" style={evidenceListStyle}>
        {formatExecutionClauses(outcome).map((clause) => (
          <li key={clause}>{clause}</li>
        ))}
      </ul>

      {showRelated ? (
        <dl aria-label="Related response outcome identifiers" style={relatedListStyle}>
          {relatedIds.map(([label, value, kind]) => (
            <div key={label} style={definitionRowStyle}>
              <dt style={termStyle}>{label}</dt>
              <dd style={descriptionStyle}>
                {value === undefined || value === null || value === "" ? (
                  "Unavailable"
                ) : typeof onOpenRelated === "function" ? (
                  <button
                    type="button"
                    onClick={() => onOpenRelated({ kind, id: value, outcome })}
                    style={relatedLinkStyle}
                    title={`Open linked ${kind} record ${value}`}
                  >
                    {value}
                  </button>
                ) : (
                  value
                )}
              </dd>
            </div>
          ))}
        </dl>
      ) : null}
    </section>
  );
}

const summaryStyle = {
  color: "#c9d1d9",
  fontSize: "13px",
};

const summaryHeaderStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  flexWrap: "wrap",
  marginBottom: "10px",
};

const summaryStatusStyle = {
  color: "#9ca3af",
  fontSize: "12px",
  fontWeight: "600",
};

const emptyTextStyle = {
  margin: 0,
  color: "#9ca3af",
};

const qualityTextStyle = {
  margin: "0 0 10px",
  color: "#fcd34d",
  fontSize: "12px",
  fontWeight: "600",
  lineHeight: 1.4,
};

const definitionListStyle = {
  display: "grid",
  gap: "8px",
  margin: "0 0 10px",
};

const relatedListStyle = {
  display: "grid",
  gap: "6px",
  margin: "10px 0 0",
  paddingTop: "10px",
  borderTop: "1px solid rgba(148, 163, 184, 0.16)",
};

const definitionRowStyle = {
  display: "grid",
  gridTemplateColumns: "minmax(120px, max-content) 1fr",
  gap: "10px",
  alignItems: "baseline",
};

const termStyle = {
  color: "#94a3b8",
  fontSize: "11px",
  fontWeight: "700",
  textTransform: "uppercase",
};

const descriptionStyle = {
  margin: 0,
  color: "#e5e7eb",
};

const evidenceListStyle = {
  display: "grid",
  gap: "4px",
  margin: "0",
  paddingLeft: "18px",
  color: "#cbd5e1",
};

const relatedLinkStyle = {
  padding: 0,
  border: "none",
  background: "transparent",
  color: "#58a6ff",
  cursor: "pointer",
  font: "inherit",
  textDecoration: "underline",
};

export default ResponseOutcomeSummary;
