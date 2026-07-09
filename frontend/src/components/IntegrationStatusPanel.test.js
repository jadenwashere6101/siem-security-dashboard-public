import React from "react";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import IntegrationStatusPanel from "./IntegrationStatusPanel";
import { readStoredSessionIdentity } from "../utils/sessionIdentity";
import {
  enableHalfOpenIntegrationCircuitBreaker,
  forceOpenIntegrationCircuitBreaker,
  getIntegrationStatus,
  getNotificationReadiness,
  resetIntegrationCircuitBreaker,
  sendNotificationTest,
} from "../services/integrationService";

jest.mock("../utils/sessionIdentity", () => ({
  readStoredSessionIdentity: jest.fn(),
}));

jest.mock("../services/integrationService", () => ({
  getIntegrationStatus: jest.fn(),
  getNotificationReadiness: jest.fn(),
  resetIntegrationCircuitBreaker: jest.fn(),
  forceOpenIntegrationCircuitBreaker: jest.fn(),
  enableHalfOpenIntegrationCircuitBreaker: jest.fn(),
  sendNotificationTest: jest.fn(),
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
  configured_mode: "simulation",
  simulated: true,
  real_mode_enabled: false,
  real_mode_status: "disabled",
  adapters: [
    {
      name: "slack",
      mode: "simulation",
      simulated: true,
      real_client: false,
      real_mode_ready: false,
      real_mode_allowed: false,
      webhook_configured: false,
      supported_actions: ["send_message"],
      circuit_breaker: sampleCircuitClosed,
    },
    {
      name: "email",
      mode: "simulation",
      simulated: true,
      real_client: false,
      real_mode_ready: false,
      real_mode_allowed: false,
      smtp_host_configured: true,
      smtp_username_configured: true,
      smtp_from_configured: true,
      smtp_to_configured: true,
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

const sampleReadiness = {
  providers: [
    {
      provider: "slack",
      label: "Slack",
      configured: true,
      missing_configuration: [],
      tested: "passed",
      ready: true,
      last_test_at: "2026-07-08T00:00:00+00:00",
      last_test_status: "success",
      last_test_message: null,
    },
    {
      provider: "teams",
      label: "Teams",
      configured: true,
      missing_configuration: [],
      tested: "never_tested",
      ready: false,
      last_test_at: "2026-07-08T00:01:00+00:00",
      last_test_status: "blocked",
      last_test_message: "Teams real mode failed closed: blocked by guard.",
    },
    {
      provider: "email",
      label: "Email",
      configured: false,
      missing_configuration: ["SMTP_PASSWORD"],
      tested: "failed",
      ready: false,
      last_test_at: "2026-07-08T00:02:00+00:00",
      last_test_status: "failed",
      last_test_message: "Email test failed.",
    },
    {
      provider: "webhook",
      label: "Webhook",
      configured: true,
      missing_configuration: [],
      tested: "never_tested",
      ready: false,
      last_test_at: null,
      last_test_status: null,
      last_test_message: null,
    },
  ],
};

beforeEach(() => {
  jest.clearAllMocks();
  getNotificationReadiness.mockResolvedValue(sampleReadiness);
  sendNotificationTest.mockResolvedValue({
    provider: "slack",
    label: "Slack",
    configured: true,
    tested: "passed",
    ready: true,
    outcome: "success",
    message: "Slack real-mode notification sent.",
  });
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "analyst",
    username: "analyst1",
  });
});

afterEach(() => {
  jest.useRealTimers();
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
  expect(screen.getByRole("note")).toHaveTextContent(/operational view/i);
  expect(screen.getByText("Execution Safety Model")).toBeInTheDocument();

  await waitFor(() => {
    expect(screen.getAllByText("Slack").length).toBeGreaterThan(0);
  });
});

test("renders error state on API failure and allows retry", async () => {
  getIntegrationStatus.mockRejectedValueOnce(new Error("Network down"));

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText(/error: network down/i)).toBeInTheDocument();
  expect(screen.queryByText(/operational summary/i)).not.toBeInTheDocument();
  expect(screen.getByRole("note")).toHaveTextContent(/does not test, send, or execute/i);

  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);
  await userEvent.click(screen.getByRole("button", { name: /retry/i }));

  expect(await screen.findByText(/operational summary/i)).toBeInTheDocument();
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
  expect(screen.getByText("Simulation")).toBeInTheDocument();
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

test("operational summary shows mode, simulation safety, delivery, and readiness", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText(/operational summary/i)).toBeInTheDocument();
  expect(screen.getAllByText("Simulation").length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByText("Yes").length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByText("Disabled").length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText("disabled", { exact: true })).toBeInTheDocument();
});

test("notification readiness renders providers, outcomes, and excludes firewall", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("Notification readiness")).toBeInTheDocument();
  expect(screen.getAllByText("Slack").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Teams").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Email").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Webhook").length).toBeGreaterThan(0);
  expect(screen.queryByText("Firewall", { selector: "span" })).not.toBeInTheDocument();
  expect(screen.getAllByText("Passed").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Never Tested (Guard Blocked)").length).toBeGreaterThan(0);
  expect(screen.getByText("SMTP_PASSWORD")).toBeInTheDocument();
  expect(screen.getByText("Teams real mode failed closed: blocked by guard.")).toBeInTheDocument();
});

test("notification readiness disables test button when provider is not configured", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "super_admin",
    username: "admin",
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("Notification readiness")).toBeInTheDocument();
  const buttons = screen.getAllByRole("button", { name: "Test" });
  expect(buttons[2]).toBeDisabled();
  expect(screen.getByText("Not Configured")).toBeInTheDocument();
});

test("notification test requires confirmation before sending", async () => {
  getIntegrationStatus.mockResolvedValue(sampleStatus);
  getNotificationReadiness.mockResolvedValue(sampleReadiness);
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "super_admin",
    username: "admin",
  });
  const confirmSpy = jest.spyOn(window, "confirm").mockReturnValueOnce(false);

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("Notification readiness")).toBeInTheDocument();
  await userEvent.click(screen.getAllByRole("button", { name: "Test" })[0]);

  expect(confirmSpy).toHaveBeenCalledWith(
    "Send one manual readiness test notification to Slack?"
  );
  expect(sendNotificationTest).not.toHaveBeenCalled();
});

test("notification test sends and refreshes after confirmation", async () => {
  getIntegrationStatus.mockResolvedValue(sampleStatus);
  getNotificationReadiness.mockResolvedValue(sampleReadiness);
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "super_admin",
    username: "admin",
  });
  jest.spyOn(window, "confirm").mockReturnValueOnce(true);

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("Notification readiness")).toBeInTheDocument();
  await userEvent.click(screen.getAllByRole("button", { name: "Test" })[0]);

  await waitFor(() => expect(sendNotificationTest).toHaveBeenCalledWith("slack"));
  expect(await screen.findByText("Slack real-mode notification sent.")).toBeInTheDocument();
  expect(getNotificationReadiness).toHaveBeenCalledTimes(2);
});

test("notification test message disappears after five seconds", async () => {
  jest.useFakeTimers();
  getIntegrationStatus.mockResolvedValue(sampleStatus);
  getNotificationReadiness.mockResolvedValue(sampleReadiness);
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "super_admin",
    username: "admin",
  });
  jest.spyOn(window, "confirm").mockReturnValueOnce(true);

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("Notification readiness")).toBeInTheDocument();
  await userEvent.click(screen.getAllByRole("button", { name: "Test" })[0]);

  expect(await screen.findByText("Slack real-mode notification sent.")).toBeInTheDocument();

  act(() => {
    jest.advanceTimersByTime(4999);
  });
  expect(screen.getByText("Slack real-mode notification sent.")).toBeInTheDocument();

  act(() => {
    jest.advanceTimersByTime(1);
  });
  await waitFor(() => {
    expect(screen.queryByText("Slack real-mode notification sent.")).not.toBeInTheDocument();
  });

  jest.useRealTimers();
});

test("each integration card shows operational fields, description, and supported actions", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  expect((await screen.findAllByText("Slack")).length).toBeGreaterThan(0);
  expect(screen.getByText(/Slack incoming webhook/i)).toBeInTheDocument();
  expect(screen.getByText("14 core playbooks")).toBeInTheDocument();
  expect(screen.getAllByText("Ready for real mode").length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByText("External delivery").length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByText("Last delivery").length).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByText("Last tested").length).toBeGreaterThanOrEqual(1);
  expect(screen.getByText("send_message")).toBeInTheDocument();
  expect(screen.getAllByText("Email").length).toBeGreaterThan(0);
  expect(screen.getByText("send_email")).toBeInTheDocument();
});

test("shows missing env variable names without secret values", async () => {
  getIntegrationStatus.mockResolvedValueOnce({
    mode: "simulation",
    configured_mode: "real",
    simulated: true,
    real_mode_enabled: false,
    real_mode_status: "disabled",
    adapters: [
      {
        name: "teams",
        mode: "simulation",
        simulated: true,
        real_client: false,
        real_mode_ready: false,
        real_mode_allowed: false,
        real_mode_status:
          "blocked: teams real mode requires guard(s): SOAR_REAL_TEAMS_ENABLED, TEAMS_WEBHOOK_URL",
        webhook_configured: false,
        supported_actions: ["send_message"],
        circuit_breaker: sampleCircuitClosed,
      },
    ],
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  expect((await screen.findAllByText("Teams")).length).toBeGreaterThan(0);
  expect(screen.getByText("Missing config")).toBeInTheDocument();
  expect(screen.getByText("SOAR_REAL_TEAMS_ENABLED")).toBeInTheDocument();
  expect(screen.getByText("TEAMS_WEBHOOK_URL")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent("https://contoso.webhook.office.com/webhookb2/SECRET");
  expect(document.body).not.toHaveTextContent("SECRET");
});

test("keeps circuit breaker fields inside collapsed Advanced details", async () => {
  getIntegrationStatus.mockResolvedValueOnce({
    mode: "simulation",
    configured_mode: "simulation",
    simulated: true,
    real_mode_enabled: false,
    real_mode_status: "disabled",
    adapters: [
      {
        name: "webhook",
        mode: "simulation",
        simulated: true,
        real_client: false,
        real_mode_ready: false,
        real_mode_allowed: false,
        webhook_url_configured: false,
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

  expect((await screen.findAllByText("Webhook")).length).toBeGreaterThan(0);
  const advanced = screen.getByText("Advanced");
  expect(advanced.closest("details")).not.toHaveAttribute("open");
  await userEvent.click(advanced);
  expect(screen.getByText(/reliability internals/i)).toBeInTheDocument();
  expect(screen.getByText(/circuit breaker state is simulation-only/i)).toBeInTheDocument();
  expect(screen.getByText("open")).toBeInTheDocument();
  expect(screen.getAllByText("Error").length).toBeGreaterThanOrEqual(1);
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
    configured_mode: "simulation",
    simulated: true,
    real_mode_enabled: false,
    real_mode_status: "disabled",
    adapters: [
      {
        name: "firewall",
        mode: "simulation",
        simulated: true,
        real_client: false,
        supported_actions: ["block_ip"],
      },
    ],
  });

  render(<IntegrationStatusPanel {...styleProps} />);

  expect(await screen.findByText("Firewall")).toBeInTheDocument();
  expect(screen.getByText(/does not change firewall rules/i)).toBeInTheDocument();
  expect(screen.queryByText(/circuit breaker state is simulation-only/i)).not.toBeInTheDocument();
});

test("simulation notice remains visible when data is loaded", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findAllByText("Slack");

  expect(screen.getByRole("note")).toHaveTextContent(/does not test, send, or execute/i);
  expect(screen.getByText("Per-adapter guards")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/global.*toggle/i);
  expect(document.body).not.toHaveTextContent(/fake/i);
});

test("does not render test-connection, run, or execute controls", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findAllByText("Slack");

  expect(screen.queryByRole("button", { name: /test connection/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /run adapter/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /execute/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /send notification/i })).not.toBeInTheDocument();
});

test("analyst does not see simulation circuit breaker control buttons", async () => {
  getIntegrationStatus.mockResolvedValueOnce(sampleStatus);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findAllByText("Slack");

  expect(screen.queryByRole("button", { name: /restore healthy state/i })).not.toBeInTheDocument();
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

  await screen.findAllByText("Slack");
  await userEvent.click(screen.getAllByText("Advanced")[0]);

  expect(
    screen.getAllByText(/advanced simulation controls \(super admin\)/i).length
  ).toBeGreaterThanOrEqual(1);
  expect(
    screen.getAllByRole("button", { name: /restore healthy state/i }).length
  ).toBeGreaterThanOrEqual(1);
  expect(screen.getAllByRole("button", { name: /simulate failure/i }).length).toBeGreaterThanOrEqual(1);
  expect(
    screen.getAllByRole("button", { name: /simulate recovery/i }).length
  ).toBeGreaterThanOrEqual(1);
  expect(screen.getByText(/super admins can adjust advanced simulation state/i)).toBeInTheDocument();
});

test("super admin must enter a reason before submitting a control", async () => {
  readStoredSessionIdentity.mockReturnValue({
    authenticated: true,
    role: "super_admin",
    username: "admin",
  });
  getIntegrationStatus.mockResolvedValueOnce(sampleStatusSingleAdapter);

  render(<IntegrationStatusPanel {...styleProps} />);

  await screen.findAllByText("Slack");
  await userEvent.click(screen.getByText("Advanced"));
  await userEvent.click(screen.getByRole("button", { name: /restore healthy state/i }));

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

  await screen.findAllByText("Slack");
  await userEvent.click(screen.getByText("Advanced"));
  await userEvent.type(
    screen.getByPlaceholderText(/describe why you are changing simulation breaker state/i),
    "post-incident review"
  );
  await userEvent.click(screen.getByRole("button", { name: /restore healthy state/i }));

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

  expect(await screen.findByText("Firewall")).toBeInTheDocument();
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
