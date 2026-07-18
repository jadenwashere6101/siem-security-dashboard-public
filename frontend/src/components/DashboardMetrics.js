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
  margin: "0 0 12px",
};

export default DashboardMetrics;
