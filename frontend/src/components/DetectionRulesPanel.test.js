import React from "react";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";

import DetectionRulesPanel from "./DetectionRulesPanel";
import {
  loadDetectionRules,
  loadPfsenseDetectionHealth,
  updateDetectionRule,
} from "../services/detectionRulesService";

jest.mock("../services/detectionRulesService", () => ({
  loadDetectionRules: jest.fn(),
  loadPfsenseDetectionHealth: jest.fn(),
  updateDetectionRule: jest.fn(),
}));

const source = (sourceName, sourceType) => ({ source: sourceName, source_type: sourceType });
const baseRule = {
  description: "Rule description",
  parameters: { threshold: 3, window_minutes: 15 },
  active: true,
  has_override: false,
  override_status: "default",
  updated_by: null,
  updated_at: null,
};

const rules = [
  {
    ...baseRule,
    rule_id: "failed_login_threshold",
    display_name: "Failed Login Threshold",
    source_applicability_category: "canonical_multi_source_authentication",
    applicable_sources: [
      source("bank_app", "custom"),
      source("nginx", "web_log"),
      source("azure_insights", "cloud_api"),
      source("opentelemetry", "telemetry"),
    ],
  },
  {
    ...baseRule,
    rule_id: "http_error_threshold",
    display_name: "HTTP Error Threshold",
    active: false,
    has_override: true,
    override_status: "applied",
    updated_by: "testadmin",
    updated_at: "2026-07-11T12:00:00Z",
    applicable_sources: [source("nginx", "web_log")],
  },
  {
    ...baseRule,
    rule_id: "pfsense_firewall_port_scan",
    display_name: "pfSense Firewall Port Scan",
    applicable_sources: [source("pfsense", "firewall")],
  },
  {
    ...baseRule,
    rule_id: "honeypot_env_probe_threshold",
    display_name: "Honeypot Env Probe Threshold",
    applicable_sources: [source("honeypot", "honeypot")],
  },
];

const renderPanel = () => render(
  <DetectionRulesPanel
    cardStyle={{}}
    cardHeaderStyle={{}}
    cardTitleStyle={{}}
    cardSubtitleStyle={{}}
  />
);

const clickAndFlush = async (element) => {
  await act(async () => {
    fireEvent.click(element);
    await Promise.resolve();
    await Promise.resolve();
  });
};

beforeEach(() => {
  jest.clearAllMocks();
  loadDetectionRules.mockResolvedValue(rules);
  loadPfsenseDetectionHealth.mockResolvedValue([
    {
      rule_id: "pfsense_firewall_port_scan",
      rule_name: "pfSense Firewall Port Scan",
      fired_count_24h: 21,
      highest_severity_24h: "critical",
      last_fired_at: "2026-07-13T14:00:00Z",
      health_badge: "Noisy",
    },
    {
      rule_id: "pfsense_firewall_noisy_source",
      rule_name: "pfSense Firewall Noisy Source",
      fired_count_24h: 0,
      highest_severity_24h: null,
      last_fired_at: null,
      health_badge: "Normal",
    },
  ]);
  updateDetectionRule.mockResolvedValue({});
  window.confirm = jest.fn(() => true);
});

test("renders active state, source coverage, global parameters, and override status", async () => {
  renderPanel();

  expect(await screen.findByText("Failed Login Threshold")).toBeInTheDocument();
  expect(await screen.findByText("pfSense Detection Health")).toBeInTheDocument();
  expect(screen.getByText("24h UTC window")).toBeInTheDocument();
  expect(screen.getByText("21 fires")).toBeInTheDocument();
  expect(screen.getByText("Noisy")).toBeInTheDocument();
  expect(screen.getAllByText("Active").length).toBeGreaterThan(0);
  expect(screen.getByText("Inactive")).toBeInTheDocument();
  for (const label of [
    "Bank App",
    "NGINX",
    "Azure Application Insights",
    "OpenTelemetry",
    "pfSense",
    "Honeypot",
  ]) {
    expect(screen.getAllByText(label).length).toBeGreaterThan(0);
  }
  expect(screen.getAllByText("One global configuration applies to all listed sources.")).toHaveLength(4);
  expect(screen.getAllByText("threshold").length).toBeGreaterThan(0);
  expect(screen.getAllByText("Default").length).toBeGreaterThan(0);
  expect(screen.getByText("Overridden")).toBeInTheDocument();
  expect(screen.getByLabelText("Bank App: bank_app/custom")).toHaveAttribute("title", "bank_app/custom");
  expect(screen.queryByRole("button", { name: /edit.*source/i })).not.toBeInTheDocument();
  expect(loadPfsenseDetectionHealth).toHaveBeenCalledWith({ operationalScope: "since_tuning" });
});

test("confirms and sends an active-only disable update", async () => {
  renderPanel();
  const button = await screen.findByRole("button", { name: "Disable Failed Login Threshold" });
  await clickAndFlush(button);

  expect(window.confirm).toHaveBeenCalledWith(
    "Disable Failed Login Threshold? Detection will stop for this rule."
  );
  expect(updateDetectionRule).toHaveBeenCalledWith("failed_login_threshold", undefined, false);
  await waitFor(() => expect(screen.getByText("Disabled failed_login_threshold")).toBeInTheDocument());
});

test("re-enables without sending or resetting global parameters", async () => {
  renderPanel();
  const button = await screen.findByRole("button", { name: "Enable HTTP Error Threshold" });
  await clickAndFlush(button);

  expect(window.confirm).not.toHaveBeenCalled();
  expect(updateDetectionRule).toHaveBeenCalledWith("http_error_threshold", undefined, true);
});

test("cancelled disable does not mutate state or call the API", async () => {
  window.confirm.mockReturnValue(false);
  renderPanel();
  await clickAndFlush(await screen.findByRole("button", { name: "Disable Failed Login Threshold" }));
  expect(updateDetectionRule).not.toHaveBeenCalled();
  expect(screen.getByRole("button", { name: "Disable Failed Login Threshold" })).toBeInTheDocument();
});

test("failed active update rolls back optimistic state and displays an error", async () => {
  let rejectUpdate;
  updateDetectionRule.mockImplementation(() => new Promise((resolve, reject) => {
    rejectUpdate = reject;
  }));
  renderPanel();
  await clickAndFlush(await screen.findByRole("button", { name: "Disable Failed Login Threshold" }));

  expect(screen.getByText("Updating...")).toBeInTheDocument();
  expect(screen.getAllByText("Inactive").length).toBeGreaterThan(1);
  await act(async () => rejectUpdate(new Error("Unable to disable rule")));

  expect(await screen.findByRole("alert")).toHaveTextContent("Unable to disable rule");
  expect(screen.getByRole("button", { name: "Disable Failed Login Threshold" })).toBeInTheDocument();
});

test("existing threshold and window editor remains compatible", async () => {
  renderPanel();
  const nameCell = (await screen.findByText("Failed Login Threshold")).closest("tr");
  await clickAndFlush(within(nameCell).getByRole("button", { name: "Edit" }));
  const threshold = within(nameCell).getByLabelText("threshold");
  fireEvent.change(threshold, { target: { value: "6" } });
  await clickAndFlush(within(nameCell).getByRole("button", { name: "Save" }));

  expect(updateDetectionRule).toHaveBeenCalledWith(
    "failed_login_threshold",
    { threshold: 6, window_minutes: 15 }
  );
});

test("detection health rows navigate to the existing rule workspace row", async () => {
  const scrollIntoView = jest.fn();
  window.HTMLElement.prototype.scrollIntoView = scrollIntoView;

  renderPanel();
  await screen.findByText("21 fires");
  const healthButton = screen.getAllByRole("button").find((button) => (
    button.textContent.includes("pfSense Firewall Port Scan") &&
    button.textContent.includes("21 fires")
  ));
  fireEvent.click(healthButton);

  expect(scrollIntoView).toHaveBeenCalled();
  await waitFor(() => {
    expect(document.activeElement).toHaveAttribute("id", "detection-rule-row-pfsense_firewall_port_scan");
  });
});
