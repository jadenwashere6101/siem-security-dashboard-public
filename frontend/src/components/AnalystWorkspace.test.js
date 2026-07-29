import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AnalystWorkspace from "./AnalystWorkspace";

test("AnalystWorkspace renders private manual notebook content and actions", async () => {
  const onCreateNote = jest.fn();
  const onCreateHypothesis = jest.fn();
  const onCreateTask = jest.fn();
  const onRemovePin = jest.fn();
  render(
    <AnalystWorkspace
      workspaceState={{
        workspace: { id: 1, visibility: "private" },
        items: [{ id: 4, item_type: "alert", referenced_object_type: "alert", referenced_object_id: "7", label: "Alert #7" }],
        notes: [{ id: 1, body: "Check login source" }],
        hypotheses: [{ id: 2, title: "Likely password spray", status: "open" }],
        tasks: [{ id: 3, title: "Review MFA logs", status: "open" }],
        evidence: [{ id: 5, label: "Primary alert", referenced_object_type: "alert", referenced_object_id: "7" }],
      }}
      onCreateNote={onCreateNote}
      onCreateHypothesis={onCreateHypothesis}
      onCreateTask={onCreateTask}
      onRemovePin={onRemovePin}
    />
  );

  expect(screen.getByRole("heading", { name: "Private investigation notebook" })).toBeInTheDocument();
  expect(screen.getByText("Nothing here mutates system data.", { exact: false })).toBeInTheDocument();
  expect(screen.getByText("Alert #7")).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Remove" }));
  expect(onRemovePin).toHaveBeenCalledWith(4);

  await userEvent.type(screen.getByLabelText("New note"), "New private note");
  await userEvent.click(screen.getByRole("button", { name: "Add note" }));
  expect(onCreateNote).toHaveBeenCalledWith("New private note");

  await userEvent.type(screen.getByLabelText("New hypothesis"), "New private hypothesis");
  await userEvent.click(screen.getByRole("button", { name: "Add hypothesis" }));
  expect(onCreateHypothesis).toHaveBeenCalledWith("New private hypothesis");

  await userEvent.type(screen.getByLabelText("New task"), "New private task");
  await userEvent.click(screen.getByRole("button", { name: "Add task" }));
  expect(onCreateTask).toHaveBeenCalledWith("New private task");
});

test("AnalystWorkspace empty state says content is not automatic", () => {
  render(<AnalystWorkspace workspaceState={{ workspace: { visibility: "private" }, items: [], notes: [], hypotheses: [], tasks: [], evidence: [] }} />);
  expect(screen.getByText(/never automatically populated/i)).toBeInTheDocument();
});
