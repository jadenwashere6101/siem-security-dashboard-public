import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AnalystWorkspace from "./AnalystWorkspace";

test("AnalystWorkspace renders private manual notebook content and actions", async () => {
  const onCreateNote = jest.fn();
  const onCreateHypothesis = jest.fn();
  const onCreateTask = jest.fn();
  const onRemovePin = jest.fn();
  const onDeleteNote = jest.fn();
  const onDeleteHypothesis = jest.fn();
  const onDeleteTask = jest.fn();
  const longToken = "very-long-investigation-token-without-natural-breaks-".repeat(4);
  render(
    <AnalystWorkspace
      workspaceState={{
        workspace: { id: 1, visibility: "private" },
        items: [{ id: 4, item_type: "alert", referenced_object_type: "alert", referenced_object_id: "7", label: `Alert #7 ${longToken}` }],
        investigations: [{ id: 8, title: "Investigation for alert #7", status: "open", linked_alert_id: 7, linked_source_ip: "203.0.113.7" }],
        notes: [{ id: 1, body: `Check login source ${longToken}` }],
        hypotheses: [{ id: 2, title: `Likely password spray ${longToken}`, status: "open" }],
        tasks: [{ id: 3, title: `Review MFA logs ${longToken}`, status: "open" }],
        evidence: [{ id: 5, label: "Primary alert", referenced_object_type: "alert", referenced_object_id: "7" }],
      }}
      onCreateNote={onCreateNote}
      onCreateHypothesis={onCreateHypothesis}
      onCreateTask={onCreateTask}
      onRemovePin={onRemovePin}
      onDeleteNote={onDeleteNote}
      onDeleteHypothesis={onDeleteHypothesis}
      onDeleteTask={onDeleteTask}
    />
  );

  expect(screen.getByRole("heading", { name: "Private investigation notebook" })).toBeInTheDocument();
  expect(screen.getByText("Nothing here mutates system data.", { exact: false })).toBeInTheDocument();
  expect(screen.getByText(/Alert #7/)).toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Remove" }));
  expect(onRemovePin).toHaveBeenCalledWith(4);

  expect(screen.getByText("Investigation for alert #7")).toBeInTheDocument();
  expect(screen.getAllByText(/alert:7/i).length).toBeGreaterThan(0);
  expect(screen.getAllByText(new RegExp(longToken.slice(0, 20)))[1]).toHaveStyle({ overflowWrap: "anywhere" });

  const deleteButtons = screen.getAllByRole("button", { name: "Delete" });
  await userEvent.click(deleteButtons[0]);
  expect(onDeleteNote).toHaveBeenCalledWith(1);
  await userEvent.click(deleteButtons[1]);
  expect(onDeleteHypothesis).toHaveBeenCalledWith(2);
  await userEvent.click(deleteButtons[2]);
  expect(onDeleteTask).toHaveBeenCalledWith(3);

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
  render(<AnalystWorkspace workspaceState={{ workspace: { visibility: "private" }, items: [], investigations: [], notes: [], hypotheses: [], tasks: [], evidence: [] }} />);
  expect(screen.getByText(/never automatically populated/i)).toBeInTheDocument();
});
