import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DashboardVisuals from "./DashboardVisuals";

jest.mock("./MapView", () => () => <div>Map</div>);
jest.mock("./SeverityChart", () => () => <div>Severity chart</div>);
jest.mock("./TimelineChart", () => () => <div>Timeline chart</div>);
jest.mock("./TopIPChart", () => () => <div>Top IP chart</div>);

const style = {};

test("DashboardVisuals exposes dashboard graph AI action", async () => {
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

  await userEvent.click(screen.getByRole("button", { name: "Explain graph/anomaly" }));

  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      contextType: "dashboard",
      action: "explain_anomaly",
    })
  );
});
