import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AiResponsePanel from "./AiResponsePanel";

test("AiResponsePanel displays answer, source metadata, and local no-cost label", () => {
  render(
    <AiResponsePanel
      state={{
        status: "success",
        title: "Alert #1",
        response: {
          answer: "Review the failed login spike.",
          insufficient_context: false,
          context: { sources: [{ source_type: "alert" }], omitted_count: 0 },
          metadata: {
            provider: "ollama",
            model: "llama3",
            status: "success",
            local_request: true,
            paid_request: false,
            estimated_cost_usd: 0,
          },
        },
      }}
      onDismiss={() => {}}
      onRetry={() => {}}
      onCancel={() => {}}
    />
  );

  expect(screen.getByText("Alert #1")).toBeInTheDocument();
  expect(screen.getByText("Review the failed login spike.")).toBeInTheDocument();
  expect(screen.getByText("Local model · no API cost")).toBeInTheDocument();
  expect(screen.getByText("1 sources")).toBeInTheDocument();
});

test("AiResponsePanel supports retry for failed requests", async () => {
  const onRetry = jest.fn();
  render(
    <AiResponsePanel
      state={{ status: "error", title: "AI failed", error: "Provider unavailable" }}
      onDismiss={() => {}}
      onRetry={onRetry}
      onCancel={() => {}}
    />
  );

  await userEvent.click(screen.getByRole("button", { name: "Retry" }));

  expect(onRetry).toHaveBeenCalledTimes(1);
});

test("AiResponsePanel supports cancel and dismissal during loading", async () => {
  const onCancel = jest.fn();
  const onDismiss = jest.fn();
  render(
    <AiResponsePanel
      state={{ status: "loading", title: "Loading AI" }}
      onDismiss={onDismiss}
      onRetry={() => {}}
      onCancel={onCancel}
    />
  );

  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));
  await userEvent.click(screen.getByRole("button", { name: "Dismiss AI response" }));

  expect(onCancel).toHaveBeenCalledTimes(1);
  expect(onDismiss).toHaveBeenCalledTimes(1);
});

test("AiResponsePanel renders insufficient context and stale warnings", () => {
  render(
    <AiResponsePanel
      state={{
        status: "success",
        title: "Stale answer",
        stale: true,
        response: {
          answer: "I do not have enough SIEM context to answer safely.",
          insufficient_context: true,
          error: "No visible SIEM context was supplied.",
          context: { sources: [], omitted_count: 2 },
          metadata: { status: "fallback_blocked", provider: null, model: null },
        },
      }}
      onDismiss={() => {}}
      onRetry={() => {}}
      onCancel={() => {}}
    />
  );

  expect(screen.getByText("No visible SIEM context was supplied.")).toBeInTheDocument();
  expect(screen.getByText("This answer may be stale because the visible SIEM context changed.")).toBeInTheDocument();
  expect(screen.getByText("0 sources · 2 omitted")).toBeInTheDocument();
});
