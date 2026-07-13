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

describe("Temporary Playground Rule mode", () => {
  const temporaryStages = {
    raw_input: { status: "succeeded", input_count: 2, input_format: "json_lines" },
    parser: { status: "succeeded", results: [] },
    normalized_event: { status: "succeeded", events: [] },
    detection_applicability: {
      status: "succeeded",
      source: "bank_app",
      source_type: "custom",
      event_type_filter: "failed_login",
      allowed_condition_fields: ["source_ip", "username", "event_type", "event_outcome", "severity"],
      allowed_group_by_fields: ["source_ip", "username"],
    },
    detection_evaluation: { status: "succeeded", candidate_event_count: 2, matching_event_count: 2 },
    threshold_window_evaluation: {
      status: "succeeded",
      matched: true,
      matched_group: "198.51.100.201",
      observed_value_label: "count",
      observed_value: 2,
      configured_threshold: 2,
      evaluated_window_minutes: 15,
      group_by_field: "source_ip",
      grouped_results: [{ group_value: "198.51.100.201", match_count: 2, window_basis: "request_scope_without_timestamps" }],
      evidence_available: true,
      pasted_event_only: true,
      nothing_persisted: true,
      nothing_executed: true,
    },
    alert_preview: {
      status: "succeeded",
      alert: { alert_type: "temporary_playground_rule", severity: "high", message: "msg", reputation_source: "simulated" },
      temporary_rule_semantics: true,
      persistence: "request_scoped_rollback_only",
    },
    mitre_mapping: { status: "succeeded", mitre_technique_id: "T1110", mitre_technique_name: "Brute Force", mitre_tactic: "Credential Access", reason: "temporary_rule_selected_mitre_technique" },
    soar_preview: { status: "succeeded", matched_playbooks: [], no_playbook_match: true, selected_response_action: "monitor" },
  };

  const fillMinimalBuilderRule = async () => {
    await userEvent.selectOptions(screen.getByLabelText(/playground source/i), "bank_app");
    await userEvent.selectOptions(screen.getByLabelText(/playground input format/i), "json_lines");
    pasteInto(
      screen.getByLabelText(/playground event input/i),
      '{"event_type": "failed_login", "source_ip": "198.51.100.201", "username": "alice"}'
    );
    await userEvent.selectOptions(screen.getByLabelText(/condition field/i), "username");
    await userEvent.selectOptions(screen.getByLabelText(/condition operator/i), "equals");
    await userEvent.type(screen.getByLabelText(/condition value/i), "alice");
    await userEvent.selectOptions(screen.getByLabelText(/group by field/i), "source_ip");
  };

  test("presents both modes to any user who can reach this workspace, defaulting to Existing Production Rule", async () => {
    render(<DetectionSimulatorPanel />);
    await screen.findByRole("option", { name: "Failed Login Threshold" });

    const modeGroup = screen.getByRole("radiogroup", { name: /detection simulator mode/i });
    const existingRadio = within(modeGroup).getByRole("radio", { name: /existing production rule/i });
    const playgroundRadio = within(modeGroup).getByRole("radio", { name: /temporary playground rule/i });

    // Both modes are offered by the same workspace with no additional
    // role-specific gating inside the panel -- the backend applies the same
    // analyst-or-super-admin boundary to both simulation_mode values via one
    // endpoint, so no separate frontend RBAC check is introduced here.
    expect(existingRadio).toBeInTheDocument();
    expect(playgroundRadio).toBeInTheDocument();
    expect(existingRadio).toBeChecked();
    expect(playgroundRadio).not.toBeChecked();
  });

  test("switching to Temporary Playground Rule mode hides the production-rule form and shows the guided builder", async () => {
    render(<DetectionSimulatorPanel />);
    await screen.findByRole("option", { name: "Failed Login Threshold" });

    await userEvent.click(screen.getByRole("radio", { name: /temporary playground rule/i }));

    expect(screen.queryByLabelText(/^detection rule$/i)).not.toBeInTheDocument();
    expect(screen.getByLabelText(/playground source/i)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /reset rule/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /save rule/i })).not.toBeInTheDocument();

    await userEvent.click(screen.getByRole("radio", { name: /existing production rule/i }));
    expect(screen.getByLabelText(/^detection rule$/i)).toBeInTheDocument();
    expect(screen.queryByLabelText(/playground source/i)).not.toBeInTheDocument();
  });

  test("submits the builder-assembled payload and renders backend evidence only, without recomputing the match client-side", async () => {
    runDetectionSimulation.mockResolvedValue({
      simulated: true,
      simulation_mode: "temporary_playground_rule",
      source: "bank_app",
      temporary_rule: { source: "bank_app" },
      stages: temporaryStages,
    });
    render(<DetectionSimulatorPanel />);
    await screen.findByRole("option", { name: "Failed Login Threshold" });
    await userEvent.click(screen.getByRole("radio", { name: /temporary playground rule/i }));

    await fillMinimalBuilderRule();
    await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

    await waitFor(() =>
      expect(runDetectionSimulation).toHaveBeenCalledWith(
        expect.objectContaining({
          simulation_mode: "temporary_playground_rule",
          temporary_rule: expect.objectContaining({
            source: "bank_app",
            condition: { field: "username", operator: "equals", value: "alice" },
            aggregation: { type: "count", group_by_field: "source_ip" },
          }),
        })
      )
    );

    const results = await screen.findByTestId("detection-simulator-results");
    // Rendered evidence is read verbatim from the mocked backend response --
    // the grouped count (2) and threshold (2) below come only from
    // temporaryStages, never from re-evaluating the pasted event in React.
    expect(within(results).getByText(/Grouped evidence: source_ip=198.51.100.201 \(2\)/)).toBeInTheDocument();
    expect(within(results).getByText(/Observed count: 2 \(required: 2\)/)).toBeInTheDocument();
    expect(within(results).getByText(/Nothing was persisted or executed by this evaluation\./)).toBeInTheDocument();
  });

  test("surfaces a backend validation error for the playground request without rendering results", async () => {
    runDetectionSimulation.mockRejectedValue(new Error("temporary_rule.condition.field is not supported for source 'bank_app'"));
    render(<DetectionSimulatorPanel />);
    await screen.findByRole("option", { name: "Failed Login Threshold" });
    await userEvent.click(screen.getByRole("radio", { name: /temporary playground rule/i }));

    await fillMinimalBuilderRule();
    await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

    expect(await screen.findByText(/is not supported for source/)).toBeInTheDocument();
    expect(screen.queryByTestId("detection-simulator-results")).not.toBeInTheDocument();
  });

  test("Reset Rule discards the current draft and clears any displayed result, with no persistence implied", async () => {
    runDetectionSimulation.mockResolvedValue({
      simulated: true,
      simulation_mode: "temporary_playground_rule",
      source: "bank_app",
      stages: temporaryStages,
    });
    render(<DetectionSimulatorPanel />);
    await screen.findByRole("option", { name: "Failed Login Threshold" });
    await userEvent.click(screen.getByRole("radio", { name: /temporary playground rule/i }));

    await fillMinimalBuilderRule();
    await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));
    await screen.findByTestId("detection-simulator-results");

    await userEvent.click(screen.getByRole("button", { name: /reset rule/i }));

    expect(screen.queryByTestId("detection-simulator-results")).not.toBeInTheDocument();
    expect(screen.getByLabelText(/playground source/i).value).toBe("");
    expect(screen.getByText(/Build a temporary rule and run a simulation/i)).toBeInTheDocument();
  });

  test("mode selector and builder controls are keyboard-focusable in a logical order with no new console errors", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    render(<DetectionSimulatorPanel />);
    await screen.findByRole("option", { name: "Failed Login Threshold" });

    const existingRadio = screen.getByRole("radio", { name: /existing production rule/i });
    const playgroundRadio = screen.getByRole("radio", { name: /temporary playground rule/i });
    expect(existingRadio.tabIndex).not.toBe(-1);
    expect(playgroundRadio.tabIndex).not.toBe(-1);

    await userEvent.click(playgroundRadio);
    expect(playgroundRadio).toBeChecked();

    // Selecting a source first enables the dependent format/field selects,
    // so tabbing through them exercises the real (non-disabled) focus order.
    await userEvent.selectOptions(screen.getByLabelText(/playground source/i), "bank_app");
    screen.getByLabelText(/playground source/i).focus();
    await userEvent.tab();
    expect(screen.getByLabelText(/playground input format/i)).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByLabelText(/playground event type filter/i)).toHaveFocus();

    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});
