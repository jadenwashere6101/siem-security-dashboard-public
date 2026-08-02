import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AnakinCommandSurface from "./AnakinCommandSurface";
import { createDefaultAnakinCommands } from "../utils/anakinCommandRegistry";

test("AnakinCommandSurface opens, executes commands, and closes with Escape", async () => {
  const onExecute = jest.fn();
  render(
    <AnakinCommandSurface
      commands={createDefaultAnakinCommands()}
      context={{ workspace: { activeSection: "dashboard" } }}
      onExecute={onExecute}
    />
  );

  const trigger = screen.getByRole("button", { name: "Ask Anakin" });
  await userEvent.click(trigger);

  expect(screen.getByRole("dialog", { name: "Anakin conversation" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Explain this alert" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Investigate further" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Recommend next action" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Draft an analyst artifact" })).toBeInTheDocument();

  const dialog = screen.getByRole("dialog", { name: "Anakin conversation" });
  await userEvent.type(within(dialog).getByRole("textbox", { name: "Ask Anakin" }), "What matters?");
  await userEvent.click(within(dialog).getByRole("button", { name: "Submit Ask Anakin question" }));

  expect(onExecute).toHaveBeenCalledWith(
    expect.objectContaining({ id: "anakin.ask-freeform", workflow: "auto" }),
    expect.objectContaining({ question: "What matters?" })
  );

  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "Anakin conversation" })).not.toBeInTheDocument();
  await waitFor(() => expect(screen.getByRole("button", { name: "Ask Anakin" })).toHaveFocus());
});

test("renders ordered authoritative turns, remembered state, and artifact safety without internal metadata", async () => {
  const turns = [
    {
      turn_id: "atn_user",
      sequence: 1,
      role: "user",
      workflow: "deep_investigate",
      content: "Investigate alert 42.",
      lifecycle_status: "completed",
    },
    {
      turn_id: "atn_assistant",
      sequence: 2,
      role: "assistant",
      workflow: "generate_artifact",
      assertion_type: "artifact_preview",
      content: "Draft escalation summary for analyst review.",
      lifecycle_status: "completed",
      artifact_safety: { preview_only: true, persisted: false, applied: false, approval_required: true },
      structured_payload: { tool_name: "internal_tool", workflow_request: "hidden" },
    },
  ];
  const thread = {
    thread_id: "ath_42",
    primary_entity: { type: "alert", id: "42" },
    focus_state: { active: { type: "alert", id: "42" } },
    state: {
      compact_summary: "Alert 42 remains under review.",
      unresolved_questions: [{ question: "Was authentication successful?" }],
      corrections: [{ content: "The scanner is not approved." }],
    },
  };

  render(
    <AnakinCommandSurface
      open
      commands={createDefaultAnakinCommands()}
      thread={thread}
      turns={turns}
      state={{ status: "idle", response: null }}
      onExecute={() => {}}
    />
  );

  const renderedTurns = document.querySelectorAll("[data-turn-sequence]");
  expect(Array.from(renderedTurns).map((node) => node.getAttribute("data-turn-sequence"))).toEqual(["1", "2"]);
  expect(screen.getByText("Alert 42")).toBeInTheDocument();
  expect(screen.getByText("Preview only")).toBeInTheDocument();
  expect(screen.getByText("Not applied")).toBeInTheDocument();
  expect(screen.getByText("Not persisted as an operational record")).toBeInTheDocument();
  expect(screen.getByText("Approval required before apply")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "What Anakin remembers" }));
  expect(screen.getByText(/alert 42 remains under review/i)).toBeInTheDocument();
  expect(screen.getByText(/open questions:/i)).toBeInTheDocument();
  expect(screen.queryByText(/internal_tool|workflow_request|canonical workflow|async request/i)).not.toBeInTheDocument();
});

test("shows per-turn progress, retry, reset, and new-thread actions in the same surface", async () => {
  const onCancel = jest.fn();
  const onReset = jest.fn();
  const onNewThread = jest.fn();
  const { rerender } = render(
    <AnakinCommandSurface
      open
      commands={createDefaultAnakinCommands()}
      thread={{ thread_id: "ath_1", primary_entity: { type: "incident", id: "9" } }}
      turns={[]}
      state={{ status: "loading", response: { workflow: "deep_investigate" } }}
      onCancel={onCancel}
      onReset={onReset}
      onNewThread={onNewThread}
      onExecute={() => {}}
    />
  );

  expect(screen.getAllByRole("dialog", { name: "Anakin conversation" })).toHaveLength(1);
  expect(screen.getByText(/correlating evidence/i)).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: "Stop waiting" }));
  expect(onCancel).toHaveBeenCalledTimes(1);

  rerender(
    <AnakinCommandSurface
      open
      commands={createDefaultAnakinCommands()}
      thread={{ thread_id: "ath_1", primary_entity: { type: "incident", id: "9" } }}
      turns={[]}
      state={{ status: "idle", response: null }}
      onReset={onReset}
      onNewThread={onNewThread}
      onExecute={() => {}}
    />
  );
  await userEvent.click(screen.getByRole("button", { name: "Reset" }));
  await userEvent.click(screen.getByRole("button", { name: "New thread" }));
  expect(onReset).toHaveBeenCalledTimes(1);
  expect(onNewThread).toHaveBeenCalledTimes(1);
});

test("offers retry for a failed turn without mounting a second response dialog", async () => {
  const onRetry = jest.fn();
  render(
    <AnakinCommandSurface
      open
      commands={createDefaultAnakinCommands()}
      turns={[]}
      state={{ status: "error", error: "Evidence lookup failed.", response: null }}
      onRetry={onRetry}
      onExecute={() => {}}
    />
  );

  expect(screen.getAllByRole("dialog")).toHaveLength(1);
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(onRetry).toHaveBeenCalledTimes(1);
});
