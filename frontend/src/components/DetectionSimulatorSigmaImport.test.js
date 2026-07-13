import React from "react";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import DetectionSimulatorSigmaImport from "./DetectionSimulatorSigmaImport";
import DetectionSimulatorSigmaPreview from "./DetectionSimulatorSigmaPreview";
import { SAMPLE_SIGMA_BANK_APP_YAML } from "../utils/detectionSimulatorSigmaSamples";
import { SIGMA_SUBSET_COMPATIBILITY_DISCLOSURE } from "../utils/detectionSimulatorPlaygroundContract";

const pasteInto = (element, value) => fireEvent.change(element, { target: { value } });

describe("DetectionSimulatorSigmaImport", () => {
  test("submits sigma_yaml and events without evaluating Sigma client-side", async () => {
    const onRun = jest.fn();
    render(
      <DetectionSimulatorSigmaImport
        running={false}
        onRun={onRun}
        onReset={jest.fn()}
        onValidationError={jest.fn()}
      />
    );

    expect(screen.getByTestId("sigma-mode-disclosure")).toHaveTextContent(/not full Sigma compatibility/i);
    expect(screen.getByTestId("sigma-mode-disclosure")).toHaveTextContent(SIGMA_SUBSET_COMPATIBILITY_DISCLOSURE);

    await userEvent.click(screen.getByRole("button", { name: /load sample sigma rule/i }));
    await userEvent.click(screen.getByRole("button", { name: /load sample events/i }));
    await userEvent.click(screen.getByRole("button", { name: /run simulation/i }));

    expect(onRun).toHaveBeenCalledTimes(1);
    const payload = onRun.mock.calls[0][0];
    expect(payload).toEqual(
      expect.objectContaining({
        simulation_mode: "sigma_subset_import",
        sigma_yaml: SAMPLE_SIGMA_BANK_APP_YAML,
        input_format: "json_array",
      })
    );
    expect(payload.input_text).toContain("admin_user");
    expect(payload).not.toHaveProperty("temporary_rule");
    expect(payload).not.toHaveProperty("rule_id");
  });

  test("Reset / Discard clears the form fields", async () => {
    const onReset = jest.fn();
    render(
      <DetectionSimulatorSigmaImport
        running={false}
        onRun={jest.fn()}
        onReset={onReset}
        onValidationError={jest.fn()}
      />
    );

    await userEvent.click(screen.getByRole("button", { name: /load sample sigma rule/i }));
    expect(screen.getByLabelText(/sigma yaml input/i).value).toContain("Bank failed login subset");

    await userEvent.click(screen.getByRole("button", { name: /reset \/ discard/i }));
    expect(onReset).toHaveBeenCalled();
    expect(screen.getByLabelText("Sigma YAML input").value).toBe("");
    expect(screen.getByLabelText("Sigma event input").value).toBe("");
  });

  test("requires yaml and events before submit", async () => {
    const onRun = jest.fn();
    const onValidationError = jest.fn();
    render(
      <DetectionSimulatorSigmaImport
        running={false}
        onRun={onRun}
        onReset={jest.fn()}
        onValidationError={onValidationError}
      />
    );

    pasteInto(screen.getByLabelText(/sigma yaml input/i), "title: incomplete");
    // Run stays disabled until events are present.
    expect(screen.getByRole("button", { name: /run simulation/i })).toBeDisabled();
    expect(onRun).not.toHaveBeenCalled();
  });

  test("controls are keyboard-focusable with no console errors", async () => {
    const errorSpy = jest.spyOn(console, "error").mockImplementation(() => {});
    render(
      <DetectionSimulatorSigmaImport
        running={false}
        onRun={jest.fn()}
        onReset={jest.fn()}
        onValidationError={jest.fn()}
      />
    );

    screen.getByLabelText(/sigma yaml input/i).focus();
    expect(screen.getByLabelText(/sigma yaml input/i)).toHaveFocus();
    await userEvent.tab();
    expect(screen.getByLabelText(/sigma event input format/i)).toHaveFocus();

    expect(errorSpy).not.toHaveBeenCalled();
    errorSpy.mockRestore();
  });
});

describe("DetectionSimulatorSigmaPreview", () => {
  test("renders backend-authored metadata and compiled predicate without inventing mappings", () => {
    render(
      <DetectionSimulatorSigmaPreview
        result={{
          simulation_mode: "sigma_subset_import",
          sigma_subset_compatibility: "Strict Sigma subset import; not full Sigma compatibility.",
          normalized_internal_rule_preview: {
            title: "Bank failed login subset",
            id: "11111111-1111-1111-1111-111111111111",
            level: "high",
            severity: "high",
            source: "bank_app",
            source_type: "custom",
            status: "experimental",
            author: "playground",
            date: "2026/07/13",
            tags: ["attack.t1110", "credential_access"],
            attack_tags: ["T1110"],
            logsource: { product: "bank_app" },
            evaluator: "temporary_playground_rule",
            description: "Strict subset example",
            condition: {
              all: [
                { field: "event_type", operator: "equals", value: "failed_login" },
                { field: "username", operator: "contains", value: "admin" },
              ],
            },
          },
        }}
      />
    );

    const preview = screen.getByTestId("sigma-internal-rule-preview");
    expect(within(preview).getByTestId("sigma-compatibility-disclosure")).toHaveTextContent(
      /not full Sigma compatibility/i
    );
    expect(within(preview).getByTestId("sigma-metadata-preview")).toHaveTextContent("Bank failed login subset");
    expect(within(preview).getByTestId("sigma-metadata-preview")).toHaveTextContent("bank_app");
    expect(within(preview).getByTestId("sigma-metadata-preview")).toHaveTextContent("T1110");
    expect(within(preview).getByTestId("sigma-compiled-predicate")).toHaveTextContent(
      /event_type equals "failed_login"/
    );
    expect(within(preview).getByTestId("sigma-compiled-predicate")).toHaveTextContent(
      /username contains "admin"/
    );
  });

  test("renders nothing for non-sigma simulation modes", () => {
    const { container } = render(
      <DetectionSimulatorSigmaPreview
        result={{ simulation_mode: "temporary_playground_rule", stages: {} }}
      />
    );
    expect(container).toBeEmptyDOMElement();
  });
});
