import React from "react";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";

import AiGatewayConfigPanel from "./AiGatewayConfigPanel";
import * as service from "../services/aiGatewayConfigService";

jest.mock("../services/aiGatewayConfigService");

const appliedPolicy = {
  status: "applied",
  error_code: null,
  configuration: {
    gateway_mode: "automatic_fallback",
    anthropic_routing_enabled: true,
    preferred_anthropic_model: "claude-approved-model",
    daily_paid_budget_usd: 12.5,
  },
  effective: {
    gateway_mode: "automatic_fallback",
    anthropic_routing_enabled: true,
    preferred_anthropic_model: "claude-approved-model",
    daily_paid_budget_usd: 12.5,
  },
  updated_by: "testadmin",
  updated_at: "2026-08-04T14:30:00Z",
};

const props = {
  userRole: "super_admin",
  displaySettings: { timezoneMode: "utc", timestampFormat: "24h" },
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
  cardSubtitleStyle: {},
};

beforeEach(() => {
  service.loadAiGatewayConfig.mockResolvedValue(appliedPolicy);
  service.updateAiGatewayConfig.mockImplementation(async (configuration) => ({
    ...appliedPolicy,
    configuration,
    effective: configuration,
  }));
});

test("renders the complete non-secret effective policy in the dark admin surface", async () => {
  render(<AiGatewayConfigPanel {...props} />);

  expect(await screen.findByRole("heading", { name: "AI Gateway Policy" })).toBeInTheDocument();
  expect(await screen.findByText("Runtime policy applied")).toBeInTheDocument();
  expect(screen.getAllByText("Automatic fallback").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Enabled").length).toBeGreaterThan(0);
  expect(screen.getAllByText("claude-approved-model").length).toBeGreaterThan(0);
  expect(screen.getByText("$12.50")).toBeInTheDocument();
  expect(screen.getByText("testadmin")).toBeInTheDocument();
  expect(screen.getByText(/Aug 04, 2026, 14:30 UTC/)).toBeInTheDocument();
  expect(screen.getByText(/credentials and endpoints are intentionally managed outside/i)).toBeInTheDocument();
  expect(screen.queryByLabelText(/api key/i)).not.toBeInTheDocument();
});

test("saves a validated policy and announces next-request effect", async () => {
  render(<AiGatewayConfigPanel {...props} />);

  fireEvent.change(await screen.findByLabelText("Gateway mode"), {
    target: { value: "local_only" },
  });
  fireEvent.click(screen.getByLabelText("Anthropic routing enabled"));
  fireEvent.change(screen.getByLabelText("Preferred Anthropic model"), {
    target: { value: "claude-next-model" },
  });
  fireEvent.change(screen.getByLabelText("Daily paid budget (USD)"), {
    target: { value: "8" },
  });
  fireEvent.click(screen.getByRole("button", { name: "Save gateway policy" }));

  await waitFor(() => expect(service.updateAiGatewayConfig).toHaveBeenCalledWith({
    gateway_mode: "local_only",
    anthropic_routing_enabled: false,
    preferred_anthropic_model: "claude-next-model",
    daily_paid_budget_usd: 8,
  }));
  expect(await screen.findByRole("status")).toHaveTextContent(/next request uses this configuration/i);
});

test("blocks locally invalid routing policy and exposes accessible validation", async () => {
  render(<AiGatewayConfigPanel {...props} />);

  await screen.findByLabelText("Daily paid budget (USD)");
  fireEvent.change(screen.getByLabelText("Daily paid budget (USD)"), {
    target: { value: "0" },
  });

  expect(screen.getByText(/must be greater than zero when routing is enabled/i)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Save gateway policy" })).toBeDisabled();
  expect(service.updateAiGatewayConfig).not.toHaveBeenCalled();
});

test("shows backend validation errors without replacing the current policy", async () => {
  service.updateAiGatewayConfig.mockRejectedValue(new Error("gateway_mode is invalid."));
  render(<AiGatewayConfigPanel {...props} />);

  fireEvent.click(await screen.findByRole("button", { name: "Save gateway policy" }));

  expect(await screen.findByRole("alert")).toHaveTextContent("gateway_mode is invalid.");
  expect(screen.getByLabelText("Gateway mode")).toHaveValue("automatic_fallback");
});

test.each(["invalid", "unavailable"])(
  "shows %s fail-closed effective state and disables mutation",
  async (status) => {
    service.loadAiGatewayConfig.mockResolvedValue({
      ...appliedPolicy,
      status,
      error_code: `runtime_config_${status}`,
      effective: {
        ...appliedPolicy.effective,
        gateway_mode: "local_only",
        anthropic_routing_enabled: false,
      },
    });

    render(<AiGatewayConfigPanel {...props} />);

    expect(await screen.findByText("Fail closed")).toBeInTheDocument();
    expect(screen.getByRole("status")).toHaveTextContent(/paid routing is disabled/i);
    expect(screen.getByRole("button", { name: "Save gateway policy" })).toBeDisabled();
  }
);

test("announces configuration-store load failures", async () => {
  service.loadAiGatewayConfig.mockRejectedValue(new Error("Configuration store unavailable"));
  render(<AiGatewayConfigPanel {...props} />);

  expect(await screen.findByRole("alert")).toHaveTextContent("Configuration store unavailable");
});

test("does not load or expose controls for a non-super-admin role", () => {
  render(<AiGatewayConfigPanel {...props} userRole="analyst" />);

  expect(screen.getByRole("alert")).toHaveTextContent("Super-admin access is required.");
  expect(service.loadAiGatewayConfig).not.toHaveBeenCalled();
  expect(screen.queryByRole("button", { name: "Save gateway policy" })).not.toBeInTheDocument();
});
