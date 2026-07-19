import React from "react";
import AiAssistantButton from "./AiAssistantButton";

function DashboardMetrics({
  metrics,
  metricsGridStyle,
  metricCardStyle,
  metricLabelStyle,
  metricValueStyle,
  onAskAi = null,
  aiEnabled = false,
}) {
  return (
    <>
      {aiEnabled && typeof onAskAi === "function" ? (
        <div style={aiBarStyle}>
          <AiAssistantButton
            onClick={() =>
              onAskAi({
                contextType: "dashboard",
                action: "ask_dashboard",
                title: "Dashboard summary",
                question: "Explain the current dashboard summary and what an analyst should focus on.",
              })
            }
          >
            Ask AI about dashboard
          </AiAssistantButton>
          <AiAssistantButton
            onClick={() =>
              onAskAi({
                contextType: "dashboard",
                action: "explain_anomaly",
                investigation: true,
                title: "Guided dashboard investigation",
                question: "Run a bounded, read-only guided investigation of the current dashboard summary and identify source-cited analyst next steps.",
                toolPolicy: { max_tool_calls: 5, time_window_hours: 24 },
              })
            }
          >
            Guided investigation
          </AiAssistantButton>
          <AiAssistantButton
            onClick={() =>
              onAskAi({
                contextType: "dashboard",
                draftType: "investigation_checklist",
                title: "Draft dashboard investigation checklist",
                instruction: "Draft a read-only investigation checklist from the visible dashboard summary. Do not run or save anything.",
              })
            }
          >
            Draft checklist
          </AiAssistantButton>
        </div>
      ) : null}
      <section style={metricsGridStyle}>
        <div style={metricCardStyle}>
          <p style={metricLabelStyle}>Total Alerts</p>
          <h3 style={metricValueStyle}>{metrics.totalAlerts}</h3>
        </div>

        <div style={metricCardStyle}>
          <p style={metricLabelStyle}>High Severity</p>
          <h3 style={metricValueStyle}>{metrics.highCount}</h3>
        </div>

        <div style={metricCardStyle}>
          <p style={metricLabelStyle}>Unique Source IPs</p>
          <h3 style={metricValueStyle}>{metrics.uniqueIPs}</h3>
        </div>

        <div style={metricCardStyle}>
          <p style={metricLabelStyle}>Medium / Low</p>
          <h3 style={metricValueStyle}>
            {metrics.mediumCount} / {metrics.lowCount}
          </h3>
        </div>
      </section>
    </>
  );
}

const aiBarStyle = {
  display: "flex",
  justifyContent: "flex-end",
  gap: "8px",
  flexWrap: "wrap",
  margin: "0 0 12px",
};

export default DashboardMetrics;
