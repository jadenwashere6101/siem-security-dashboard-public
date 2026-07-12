import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DetectionSimulatorPanel from "./DetectionSimulatorPanel";
import { loadSimulatorRules, runDetectionSimulation } from "../services/detectionSimulatorService";

jest.mock("../services/detectionSimulatorService", () => ({
  loadSimulatorRules: jest.fn(),
  runDetectionSimulation: jest.fn(),
}));

// Textarea input is simulated via fireEvent.change (a paste), not
// userEvent.type: user-event v13 interprets "{" and "[" in typed strings as
// special key codes, which corrupts literal JSON/log text.
const pasteInto = (element, value) => fireEvent.change(element, { target: { value } });

const rules = [
  { rule_id: "failed_login_threshold", display_name: "Failed Login Threshold", description: "", active: true, applicable_sources: [] },
  { rule_id: "pfsense_firewall_repeated_deny", display_name: "pfSense Firewall Repeated Deny", description: "", active: true, applicable_sources: [] },
];

const succeededStages = {
  raw_input: { status: "succeeded" },
  parser: { status: "succeeded" },
  normalized_event: { status: "succeeded" },
  detection_applicability: { status: "succeeded" },
  detection_evaluation: { status: "succeeded" },
  threshold_window_evaluation: { status: "succeeded", rule_parameters: { threshold: 3 }, matched: true },
  alert_preview: { status: "succeeded", alert: { alert_type: "failed_login_threshold", severity: "high", message: "msg", reputation_source: "simulated" } },
  mitre_mapping: { status: "succeeded", mitre_technique_id: "T1110", mitre_technique_name: "Brute Force", mitre_tactic: "Credential Access" },
  soar_preview: { status: "succeeded", matched_playbooks: [], no_playbook_match: true, selected_response_action: "monitor" },
};

beforeEach(() => {
  jest.clearAllMocks();
  loadSimulatorRules.mockResolvedValue(rules);
});

test("renders the workspace heading and safety statement", async () => {
  render(<DetectionSimulatorPanel />);
  expect(screen.getByRole("heading", { name: /detection simulator/i })).toBeInTheDocument();
  expect(screen.getByText(/always rolled back/i)).toBeInTheDocument();
  await waitFor(() => expect(loadSimulatorRules).toHaveBeenCalled());
});

test("populates the rule selector from the backend's existing-rules list only", async () => {
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });
  expect(screen.getByRole("option", { name: "pfSense Firewall Repeated Deny" })).toBeInTheDocument();
  // No custom-rule input of any kind is offered.
  expect(screen.queryByLabelText(/python/i)).not.toBeInTheDocument();
  expect(screen.queryByLabelText(/sql/i)).not.toBeInTheDocument();
});

test("shows a rules-load error without blocking the rest of the form", async () => {
  loadSimulatorRules.mockRejectedValue(new Error("forbidden"));
  render(<DetectionSimulatorPanel />);
  expect(await screen.findByText(/Unable to load detection rules: forbidden/)).toBeInTheDocument();
  expect(screen.getByLabelText(/event source/i)).toBeInTheDocument();
});

test("input format options are constrained by the selected source", async () => {
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "nginx");
  const formatSelect = screen.getByLabelText(/input format/i);
  expect(within(formatSelect).getAllByRole("option").map((o) => o.value)).toEqual(["", "raw"]);

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "honeypot");
  expect(within(formatSelect).getAllByRole("option").map((o) => o.value)).toEqual(["", "json"]);
});

test("submits the exact selected source, rule, and raw input to the backend", async () => {
  runDetectionSimulation.mockResolvedValue({ simulated: true, source: "nginx", rule_id: "failed_login_threshold", stages: succeededStages });
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "nginx");
  await userEvent.selectOptions(screen.getByLabelText(/detection rule/i), "failed_login_threshold");
  pasteInto(
    screen.getByLabelText(/raw log input/i),
    '203.0.113.9 - - [10/Oct/2026:13:55:36 -0700] "GET /admin HTTP/1.1" 500 123'
  );
  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  await waitFor(() =>
    expect(runDetectionSimulation).toHaveBeenCalledWith({
      source: "nginx",
      rule_id: "failed_login_threshold",
      input_format: "raw",
      raw_lines: ['203.0.113.9 - - [10/Oct/2026:13:55:36 -0700] "GET /admin HTTP/1.1" 500 123'],
    })
  );
});

test("parses JSON input into an array before submitting", async () => {
  runDetectionSimulation.mockResolvedValue({ simulated: true, source: "bank_app", rule_id: "failed_login_threshold", stages: succeededStages });
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "bank_app");
  await userEvent.selectOptions(screen.getByLabelText(/detection rule/i), "failed_login_threshold");
  pasteInto(
    screen.getByLabelText(/json event input/i),
    '{"event_type": "failed_login", "severity": "medium", "source_ip": "203.0.113.5", "message": "m", "app_name": "a", "environment": "test"}'
  );
  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  await waitFor(() => expect(runDetectionSimulation).toHaveBeenCalled());
  const payload = runDetectionSimulation.mock.calls[0][0];
  expect(payload.input_format).toBe("json");
  expect(payload.json_events).toEqual([
    { event_type: "failed_login", severity: "medium", source_ip: "203.0.113.5", message: "m", app_name: "a", environment: "test" },
  ]);
});

test("rejects invalid JSON input before calling the backend", async () => {
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "bank_app");
  await userEvent.selectOptions(screen.getByLabelText(/detection rule/i), "failed_login_threshold");
  pasteInto(screen.getByLabelText(/json event input/i), "{not valid json");
  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  expect(await screen.findByRole("alert")).toHaveTextContent(/not valid JSON/i);
  expect(runDetectionSimulation).not.toHaveBeenCalled();
});

test("shows a loading state while the simulation request is pending", async () => {
  let resolveRequest;
  runDetectionSimulation.mockReturnValue(new Promise((resolve) => { resolveRequest = resolve; }));
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "bank_app");
  await userEvent.selectOptions(screen.getByLabelText(/detection rule/i), "failed_login_threshold");
  pasteInto(screen.getByLabelText(/json event input/i), '{"event_type": "failed_login"}');
  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  expect(await screen.findByRole("status")).toHaveTextContent(/running simulation/i);
  resolveRequest({ simulated: true, source: "bank_app", rule_id: "failed_login_threshold", stages: succeededStages });
  await waitFor(() => expect(screen.queryByText(/running simulation…/i)).not.toBeInTheDocument());
});

test("renders pipeline and explanation results after a successful run without recomputing anything client-side", async () => {
  runDetectionSimulation.mockResolvedValue({ simulated: true, source: "bank_app", rule_id: "failed_login_threshold", stages: succeededStages });
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "bank_app");
  await userEvent.selectOptions(screen.getByLabelText(/detection rule/i), "failed_login_threshold");
  pasteInto(screen.getByLabelText(/json event input/i), '{"event_type": "failed_login"}');
  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  const results = await screen.findByTestId("detection-simulator-results");
  expect(within(results).getByText(/T1110 — Brute Force/)).toBeInTheDocument();
  expect(within(results).getAllByRole("listitem")).toHaveLength(9);
});

test("surfaces a backend API failure without rendering results", async () => {
  runDetectionSimulation.mockRejectedValue(new Error("Unknown rule_id"));
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "bank_app");
  await userEvent.selectOptions(screen.getByLabelText(/detection rule/i), "failed_login_threshold");
  pasteInto(screen.getByLabelText(/json event input/i), '{"event_type": "failed_login"}');
  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  expect(await screen.findByText("Unknown rule_id")).toBeInTheDocument();
  expect(screen.queryByTestId("detection-simulator-results")).not.toBeInTheDocument();
});

test("surfaces a malformed-response failure from the service layer", async () => {
  runDetectionSimulation.mockRejectedValue(new Error("Invalid simulation response"));
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "bank_app");
  await userEvent.selectOptions(screen.getByLabelText(/detection rule/i), "failed_login_threshold");
  pasteInto(screen.getByLabelText(/json event input/i), '{"event_type": "failed_login"}');
  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  expect(await screen.findByText("Invalid simulation response")).toBeInTheDocument();
});

test("the Run Simulation button is disabled until source, rule, and input are all provided", async () => {
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });

  expect(screen.getByRole("button", { name: /run simulation/i })).toBeDisabled();

  await userEvent.selectOptions(screen.getByLabelText(/event source/i), "bank_app");
  expect(screen.getByRole("button", { name: /run simulation/i })).toBeDisabled();

  await userEvent.selectOptions(screen.getByLabelText(/detection rule/i), "failed_login_threshold");
  expect(screen.getByRole("button", { name: /run simulation/i })).toBeDisabled();

  pasteInto(screen.getByLabelText(/json event input/i), '{"event_type": "failed_login"}');
  expect(screen.getByRole("button", { name: /run simulation/i })).toBeEnabled();
});

test("shows an empty state before any simulation has been run", async () => {
  render(<DetectionSimulatorPanel />);
  await screen.findByRole("option", { name: "Failed Login Threshold" });
  expect(screen.getByText(/Select a source, rule, and input/i)).toBeInTheDocument();
});
