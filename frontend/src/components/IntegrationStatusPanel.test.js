import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import IntegrationStatusPanel from "./IntegrationStatusPanel";
import { getIntegrationStatus } from "../services/integrationService";

jest.mock("../services/integrationService", () => ({
  getIntegrationStatus: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
};

const sampleStatus = {
  mode: "simulation",
  simulated: true,
  real_mode_enabled: false,
  real_mode_status: "disabled",
  adapters: [
    {
      name: "slack",
      mode: "simulation",
      simulated: true,
      real_client: false,
      supported_actions: ["send_message"],
    },
    {
      name: "email",
      mode: "simulation",
      simulated: true,
      supported_actions: ["send_email"],
    },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
});

test("shows loading state while request is in flight", async () => {
  getIntegrationStatus.mockImplementation(
    () =>
      new Promise((resolve) => {
        setTimeout(() => resolve(sampleStatus), 60);
      })
  );

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(screen.getByText(/loading integration status/i)).toBeInTheDocument();
  expect(screen.getByRole("note")).toHaveTextContent(/simulation only/i);

  await waitFor(() => {
    expect(screen.getByText("slack")).toBeInTheDocument();
  });
});

test("renders error state on API failure and allows retry", async () => {
  getIntegrationStatus.mockRejectedValueOnce(new Error("Network down"));

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText(/error: network down/i)).toBeInTheDocument();
  expect(screen.queryByText(/mode summary/i)).not.toBeInTheDocument();
  expect(screen.getByRole("note")).toHaveTextContent(/simulation only/i);

  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);
  await userEvent.click(screen.getByRole("button", { name: /retry/i }));

  expect(await screen.findByText(/mode summary/i)).toBeInTheDocument();
});

test("renders empty state when adapters is empty or missing", async () => {
  getIntegrationStatus.mockResolvedValueOnce({
    mode: "simulation",
    simulated: true,
    real_mode_enabled: false,
    real_mode_status: "disabled",
    adapters: [],
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText(/no integration adapters registered/i)).toBeInTheDocument();
  expect(screen.getByText("simulation")).toBeInTheDocument();
});

test("renders empty state when adapters is null", async () => {
  getIntegrationStatus.mockResolvedValueOnce({
    mode: "simulation",
    simulated: true,
    real_mode_enabled: false,
    real_mode_status: "disabled",
    adapters: null,
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText(/no integration adapters registered/i)).toBeInTheDocument();
});

test("mode summary shows mode, simulated, real mode disabled, and real_mode_status", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText(/mode summary/i)).toBeInTheDocument();
  expect(screen.getAllByText("simulation").length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByText("Yes").length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText("Real mode disabled")).toBeInTheDocument();
  expect(screen.getByText("disabled", { exact: true })).toBeInTheDocument();
});

test("each adapter row shows name and supported actions", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("slack")).toBeInTheDocument();
  expect(screen.getByText("send_message")).toBeInTheDocument();
  expect(screen.getByText("email")).toBeInTheDocument();
  expect(screen.getByText("send_email")).toBeInTheDocument();
});

test("simulation notice remains visible when data is loaded", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findByText("slack");

  expect(screen.getByRole("note")).toHaveTextContent(/no real outbound/i);
});

test("does not render test-connection, run, or execute controls", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findByText("slack");

  expect(screen.queryByRole("button", { name: /test connection/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /run adapter/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /execute/i })).not.toBeInTheDocument();
});

test("does not crash when supported_actions is missing for an adapter", async () => {
  getIntegrationStatus.mockResolvedValueOnce({
    ...sampleStatus,
    adapters: [{ name: "firewall", mode: "simulation", simulated: true }],
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("firewall")).toBeInTheDocument();
  expect(screen.getByText(/none listed/i)).toBeInTheDocument();
});

test("does not crash when adapters is undefined on success payload", async () => {
  getIntegrationStatus.mockResolvedValueOnce({
    mode: "simulation",
    simulated: true,
    real_mode_enabled: false,
    real_mode_status: "disabled",
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText(/no integration adapters registered/i)).toBeInTheDocument();
});
