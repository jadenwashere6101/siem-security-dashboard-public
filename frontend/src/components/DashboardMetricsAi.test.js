import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import DashboardMetrics from "./DashboardMetrics";

const style = {};

test("DashboardMetrics exposes contextual dashboard AI action", async () => {
  const onAskAi = jest.fn();
  render(
    <DashboardMetrics
      metrics={{ totalAlerts: 1, highCount: 1, mediumCount: 0, lowCount: 0, uniqueIPs: 1 }}
      metricsGridStyle={style}
      metricCardStyle={style}
      metricLabelStyle={style}
      metricValueStyle={style}
      onAskAi={onAskAi}
      aiEnabled
    />
  );

  await userEvent.click(screen.getByRole("button", { name: "Ask AI about dashboard" }));
  await userEvent.click(screen.getByRole("button", { name: "Draft checklist" }));

  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      contextType: "dashboard",
      action: "ask_dashboard",
    })
  );
  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      contextType: "dashboard",
      draftType: "investigation_checklist",
    })
  );
});
