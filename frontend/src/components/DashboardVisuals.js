import React from "react";
import MapView from "./MapView";
import SeverityChart from "./SeverityChart";
import TimelineChart from "./TimelineChart";
import TopIPChart from "./TopIPChart";

function DashboardVisuals({
  metrics,
  topIPChartData,
  alertTimelineData,
  sortedAlerts,
  chartsGridStyle,
  tooltipStyle,
  tooltipLabelStyle,
  tooltipItemStyle,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
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
          <MapView alerts={sortedAlerts} onOpenResponseRegistry={onOpenResponseRegistry} />
        </div>
      </div>
    </>
  );
}

export default DashboardVisuals;
