import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AlertSidePanel from "./AlertSidePanel";

test("provides accessible dialog semantics, close control, and narrow viewport sizing", async () => {
  const onClose = jest.fn();
  render(
    <AlertSidePanel onClose={onClose}>
      <p>Readable alert content</p>
    </AlertSidePanel>
  );

  const dialog = screen.getByRole("dialog", { name: "Alert Details" });
  expect(dialog).toHaveAttribute("aria-modal", "true");
  expect(dialog).toHaveStyle({ width: "min(420px, 100vw)", color: "#fff" });

  await userEvent.click(screen.getByRole("button", { name: "Close alert details" }));
  expect(onClose).toHaveBeenCalledTimes(1);
});
