import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import CommandPalette from "./CommandPalette";

test("CommandPalette opens with Ctrl+K, filters read-only commands, executes, and returns focus", async () => {
  const onExecute = jest.fn();
  const onOpenChange = jest.fn();
  render(
    <>
      <button type="button">Before</button>
      <CommandPalette
        commands={[
          { id: "navigate.dashboard", label: "Dashboard", group: "Navigation", readOnly: true, description: "Open dashboard" },
          { id: "retry.dead-letter", label: "Retry dead letter", group: "Mutation", readOnly: true },
        ]}
        objects={[{ id: "alert.1", label: "failed_login", group: "Alert lookup", readOnly: true, description: "203.0.113.10" }]}
        onExecute={onExecute}
        onOpenChange={onOpenChange}
      />
    </>
  );

  const before = screen.getByRole("button", { name: "Before" });
  before.focus();
  await userEvent.keyboard("{Control>}k{/Control}");

  expect(screen.getByRole("dialog", { name: "Command palette" })).toBeInTheDocument();
  expect(onOpenChange).toHaveBeenCalledWith(true);
  expect(screen.getByRole("option", { name: /Dashboard/ })).toBeInTheDocument();
  expect(screen.queryByRole("option", { name: /Retry dead letter/ })).not.toBeInTheDocument();

  await userEvent.type(screen.getByRole("textbox", { name: "Command palette" }), "failed");
  await userEvent.keyboard("{Enter}");

  expect(onExecute).toHaveBeenCalledWith(expect.objectContaining({ id: "alert.1" }));
  expect(onOpenChange).toHaveBeenLastCalledWith(false);
  expect(screen.queryByRole("dialog", { name: "Command palette" })).not.toBeInTheDocument();
  await waitFor(() => expect(before).toHaveFocus());
});
