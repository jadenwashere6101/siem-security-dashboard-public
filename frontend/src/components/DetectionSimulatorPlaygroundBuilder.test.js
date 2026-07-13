import React from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DetectionSimulatorPlaygroundBuilder from "./DetectionSimulatorPlaygroundBuilder";

// Mirrors DetectionSimulatorPanel.test.js's approach: textarea input is
// simulated via fireEvent.change (a paste), not userEvent.type, because
// user-event v13 interprets "{" and "[" in typed strings as special keys.
const pasteInto = (element, value) => fireEvent.change(element, { target: { value } });

const renderBuilder = (overrides = {}) => {
  const onRun = jest.fn();
  const onReset = jest.fn();
  const onValidationError = jest.fn();
  render(
    <DetectionSimulatorPlaygroundBuilder
      running={false}
      onRun={onRun}
      onReset={onReset}
      onValidationError={onValidationError}
      {...overrides}
    />
  );
  return { onRun, onReset, onValidationError };
};

const fillMinimalValidRule = async () => {
  await userEvent.selectOptions(screen.getByLabelText(/playground source/i), "bank_app");
  await userEvent.selectOptions(screen.getByLabelText(/playground input format/i), "json_lines");
  pasteInto(screen.getByLabelText(/playground event input/i), '{"event_type": "failed_login", "source_ip": "198.51.100.1", "username": "alice"}');
  await userEvent.selectOptions(screen.getByLabelText(/condition field/i), "username");
  await userEvent.selectOptions(screen.getByLabelText(/condition operator/i), "equals");
  await userEvent.type(screen.getByLabelText(/condition value/i), "alice");
  await userEvent.selectOptions(screen.getByLabelText(/group by field/i), "source_ip");
};

test("shows the non-persistence disclosure and offers no save or promotion controls", () => {
  renderBuilder();
  expect(screen.getByRole("note")).toHaveTextContent(/rollback-only transaction/i);
  expect(screen.getByRole("note")).toHaveTextContent(/nothing is saved, promoted, or persisted/i);
  expect(screen.queryByRole("button", { name: /save rule/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /promote/i })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /reset rule/i })).toBeInTheDocument();
});

test("constrains input format and condition-field options to the selected source", async () => {
  renderBuilder();

  await userEvent.selectOptions(screen.getByLabelText(/playground source/i), "nginx");
  const formatSelect = screen.getByLabelText(/playground input format/i);
  expect(Array.from(formatSelect.options).map((o) => o.value).filter(Boolean)).toEqual(["raw_text"]);

  const fieldSelect = screen.getByLabelText(/condition field/i);
  expect(Array.from(fieldSelect.options).map((o) => o.value).filter(Boolean)).toEqual([
    "source_ip",
    "event_type",
    "http_status",
    "severity",
  ]);

  await userEvent.selectOptions(screen.getByLabelText(/playground source/i), "bank_app");
  expect(Array.from(formatSelect.options).map((o) => o.value).filter(Boolean)).toEqual(["json_lines", "json_array"]);
});

test("offers only numeric operators for a numeric condition field", async () => {
  renderBuilder();
  await userEvent.selectOptions(screen.getByLabelText(/playground source/i), "nginx");
  await userEvent.selectOptions(screen.getByLabelText(/condition field/i), "http_status");

  const operatorSelect = screen.getByLabelText(/condition operator/i);
  const options = Array.from(operatorSelect.options).map((o) => o.value).filter(Boolean);
  expect(options).toContain("greater_than");
  expect(options).not.toContain("contains");
  expect(options).not.toContain("starts_with");
});

test("submits the exact assembled temporary_rule payload without evaluating any event", async () => {
  const { onRun } = renderBuilder();
  await fillMinimalValidRule();
  await userEvent.selectOptions(screen.getByLabelText(/playground severity/i), "high");
  await userEvent.type(screen.getByLabelText(/mitre technique id/i), "T1110");

  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  expect(onRun).toHaveBeenCalledWith({
    simulation_mode: "temporary_playground_rule",
    temporary_rule: {
      source: "bank_app",
      source_type: "custom",
      input_format: "json_lines",
      event_type: null,
      condition: { field: "username", operator: "equals", value: "alice" },
      aggregation: { type: "count", group_by_field: "source_ip" },
      threshold: 3,
      window_minutes: 15,
      severity: "high",
      mitre_technique_id: "T1110",
    },
    input_text: '{"event_type": "failed_login", "source_ip": "198.51.100.1", "username": "alice"}',
  });
});

test("converts a numeric in_list condition into an array of numbers", async () => {
  const { onRun } = renderBuilder();
  await userEvent.selectOptions(screen.getByLabelText(/playground source/i), "pfsense");
  await userEvent.selectOptions(screen.getByLabelText(/playground input format/i), "raw_text");
  pasteInto(screen.getByLabelText(/playground event input/i), "raw log line placeholder");
  await userEvent.selectOptions(screen.getByLabelText(/condition field/i), "destination_port");
  await userEvent.selectOptions(screen.getByLabelText(/condition operator/i), "in_list");
  await userEvent.type(screen.getByLabelText(/condition value/i), "22, 3389");
  await userEvent.selectOptions(screen.getByLabelText(/group by field/i), "source_ip");

  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  expect(onRun).toHaveBeenCalled();
  const payload = onRun.mock.calls[0][0];
  expect(payload.temporary_rule.condition).toEqual({ field: "destination_port", operator: "in_list", value: [22, 3389] });
});

test("loads verified sample events into the textarea for the selected source and format", async () => {
  renderBuilder();
  await userEvent.selectOptions(screen.getByLabelText(/playground source/i), "honeypot");
  await userEvent.selectOptions(screen.getByLabelText(/playground input format/i), "json_lines");

  await userEvent.click(screen.getByRole("button", { name: /load sample events/i }));

  const textarea = screen.getByLabelText(/playground event input/i);
  expect(textarea.value).toMatch(/env_probe/);
  expect(textarea.value.trim().length).toBeGreaterThan(0);
});

test("keeps Run Simulation disabled until source, input, condition, grouping, threshold, and window are all provided", async () => {
  const { onRun } = renderBuilder();
  const runButton = screen.getByRole("button", { name: /run simulation/i });
  expect(runButton).toBeDisabled();

  await userEvent.selectOptions(screen.getByLabelText(/playground source/i), "bank_app");
  await userEvent.selectOptions(screen.getByLabelText(/playground input format/i), "json_lines");
  expect(runButton).toBeDisabled();

  await fillMinimalValidRule();
  expect(runButton).toBeEnabled();

  await userEvent.click(runButton);
  expect(onRun).toHaveBeenCalled();
});

test("rejects a malformed MITRE technique id before calling onRun", async () => {
  const { onRun, onValidationError } = renderBuilder();
  await fillMinimalValidRule();
  await userEvent.type(screen.getByLabelText(/mitre technique id/i), "not-a-technique");

  await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

  expect(onRun).not.toHaveBeenCalled();
  expect(onValidationError).toHaveBeenCalledWith(expect.stringMatching(/mitre technique id must match/i));
});

test("Reset Rule clears all builder fields and calls onReset", async () => {
  const { onReset } = renderBuilder();
  await fillMinimalValidRule();

  await userEvent.click(screen.getByRole("button", { name: /reset rule/i }));

  expect(onReset).toHaveBeenCalled();
  expect(screen.getByLabelText(/playground source/i).value).toBe("");
  expect(screen.getByLabelText(/playground event input/i).value).toBe("");
});

test("updates the live plain-language summary from form state alone", async () => {
  renderBuilder();
  expect(screen.getByTestId("playground-rule-summary")).toHaveTextContent(/select a source/i);

  await fillMinimalValidRule();

  expect(screen.getByTestId("playground-rule-summary")).toHaveTextContent(/username equals "alice"/i);
  expect(screen.getByTestId("playground-rule-summary")).toHaveTextContent(/group by source_ip/i);
});

test("disables Run Simulation and shows a running label while a simulation is in flight", () => {
  renderBuilder({ running: true });
  const runButton = screen.getByRole("button", { name: /running simulation/i });
  expect(runButton).toBeDisabled();
});
