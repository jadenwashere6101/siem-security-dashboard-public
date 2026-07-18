import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import FloatingSiemChat from "./FloatingSiemChat";

test("FloatingSiemChat submits a general SIEM question", async () => {
  const onAsk = jest.fn();
  render(<FloatingSiemChat onAsk={onAsk} />);

  await userEvent.click(screen.getByRole("button", { name: "Open general SIEM AI chat" }));
  await userEvent.type(
    screen.getByPlaceholderText("Ask a general question about what you are seeing..."),
    "What does this graph mean?"
  );
  await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

  expect(onAsk).toHaveBeenCalledWith("What does this graph mean?");
});

test("FloatingSiemChat does not persist chat text to local storage", async () => {
  const setItem = jest.spyOn(window.localStorage.__proto__, "setItem");
  render(<FloatingSiemChat onAsk={() => {}} />);

  await userEvent.click(screen.getByRole("button", { name: "Open general SIEM AI chat" }));
  await userEvent.type(
    screen.getByPlaceholderText("Ask a general question about what you are seeing..."),
    "Do not persist this"
  );
  await userEvent.click(screen.getByRole("button", { name: "Ask AI" }));

  expect(setItem).not.toHaveBeenCalled();
});
