import React from "react";
import MapView from "./MapView";
import SeverityChart from "./SeverityChart";
import TimelineChart from "./TimelineChart";
import TopIPChart from "./TopIPChart";

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
}) {
  return (
    <>
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
