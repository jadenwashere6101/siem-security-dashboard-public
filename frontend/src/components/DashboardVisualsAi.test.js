import { render, screen } from "@testing-library/react";
import DashboardVisuals from "./DashboardVisuals";

jest.mock("./MapView", () => () => <div>Map</div>);
jest.mock("./SeverityChart", () => () => <div>Severity chart</div>);
jest.mock("./TimelineChart", () => () => <div>Timeline chart</div>);
jest.mock("./TopIPChart", () => () => <div>Top IP chart</div>);

const style = {};

test("DashboardVisuals does not duplicate dashboard AI controls", () => {
  const onAskAi = jest.fn();
  render(
    <DashboardVisuals
      metrics={{}}
      topIPChartData={[]}
      alertTimelineData={[]}
      mapMarkers={[]}
      chartsGridStyle={style}
      tooltipStyle={style}
      tooltipLabelStyle={style}
      tooltipItemStyle={style}
      cardStyle={style}
      cardHeaderStyle={style}
      cardTitleStyle={style}
      cardSubtitleStyle={style}
      timelineRange="7d"
      onTimelineRangeChange={() => {}}
      timelineMeta={{}}
      summaryPendingLabel=""
      summaryBusy={false}
      displaySettings={{}}
      onAskAi={onAskAi}
      aiEnabled
    />
  );

  expect(screen.queryByRole("button", { name: "Explain graph/anomaly" })).not.toBeInTheDocument();
  expect(onAskAi).not.toHaveBeenCalled();
});

test("DashboardVisuals shows map truncation notice when summary is capped", () => {
  render(
    <DashboardVisuals
      metrics={{}}
      topIPChartData={[]}
      alertTimelineData={[]}
      mapMarkers={[{ source_ip: "8.8.8.8" }]}
      mapMarkersMeta={{ total: 1250, returned: 500, truncated: true }}
      chartsGridStyle={style}
      tooltipStyle={style}
      tooltipLabelStyle={style}
      tooltipItemStyle={style}
      cardStyle={style}
      cardHeaderStyle={style}
      cardTitleStyle={style}
      cardSubtitleStyle={style}
      timelineRange="7d"
      onTimelineRangeChange={() => {}}
      timelineMeta={{}}
      summaryPendingLabel=""
      summaryBusy={false}
      displaySettings={{}}
    />
  );

  expect(screen.getByRole("status")).toHaveTextContent("Showing top 500 of 1250 sources");
});

test("DashboardVisuals omits map truncation notice when summary is not capped", () => {
  render(
    <DashboardVisuals
      metrics={{}}
      topIPChartData={[]}
      alertTimelineData={[]}
      mapMarkers={[]}
      mapMarkersMeta={{ total: 5, returned: 5, truncated: false }}
      chartsGridStyle={style}
      tooltipStyle={style}
      tooltipLabelStyle={style}
      tooltipItemStyle={style}
      cardStyle={style}
      cardHeaderStyle={style}
      cardTitleStyle={style}
      cardSubtitleStyle={style}
      timelineRange="7d"
      onTimelineRangeChange={() => {}}
      timelineMeta={{}}
      summaryPendingLabel=""
      summaryBusy={false}
      displaySettings={{}}
    />
  );

  expect(screen.queryByRole("status")).not.toBeInTheDocument();
});
