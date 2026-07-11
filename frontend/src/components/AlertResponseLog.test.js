import { render, screen } from "@testing-library/react";

import AlertResponseLog from "./AlertResponseLog";

test("AlertResponseLog uses canonical outcome label when response_outcome is present", () => {
  render(
    <AlertResponseLog
      logs={[
        {
          id: 1,
          action: "block_ip",
          status: "success",
          executed_at: "2026-06-16T12:00:00Z",
          response_outcome: {
            execution_mode: "real",
            execution_state: "succeeded",
            external_executed: true,
            tracking_recorded: false,
            simulated: false,
          },
        },
      ]}
    />
  );

  expect(screen.getByText(/Real executed/)).toBeInTheDocument();
  expect(screen.queryByText(/BLOCK_IP → success/)).not.toBeInTheDocument();
});

test("AlertResponseLog preserves legacy status display without response_outcome", () => {
  const { container } = render(
    <AlertResponseLog
      logs={[
        {
          id: 1,
          action: "monitor",
          status: "success",
          executed_at: "2026-06-16T12:00:00Z",
        },
      ]}
    />
  );

  expect(screen.getByText("MONITOR")).toBeInTheDocument();
  expect(container).toHaveTextContent("MONITOR → success");
});

test("panel variant uses explicit readable dark-theme foregrounds", () => {
  render(<AlertResponseLog logs={[]} variant="panel" />);

  expect(screen.getByText("Response Log:").parentElement).toHaveStyle({ color: "#e5e7eb" });
  expect(screen.getByText("No response actions logged")).toHaveStyle({ color: "#cbd5e1" });
});
