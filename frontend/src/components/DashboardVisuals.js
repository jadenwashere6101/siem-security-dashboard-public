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
          <MapView alerts={mapMarkers} onOpenResponseRegistry={onOpenResponseRegistry} />
        </div>
      </div>
    </>
  );
}

const aiBarStyle = {
  display: "flex",
  justifyContent: "flex-end",
  margin: "0 0 12px",
};

export default DashboardVisuals;
