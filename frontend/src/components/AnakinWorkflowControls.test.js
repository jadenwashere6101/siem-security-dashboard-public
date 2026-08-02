import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AnakinWorkflowControls, { ANAKIN_WORKFLOWS } from "./AnakinWorkflowControls";

test("AnakinWorkflowControls renders compact workflow shortcuts and one artifact menu", async () => {
  const onAskAi = jest.fn();
  render(
    <AnakinWorkflowControls
      contextType="alert"
      context={{ alert_id: 7, source_ip: "203.0.113.77" }}
      controls={[
        ANAKIN_WORKFLOWS.quickExplain,
        ANAKIN_WORKFLOWS.deepInvestigate,
        ANAKIN_WORKFLOWS.decisionSupport,
      ]}
      artifacts={[
        { type: "investigation_checklist", label: "Checklist" },
        { type: "response_recommendation", label: "Response Recommendation" },
      ]}
      titlePrefix="Alert #7"
      subject="alert #7"
      onAskAi={onAskAi}
    />
  );

  expect(screen.getByText("Anakin")).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Explain alert" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Investigate further" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Recommend next action" })).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Draft an analyst artifact" })).not.toBeInTheDocument();
  expect(screen.getByLabelText("Draft an analyst artifact")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Investigate further" }));
  await userEvent.selectOptions(screen.getByLabelText("Draft an analyst artifact"), "response_recommendation");

  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      workflow: "deep_investigate",
      contextType: "alert",
      context: { alert_id: 7, source_ip: "203.0.113.77" },
      toolPolicy: { max_tool_calls: 5, time_window_hours: 24 },
    })
  );
  expect(onAskAi).toHaveBeenCalledWith(
    expect.objectContaining({
      workflow: "generate_artifact",
      artifactType: "response_recommendation",
      contextType: "alert",
      context: { alert_id: 7, source_ip: "203.0.113.77" },
      toolPolicy: { max_tool_calls: 3, time_window_hours: 24 },
    })
  );
});

test("AnakinWorkflowControls keeps responsive wrapping and does not render without a handler", () => {
  const { container, rerender } = render(
    <AnakinWorkflowControls
      contextType="dashboard"
      controls={[ANAKIN_WORKFLOWS.auto, ANAKIN_WORKFLOWS.quickExplain]}
      onAskAi={() => {}}
    />
  );

  expect(container.firstChild).toHaveStyle({ display: "flex", flexWrap: "wrap" });

  rerender(
    <AnakinWorkflowControls
      contextType="dashboard"
      controls={[ANAKIN_WORKFLOWS.auto, ANAKIN_WORKFLOWS.quickExplain]}
    />
  );
  expect(container.firstChild).toBeNull();
});
