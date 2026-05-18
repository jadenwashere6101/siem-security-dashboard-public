import React from "react";

export const SAFETY_CAPABILITY_ROWS = [
  {
    capability: "Alert ingestion",
    model: "Real Workflow",
    meaning: "Events are stored and processed by the SIEM pipeline.",
  },
  {
    capability: "Detection/correlation",
    model: "Real Workflow",
    meaning: "Rules and correlation logic create operational alert context.",
  },
  {
    capability: "Playbook orchestration",
    model: "Real Workflow",
    meaning: "Worker leases, steps, logs, metrics, and timelines are platform behavior.",
  },
  {
    capability: "Approvals/retry/dead letters",
    model: "Real Workflow",
    meaning: "Human gates, retry state, and failure records are durable operator workflows.",
  },
  {
    capability: "Slack/Teams/Email/Webhook",
    model: "Guarded Real-Capable",
    meaning: "Outbound sends require per-adapter guards, credentials, audit, rate limits, and dedup.",
  },
  {
    capability: "Firewall/block_ip",
    model: "Dry-Run Only",
    meaning: "Firewall actions do not mutate live firewall or blocklist state.",
  },
];

function ExecutionSafetyModelPanel({ compact = false }) {
  return (
    <section
      style={compact ? compactPanelStyle : panelStyle}
      aria-label="Execution Safety Model"
    >
      <div style={headerStyle}>
        <div>
          <p style={eyebrowStyle}>Execution Safety Model</p>
          <h3 style={titleStyle}>Simulation-Safe Execution</h3>
        </div>
        <span style={badgeStyle}>Per-adapter guards</span>
      </div>
      <p style={bodyStyle}>
        Workflows, approvals, rate limits, dead letters, retry workflows, metrics, and audits are
        real operational behavior. Outbound integration execution is adapter-specific and
        guard-controlled; there is no UI control that promotes all adapters at once. Firewall
        blocking remains dry-run only.
      </p>
      {compact ? null : (
        <div style={matrixStyle} aria-label="Execution capability matrix">
          {SAFETY_CAPABILITY_ROWS.map((row) => (
            <div key={row.capability} style={matrixRowStyle}>
              <div>
                <p style={capabilityStyle}>{row.capability}</p>
                <p style={meaningStyle}>{row.meaning}</p>
              </div>
              <span style={modelBadgeStyle}>{row.model}</span>
            </div>
          ))}
        </div>
      )}
    </section>
  );
}

const panelStyle = {
  border: "1px solid #30363d",
  borderRadius: "8px",
  background: "#0d1117",
  padding: "16px",
};

const compactPanelStyle = {
  ...panelStyle,
  padding: "12px",
};

const headerStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  alignItems: "flex-start",
  marginBottom: "10px",
  flexWrap: "wrap",
};

const eyebrowStyle = {
  margin: "0 0 4px",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.12em",
  textTransform: "uppercase",
};

const titleStyle = {
  margin: 0,
  color: "#f0f6fc",
  fontSize: "16px",
};

const badgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  borderRadius: "999px",
  color: "#79c0ff",
  background: "rgba(56, 139, 253, 0.12)",
  fontSize: "11px",
  fontWeight: "700",
  padding: "4px 8px",
};

const bodyStyle = {
  margin: "0 0 12px",
  color: "#c9d1d9",
  fontSize: "13px",
  lineHeight: 1.5,
};

const matrixStyle = {
  display: "grid",
  gap: "8px",
};

const matrixRowStyle = {
  display: "grid",
  gridTemplateColumns: "minmax(0, 1fr) auto",
  gap: "12px",
  alignItems: "center",
  borderTop: "1px solid #21262d",
  paddingTop: "8px",
};

const capabilityStyle = {
  margin: "0 0 2px",
  color: "#f0f6fc",
  fontSize: "13px",
  fontWeight: "700",
};

const meaningStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
  lineHeight: 1.4,
};

const modelBadgeStyle = {
  ...badgeStyle,
  borderColor: "rgba(63, 185, 80, 0.35)",
  color: "#7ee787",
  background: "rgba(46, 160, 67, 0.12)",
  whiteSpace: "nowrap",
};

export default ExecutionSafetyModelPanel;
