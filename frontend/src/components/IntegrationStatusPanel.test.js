import React from "react";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import IntegrationStatusPanel from "./IntegrationStatusPanel";
import { readStoredSessionIdentity } from "../utils/sessionIdentity";
import {
  enableHalfOpenIntegrationCircuitBreaker,
  forceOpenIntegrationCircuitBreaker,
  getIntegrationStatus,
  resetIntegrationCircuitBreaker,
} from "../services/integrationService";

jest.mock("../utils/sessionIdentity", () => ({
  readStoredSessionIdentity: jest.fn(),
}));

jest.mock("../services/integrationService", () => ({
  getIntegrationStatus: jest.fn(),
  resetIntegrationCircuitBreaker: jest.fn(),
  forceOpenIntegrationCircuitBreaker: jest.fn(),
  enableHalfOpenIntegrationCircuitBreaker: jest.fn(),
}));

const styleProps = {
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
};

const sampleCircuitClosed = {
  state: "closed",
  consecutive_failures: 0,
  failure_threshold: 3,
  cooldown_seconds: 60,
  cooldown_until: null,
  last_failure_reason: null,
  last_failure_classification: null,
  timeout_seconds: 30,
  retry_eligible: true,
  half_open_probe_available: false,
  last_manual_action: null,
  last_manual_action_by: null,
  last_manual_action_at: null,
  last_manual_reason: null,
  state_persisted: false,
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
      circuit_breaker: sampleCircuitClosed,
    },
    {
      name: "email",
      mode: "simulation",
      simulated: true,
      supported_actions: ["send_email"],
      circuit_breaker: sampleCircuitClosed,
    },
  ],
};

/** One adapter simplifies super-admin control queries (single reason field / button set). */
const sampleStatusSingleAdapter = {
  ...sampleStatus,
  adapters: [sampleStatus.adapters[0]],
};

beforeEach(() => {
  jest.clearAllMocks();
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "analyst",
    username: "analyst1",
  });
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
  expect(screen.getByRole("note")).toHaveTextContent(/adapter-specific and guard-controlled/i);
  expect(screen.getByText("Execution Safety Model")).toBeInTheDocument();

  await waitFor(() => {
    expect(screen.getByText("slack")).toBeInTheDocument();
  });
});

test("renders error state on API failure and allows retry", async () => {
  getIntegrationStatus.mockRejectedValueOnce(new Error("Network down"));

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText(/error: network down/i)).toBeInTheDocument();
  expect(screen.queryByText(/mode summary/i)).not.toBeInTheDocument();
  expect(screen.getByRole("note")).toHaveTextContent(/simulation-safe execution is the default/i);

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
  expect(screen.getAllByText("Real Integration Disabled").length).toBeGreaterThanOrEqual(1);
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

test("renders circuit breaker fields and in-memory simulation copy when present", async () => {
  getIntegrationStatus.mockResolvedValueOnce({
    mode: "simulation",
    simulated: true,
    real_mode_enabled: false,
    real_mode_status: "disabled",
    adapters: [
      {
        name: "webhook",
        mode: "simulation",
        simulated: true,
        real_client: false,
        supported_actions: ["post_event"],
        circuit_breaker: {
          state: "open",
          consecutive_failures: 3,
          failure_threshold: 5,
          cooldown_seconds: 120,
          cooldown_until: "2026-05-10T18:30:00Z",
          last_failure_reason: "simulated timeout",
          last_failure_classification: "transient_timeout",
          timeout_seconds: 15,
          retry_eligible: false,
          state_persisted: false,
        },
      },
    ],
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("webhook")).toBeInTheDocument();
  expect(screen.getByText(/circuit breaker state is simulation-only/i)).toBeInTheDocument();
  expect(screen.getByText(/stored in memory on the server/i)).toBeInTheDocument();
  expect(screen.getByText("open")).toBeInTheDocument();
  expect(screen.getByText("3")).toBeInTheDocument();
  expect(screen.getByText("5")).toBeInTheDocument();
  expect(screen.getByText("120")).toBeInTheDocument();
  expect(screen.getByText("2026-05-10T18:30:00Z")).toBeInTheDocument();
  expect(screen.getByText("simulated timeout")).toBeInTheDocument();
  expect(screen.getByText("transient_timeout")).toBeInTheDocument();
  expect(screen.getByText("15")).toBeInTheDocument();
  expect(screen.getAllByText("No").length).toBeGreaterThanOrEqual(1);
});

test("omits circuit breaker block when adapter has no circuit_breaker", async () => {
  getIntegrationStatus.mockResolvedValueOnce({
    mode: "simulation",
    simulated: true,
    real_mode_enabled: false,
    real_mode_status: "disabled",
    adapters: [
      {
        name: "firewall",
        mode: "simulation",
        simulated: true,
        supported_actions: ["block_ip"],
      },
    ],
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("firewall")).toBeInTheDocument();
  expect(screen.getByText("Dry-Run Only")).toBeInTheDocument();
  expect(screen.queryByText(/circuit breaker state is simulation-only/i)).not.toBeInTheDocument();
});

test("simulation notice remains visible when data is loaded", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findByText("slack");

  expect(screen.getByRole("note")).toHaveTextContent(/guard-controlled/i);
  expect(screen.getByRole("note")).toHaveTextContent(/firewall remains dry-run only/i);
  expect(screen.getByText("Per-adapter guards")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/global.*toggle/i);
  expect(document.body).not.toHaveTextContent(/fake/i);
});

test("does not render test-connection, run, or execute controls", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findByText("slack");

  expect(screen.queryByRole("button", { name: /test connection/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /run adapter/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /execute/i })).not.toBeInTheDocument();
});

test("analyst does not see simulation circuit breaker control buttons", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findByText("slack");

  expect(screen.queryByRole("button", { name: /reset to closed/i })).not.toBeInTheDocument();
  expect(screen.getByText(/analysts have read-only access/i)).toBeInTheDocument();
});

test("super admin sees simulation circuit breaker controls", async () => {
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "super_admin",
    username: "admin",
  });
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findByText("slack");

  expect(
    screen.getAllByText(/simulation circuit breaker controls \(super admin\)/i).length
  ).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByRole("button", { name: /reset to closed/i }).length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByRole("button", { name: /force open/i }).length).toBeGreaterThanOrEqual(1);
  expect(
    screen.getAllByRole("button", { name: /enable half-open probe/i }).length
  ).toBeGreaterThanOrEqual(1);
  expect(screen.getByText(/super admins can adjust simulation circuit breakers/i)).toBeInTheDocument();
});

test("super admin must enter a reason before submitting a control", async () => {
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "super_admin",
    username: "admin",
  });
  getIntegrationStatus.mockResolvedValueOnce(sampleStatusSingleAdapter);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findByText("slack");
  await userEvent.click(screen.getByRole("button", { name: /reset to closed/i }));

  expect(await screen.findByText(/non-empty reason/i)).toBeInTheDocument();
  expect(resetIntegrationCircuitBreaker).not.toHaveBeenCalled();
});

test("super admin reset calls API and reloads status", async () => {
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "super_admin",
    username: "admin",
  });
  getIntegrationStatus.mockResolvedValue(sampleStatusSingleAdapter);
  resetIntegrationCircuitBreaker.mockResolvedValue({
    adapter: "slack",
    circuit_breaker: { ...sampleCircuitClosed },
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findByText("slack");
  await userEvent.type(
    screen.getByPlaceholderText(/describe why you are changing simulation breaker state/i),
    "post-incident review"
  );
  await userEvent.click(screen.getByRole("button", { name: /reset to closed/i }));

  await waitFor(() => {
    expect(resetIntegrationCircuitBreaker).toHaveBeenCalledWith("slack", "post-incident review");
  });
  expect(getIntegrationStatus.mock.calls.length).toBeGreaterThanOrEqual(2);
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
