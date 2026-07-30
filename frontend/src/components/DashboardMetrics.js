import React from "react";
import AiAssistantButton from "./AiAssistantButton";
import { MetricCard } from "./uiPrimitives";

function dashboardMetricModels(metrics) {
  const high = Number(metrics.highCount) || 0;
  const total = Number(metrics.totalAlerts) || 0;
  const medium = Number(metrics.mediumCount) || 0;
  const low = Number(metrics.lowCount) || 0;
  const unique = Number(metrics.uniqueIPs) || 0;
  const lowerPriorityTone = getLowerPriorityTone(medium, low);
  return [
    {
      label: "Total Alerts",
      value: total,
      tone: total > 0 ? "info" : "neutral",
      summary: total > 0 ? "Current filtered alert volume." : "No alerts in the current filtered view.",
      why: total > 0 ? "Volume sets the triage workload for this dashboard view." : "An empty view can indicate filters are narrow or ingestion is quiet.",
    },
    {
      label: "High Severity",
      value: high,
      tone: high > 0 ? "danger" : "neutral",
      summary: high > 0 ? "High-priority alerts are present." : "No high-severity alerts in view.",
      why: high > 0 ? "High-severity alerts are the first candidates for analyst review." : null,
    },
    {
      label: "Unique Source IPs",
      value: unique,
      tone: unique > 0 ? "info" : "neutral",
      summary: unique > 0 ? "Distinct sources represented in the current data." : "No source diversity to evaluate.",
      why: unique > 1 ? "Multiple sources can indicate distributed activity or broad scanning." : null,
    },
    {
      label: "Medium / Low",
      value: `${medium} / ${low}`,
      tone: lowerPriorityTone,
      summary: "Lower-priority workload split.",
      why: medium > 0 ? "Medium alerts may contain early indicators that deserve review after urgent items." : null,
    },
  ];
}

function getLowerPriorityTone(medium, low) {
  if (medium > 0) return "warning";
  if (low > 0) return "success";
  return "neutral";
}

function DashboardMetrics({
  metrics,
  metricsGridStyle,
  onAskAi = null,
  aiEnabled = false,
}) {
  return (
    <>
      {aiEnabled && typeof onAskAi === "function" ? (
        <div style={aiBarStyle}>
          <span style={agentClusterLabelStyle}>Anakin analyst tools</span>
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
            Dashboard summary
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
        {dashboardMetricModels(metrics).map((item) => (
          <MetricCard
            key={item.label}
            label={item.label}
            value={item.value}
            tone={item.tone}
            summary={item.summary}
            why={item.why}
          />
        ))}
      </section>
    </>
  );
}

const aiBarStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  gap: "8px",
  flexWrap: "wrap",
  margin: "0 0 12px",
};

const agentClusterLabelStyle = {
  color: "#93c5fd",
  fontSize: "11px",
  fontWeight: 800,
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

export default DashboardMetrics;
