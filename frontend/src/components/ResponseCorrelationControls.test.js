import React from "react";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AlertManualActions from "./AlertManualActions";
import ResponseStateSummary from "./ResponseStateSummary";
import LifecycleIndependenceNotice from "./LifecycleIndependenceNotice";

test("locked alert actions are disabled and do not execute", async () => {
  const executeAction = jest.fn();
  render(
    <AlertManualActions
      alertId={1}
      sourceIp="8.8.8.8"
      executeAction={executeAction}
      executingActionId={null}
      canTakeAlertActions={false}
      getActionButtonStyle={(style) => style}
    />
  );

  const blockButton = screen.getByRole("button", { name: /Block IP/i });
  expect(blockButton).toBeDisabled();
  await userEvent.click(blockButton);
  expect(executeAction).not.toHaveBeenCalled();
  expect(screen.getByText(/Requires analyst or super-admin privileges/i)).toBeInTheDocument();
});

test("response state summary exposes registry deep link", async () => {
  const onOpenRegistry = jest.fn();
  render(
    <ResponseStateSummary
      alert={{ response_action: "monitor", response_status: "executed" }}
      onOpenRegistry={onOpenRegistry}
    />
  );
  expect(screen.getByTestId("response-state-summary")).toHaveTextContent("Monitored");
  await userEvent.click(screen.getByRole("button", { name: /Open in Response Registry/i }));
  expect(onOpenRegistry).toHaveBeenCalled();
});

test("lifecycle notice explains independent statuses", () => {
  render(<LifecycleIndependenceNotice />);
  expect(screen.getByTestId("lifecycle-independence-notice")).toHaveTextContent(
    /independent/i
  );
  expect(screen.getByTestId("lifecycle-independence-notice")).toHaveTextContent(
    /does not automatically resolve/i
  );
});
