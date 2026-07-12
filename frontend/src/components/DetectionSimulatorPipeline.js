import React from "react";

import { SIMULATOR_STAGE_DEFINITIONS, describeStageReason } from "../utils/detectionSimulatorStages";

const STATUS_META = {
  succeeded: { label: "Succeeded", symbol: "✓", style: { color: "#3fb950", borderColor: "#2ea043", background: "rgba(46,160,67,.12)" } },
  failed: { label: "Failed", symbol: "✕", style: { color: "#f85149", borderColor: "#f85149", background: "rgba(248,81,73,.12)" } },
  skipped: { label: "Skipped", symbol: "–", style: { color: "#9da7b3", borderColor: "#30363d", background: "rgba(48,54,61,.4)" } },
};

function StatusBadge({ status }) {
  const meta = STATUS_META[status] || STATUS_META.skipped;
  return (
    <span
      role="status"
      aria-label={`${meta.label} status`}
      data-status={status}
      style={{ ...statusBadgeStyle, ...meta.style }}
    >
      <span aria-hidden="true">{meta.symbol}</span> {meta.label}
    </span>
  );
}

// Pure presentation over the backend's per-stage response. This component
// does not evaluate detections, thresholds, or rules -- it only renders the
// status and reason strings the backend already computed.
function DetectionSimulatorPipeline({ stages }) {
  if (!stages) return null;

  return (
    <ol aria-label="Simulation pipeline stages" style={listStyle}>
      {SIMULATOR_STAGE_DEFINITIONS.map((stageDef, index) => {
        const stage = stages[stageDef.id] || { status: "skipped", reason: "not_reached" };
        const reasonText = describeStageReason(stage.reason);
        const isLast = index === SIMULATOR_STAGE_DEFINITIONS.length - 1;

        return (
          <li key={stageDef.id} data-stage={stageDef.id} data-status={stage.status} style={itemStyle}>
            <div style={rowStyle}>
              <span style={labelStyle}>{stageDef.label}</span>
              <StatusBadge status={stage.status} />
            </div>
            {reasonText && <p style={reasonStyle}>{reasonText}</p>}
            {!isLast && (
              <div aria-hidden="true" style={connectorStyle}>
                ↓
              </div>
            )}
          </li>
        );
      })}
    </ol>
  );
}

const listStyle = { listStyle: "none", margin: 0, padding: 0, display: "flex", flexDirection: "column", gap: "2px" };
const itemStyle = { display: "flex", flexDirection: "column" };
const rowStyle = {
  display: "flex",
  justifyContent: "space-between",
  alignItems: "center",
  gap: "12px",
  background: "#161b22",
  border: "1px solid #30363d",
  borderRadius: "8px",
  padding: "10px 14px",
};
const labelStyle = { color: "#f0f6fc", fontWeight: 600, fontSize: "14px" };
const statusBadgeStyle = {
  border: "1px solid",
  borderRadius: "999px",
  padding: "3px 10px",
  fontSize: "12px",
  fontWeight: 600,
  whiteSpace: "nowrap",
};
const reasonStyle = { margin: "6px 0 0", color: "#9da7b3", fontSize: "12px", paddingLeft: "14px" };
const connectorStyle = { textAlign: "center", color: "#484f58", fontSize: "14px", padding: "2px 0" };

export default DetectionSimulatorPipeline;
