import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AiAssistantButton from "./AiAssistantButton";

test("AiAssistantButton is accessible and clickable", async () => {
  const onClick = jest.fn();
  render(<AiAssistantButton onClick={onClick}>Explain alert</AiAssistantButton>);

  await userEvent.click(screen.getByRole("button", { name: "Explain alert" }));

  expect(onClick).toHaveBeenCalledTimes(1);
});

test("AiAssistantButton exposes loading state and blocks clicks", async () => {
  const onClick = jest.fn();
  render(<AiAssistantButton onClick={onClick} loading>Explain alert</AiAssistantButton>);

  const button = screen.getByRole("button", { name: "Asking AI..." });
  expect(button).toHaveAttribute("aria-busy", "true");
  await userEvent.click(button);

  expect(onClick).not.toHaveBeenCalled();
});
