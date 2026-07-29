import { render, screen } from "@testing-library/react";

import { MetricCard, SeverityPill, StatusPill } from "./uiPrimitives";
import { toneForStatus } from "../theme";

test("severity and status primitives reserve red semantics for critical or failed states", () => {
  render(
    <>
      <SeverityPill severity="critical" />
      <StatusPill status="failed" />
      <StatusPill status="pending" />
      <StatusPill status="healthy" />
    </>
  );

  expect(screen.getByText("critical")).toHaveStyle({ color: "#fca5a5" });
  expect(screen.getByText("failed")).toHaveStyle({ color: "#fca5a5" });
  expect(screen.getByText("pending")).toHaveStyle({ color: "#f5d487" });
  expect(screen.getByText("healthy")).toHaveStyle({ color: "#86efac" });
  expect(toneForStatus("blocked")).toBe("danger");
  expect(toneForStatus("awaiting_approval")).toBe("warning");
});

test("MetricCard renders deterministic hierarchy without fabricating unavailable indicators", () => {
  render(
    <MetricCard
      label="High Severity"
      value={0}
      tone="neutral"
      summary="No high-severity alerts in view."
      why={null}
    />
  );

  expect(screen.getByText("High Severity")).toBeInTheDocument();
  expect(screen.getByText("No high-severity alerts in view.")).toBeInTheDocument();
  expect(screen.queryByText(/Trend/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Confidence/i)).not.toBeInTheDocument();
  expect(screen.queryByText(/Why this matters/i)).not.toBeInTheDocument();
});
