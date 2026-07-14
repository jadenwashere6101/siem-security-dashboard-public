import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import NotificationPolicyPanel from "./NotificationPolicyPanel";
import * as service from "../services/notificationPolicyService";

jest.mock("../services/notificationPolicyService");

const basePolicy = {
  slack_enabled: false,
  minimum_severity: "high",
  notify_on_alerts: true,
  notify_on_incidents: true,
  slack_format: "compact",
  pfsense_destination: "pfSense destination",
  honeypot_destination: "Honeypot destination",
  critical_cross_source_destination: "Critical / Cross-Source Security destination",
  updated_at: "2026-07-14T12:00:00Z",
  updated_by: "testadmin",
};

const props = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
};

beforeEach(() => {
  service.loadNotificationPolicy.mockResolvedValue(basePolicy);
  service.updateNotificationPolicy.mockResolvedValue({
    ...basePolicy,
    slack_enabled: true,
    slack_format: "detailed",
    pfsense_destination: "#soc-pfsense",
    honeypot_destination: "#soc-honeypot",
    critical_cross_source_destination: "#soc-critical",
  });
  service.testNotificationPolicyRoute.mockResolvedValue({
    success: true,
    status: "success",
    message: "Notification policy route test sent for pfsense.",
  });
});

test("renders policy controls and suppression note", async () => {
  render(<NotificationPolicyPanel {...props} />);

  expect(await screen.findByRole("heading", { name: "Notification Policy" })).toBeInTheDocument();
  expect(await screen.findByLabelText("Slack notifications enabled")).not.toBeChecked();
  expect(screen.getByLabelText("Minimum severity")).toHaveValue("high");
  expect(screen.getByText(/Slack credentials remain in the existing runtime secret mechanism/i)).toBeInTheDocument();
  expect(screen.getByText(/Policy suppression affects Slack delivery only/i)).toBeInTheDocument();
});

test("saves the edited policy and reloads the rendered values", async () => {
  render(<NotificationPolicyPanel {...props} />);

  fireEvent.click(await screen.findByLabelText("Slack notifications enabled"));
  fireEvent.change(screen.getByLabelText("Slack format"), { target: { value: "detailed" } });
  fireEvent.change(screen.getByLabelText("pfSense destination label"), {
    target: { value: "#soc-pfsense" },
  });
  fireEvent.change(screen.getByLabelText("Honeypot destination label"), {
    target: { value: "#soc-honeypot" },
  });
  fireEvent.change(screen.getByLabelText("Critical cross-source destination label"), {
    target: { value: "#soc-critical" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save notification policy" }));

  await waitFor(() =>
    expect(service.updateNotificationPolicy).toHaveBeenCalledWith({
      slack_enabled: true,
      minimum_severity: "high",
      notify_on_alerts: true,
      notify_on_incidents: true,
      slack_format: "detailed",
      pfsense_destination: "#soc-pfsense",
      honeypot_destination: "#soc-honeypot",
      critical_cross_source_destination: "#soc-critical",
    })
  );
  expect(await screen.findByRole("status")).toHaveTextContent("Notification policy updated.");
  expect(screen.getByLabelText("Slack notifications enabled")).toBeChecked();
});

test("exposes navigation links to the matrix and detection rules", async () => {
  const onNavigate = jest.fn();
  render(<NotificationPolicyPanel {...props} onNavigate={onNavigate} />);

  fireEvent.click(await screen.findByRole("button", { name: "Open Severity & Response Matrix" }));
  fireEvent.click(screen.getByRole("button", { name: "Open Detection Rules" }));

  expect(onNavigate).toHaveBeenNthCalledWith(1, "severity-response-matrix");
  expect(onNavigate).toHaveBeenNthCalledWith(2, "detection-rules");
});

test("announces backend failures accessibly", async () => {
  service.loadNotificationPolicy.mockRejectedValue(new Error("Forbidden"));

  render(<NotificationPolicyPanel {...props} />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Forbidden");
});

test("runs a pfSense route test and shows success feedback", async () => {
  render(<NotificationPolicyPanel {...props} />);

  fireEvent.click(await screen.findByRole("button", { name: "Test pfSense route" }));

  await waitFor(() => expect(service.testNotificationPolicyRoute).toHaveBeenCalledWith("pfsense"));
  expect(await screen.findByRole("status")).toHaveTextContent(
    "Notification policy route test sent for pfsense."
  );
});

test("shows route test failures accessibly", async () => {
  service.testNotificationPolicyRoute.mockRejectedValue(new Error("Missing route-specific webhook"));

  render(<NotificationPolicyPanel {...props} />);

  fireEvent.click(await screen.findByRole("button", { name: "Test Honeypot route" }));

  await waitFor(() => expect(service.testNotificationPolicyRoute).toHaveBeenCalledWith("honeypot"));
  expect(await screen.findByRole("alert")).toHaveTextContent("Missing route-specific webhook");
});
