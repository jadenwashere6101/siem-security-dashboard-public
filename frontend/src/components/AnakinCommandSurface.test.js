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

  expect(screen.getByRole("dialog", { name: "Anakin command surface" })).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Summarize" })).toBeInTheDocument();

  const dialog = screen.getByRole("dialog", { name: "Anakin command surface" });
  await userEvent.type(within(dialog).getByRole("textbox", { name: "Ask Anakin" }), "What matters?");
  await userEvent.click(within(dialog).getByRole("button", { name: "Submit Ask Anakin question" }));

  expect(onExecute).toHaveBeenCalledWith(
    expect.objectContaining({ id: "anakin.ask" }),
    expect.objectContaining({ question: "What matters?" })
  );

  await userEvent.keyboard("{Escape}");
  expect(screen.queryByRole("dialog", { name: "Anakin command surface" })).not.toBeInTheDocument();
  await waitFor(() => expect(trigger).toHaveFocus());
});
