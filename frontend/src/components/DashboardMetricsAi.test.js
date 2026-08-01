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

  expect(screen.getByText("Anakin")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Ask Anakin" }));
  await userEvent.click(screen.getByRole("button", { name: "Quick Explain" }));
  await userEvent.click(screen.getByRole("button", { name: "Deep Investigate" }));

  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      contextType: "dashboard",
      workflow: "auto",
    })
  );
  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      contextType: "dashboard",
      workflow: "quick_explain",
    })
  );
  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      contextType: "dashboard",
      workflow: "deep_investigate",
    })
  );
});
