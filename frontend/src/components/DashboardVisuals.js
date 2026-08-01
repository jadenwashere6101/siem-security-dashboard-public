import React from "react";
import MapView from "./MapView";
import SeverityChart from "./SeverityChart";
import TimelineChart from "./TimelineChart";
import TopIPChart from "./TopIPChart";
import AiAssistantButton from "./AiAssistantButton";

function DashboardVisuals({
  metrics,
  topIPChartData,
  alertTimelineData,
  mapMarkers,
  mapMarkersMeta,
  chartsGridStyle,
  tooltipStyle,
  tooltipLabelStyle,
  tooltipItemStyle,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  timelineRange,
  onTimelineRangeChange,
  timelineMeta,
  summaryPendingLabel,
  summaryBusy,
  displaySettings,
  onOpenResponseRegistry = null,
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
                action: "explain_anomaly",
                title: "Dashboard graph explanation",
                question: "Explain notable patterns, spikes, or anomalies in the visible dashboard graphs.",
              })
            }
          >
            Explain graph/anomaly
          </AiAssistantButton>
          <AiAssistantButton
            onClick={() =>
              onAskAi({
                contextType: "dashboard",
                action: "explain_anomaly",
                investigation: true,
                title: "Guided dashboard anomaly investigation",
                question: "Run a bounded, read-only guided investigation of visible dashboard anomalies with source-cited evidence.",
                toolPolicy: { max_tool_calls: 5, time_window_hours: 24 },
              })
            }
          >
            Guided investigation
          </AiAssistantButton>
        </div>
      ) : null}
      <div style={chartsGridStyle}>
        <SeverityChart
          metrics={metrics}
          tooltipStyle={tooltipStyle}
          tooltipLabelStyle={tooltipLabelStyle}
          tooltipItemStyle={tooltipItemStyle}
          cardStyle={cardStyle}
          cardHeaderStyle={cardHeaderStyle}
          cardTitleStyle={cardTitleStyle}
        />

        <TopIPChart
          data={topIPChartData}
          tooltipStyle={tooltipStyle}
          tooltipLabelStyle={tooltipLabelStyle}
          tooltipItemStyle={tooltipItemStyle}
          cardStyle={cardStyle}
          cardHeaderStyle={cardHeaderStyle}
          cardTitleStyle={cardTitleStyle}
        />
      </div>

      <TimelineChart
        data={alertTimelineData}
        tooltipStyle={tooltipStyle}
        tooltipLabelStyle={tooltipLabelStyle}
        tooltipItemStyle={tooltipItemStyle}
        cardStyle={cardStyle}
        cardHeaderStyle={cardHeaderStyle}
        cardTitleStyle={cardTitleStyle}
        timelineRange={timelineRange}
        onTimelineRangeChange={onTimelineRangeChange}
        timelineMeta={timelineMeta}
        summaryPendingLabel={summaryPendingLabel}
        summaryBusy={summaryBusy}
        displaySettings={displaySettings}
      />
      <div style={cardStyle}>
        <div style={cardHeaderStyle}>
          <h2 style={cardTitleStyle}>Attack Map</h2>
          <p style={cardSubtitleStyle}>
            Alert locations based on source IP geolocation
          </p>
        </div>
        <div style={{ padding: "20px" }}>
          {mapMarkersMeta?.truncated ? (
            <div style={mapLimitNoticeStyle} role="status">
              Showing top {mapMarkersMeta.returned} of {mapMarkersMeta.total} sources
            </div>
          ) : null}
          <MapView alerts={mapMarkers} onOpenResponseRegistry={onOpenResponseRegistry} />
        </div>
      </div>
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

const mapLimitNoticeStyle = {
  display: "inline-flex",
  alignItems: "center",
  margin: "0 0 12px",
  padding: "6px 10px",
  borderRadius: "6px",
  border: "1px solid rgba(251, 191, 36, 0.32)",
  background: "rgba(251, 191, 36, 0.1)",
  color: "#facc15",
  fontSize: "12px",
  fontWeight: 700,
};

export default DashboardVisuals;
