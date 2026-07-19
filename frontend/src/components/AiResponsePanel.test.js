import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import AiResponsePanel from "./AiResponsePanel";
import { confirmAiAction, previewAiAction } from "../services/aiService";

jest.mock("../services/aiService", () => ({
  previewAiAction: jest.fn(),
  confirmAiAction: jest.fn(),
}));

beforeEach(() => {
  previewAiAction.mockReset();
  confirmAiAction.mockReset();
});

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

test("AiResponsePanel renders read-only tool evidence metadata", () => {
  render(
    <AiResponsePanel
      state={{
        status: "success",
        title: "Tool-assisted answer",
        response: {
          answer: "The source IP is linked to recent alerts.",
          insufficient_context: false,
          context: { sources: [{ source_type: "visible_context" }], omitted_count: 0 },
          metadata: {
            provider: "ollama",
            model: "qwen3:4b-instruct",
            status: "success",
            local_request: true,
            paid_request: false,
            estimated_cost_usd: 0,
          },
          tools: {
            used: true,
            read_only: true,
            truncated: true,
            omitted_count: 1,
            calls: [
              {
                tool_name: "get_source_ip_context",
                status: "success",
                sources: [{ source_path: "/source-ip-context" }],
              },
              {
                tool_name: "read_audit_log",
                status: "forbidden",
                sources: [],
              },
            ],
          },
        },
      }}
      onDismiss={() => {}}
      onRetry={() => {}}
      onCancel={() => {}}
    />
  );

  expect(screen.getByLabelText("Read-only AI tool evidence")).toBeInTheDocument();
  expect(screen.getByText("2 read tools · 1 limited/failed · 1 omitted")).toBeInTheDocument();
  expect(screen.getByText("get_source_ip_context")).toBeInTheDocument();
  expect(screen.getByText("read_audit_log")).toBeInTheDocument();
  expect(screen.getByText("forbidden")).toBeInTheDocument();
});

test("AiResponsePanel renders AI drafts as review-only not-applied payloads", () => {
  render(
    <AiResponsePanel
      state={{
        status: "success",
        title: "Draft incident note",
        response: {
          draft: {
            draft_type: "incident_note",
            title: "Incident note draft",
            labels: {
              ai_generated: true,
              read_only: true,
              persisted: false,
              applied: false,
              approval_required_before_apply: true,
            },
            validation: { valid: true, errors: [] },
            payload: {
              summary: "Suspicious scan activity observed.",
              evidence: ["Alert #7 fired"],
              recommended_next_steps: ["Review related events"],
            },
          },
          context: { sources: [{ source_type: "incident" }], omitted_count: 0 },
          metadata: {
            provider: "ollama",
            model: "qwen3:4b-instruct",
            status: "success",
            local_request: true,
            paid_request: false,
            estimated_cost_usd: 0,
          },
          tools: { used: false, calls: [] },
        },
      }}
      onDismiss={() => {}}
      onRetry={() => {}}
      onCancel={() => {}}
    />
  );

  expect(screen.getByLabelText("AI-generated draft review")).toBeInTheDocument();
  expect(screen.getByText("AI-generated draft")).toBeInTheDocument();
  expect(screen.getByText("Not saved")).toBeInTheDocument();
  expect(screen.getByText("Not applied")).toBeInTheDocument();
  expect(screen.getByText("Review required before apply")).toBeInTheDocument();
  expect(screen.getByText("Suspicious scan activity observed.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /apply/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /approve/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /execute/i })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /save/i })).not.toBeInTheDocument();
});

test("AiResponsePanel shows draft validation errors without payload submission controls", () => {
  render(
    <AiResponsePanel
      state={{
        status: "success",
        title: "Invalid draft",
        response: {
          error: "AI draft response did not match the required schema.",
          draft: {
            draft_type: "incident_note",
            title: "Incident note draft",
            labels: {
              ai_generated: true,
              read_only: true,
              persisted: false,
              applied: false,
              approval_required_before_apply: true,
            },
            validation: { valid: false, errors: ["evidence is required"] },
            payload: {},
          },
          context: { sources: [], omitted_count: 0 },
          metadata: { status: "draft_validation_failed" },
          tools: { used: false, calls: [] },
        },
      }}
      onDismiss={() => {}}
      onRetry={() => {}}
      onCancel={() => {}}
    />
  );

  expect(screen.getByText("Needs review")).toBeInTheDocument();
  expect(screen.getByText("evidence is required")).toBeInTheDocument();
  expect(screen.getByText("No valid draft payload was returned.")).toBeInTheDocument();
  expect(screen.queryByRole("button", { name: /run/i })).not.toBeInTheDocument();
});

test("AiResponsePanel previews and confirms incident-note actions only after acknowledgement", async () => {
  previewAiAction.mockResolvedValue({
    status: "preview_ready",
    preview: {
      action_type: "add_incident_note",
      required_role: "analyst_or_super_admin",
      dispatch_path: "core.note_store.create_incident_note",
      target_resource_keys: ["incident:7"],
      target_fingerprint: "fingerprint",
      payload_digest: "digest",
      confirmation_token: "token",
      payload: { incident_id: 7, note_text: "Suspicious scan activity observed." },
      stale: false,
    },
  });
  confirmAiAction.mockResolvedValue({
    status: "confirmed",
    result: { outcome: "real", message: "Incident note added.", no_production_change: false },
  });

  render(
    <AiResponsePanel
      userRole="analyst"
      state={{
        status: "success",
        title: "Draft incident note",
        response: {
          draft: {
            draft_type: "incident_note",
            title: "Incident note draft",
            generated_at: "2026-07-19T00:00:00Z",
            labels: {
              ai_generated: true,
              read_only: true,
              persisted: false,
              applied: false,
              approval_required_before_apply: true,
            },
            validation: { valid: true, errors: [] },
            payload: {
              summary: "Suspicious scan activity observed.",
              evidence: ["Alert #7 fired"],
              uncertainty: "Source owner unknown.",
              recommended_next_steps: ["Review related events"],
            },
          },
          context: {
            sources: [{ source_type: "incident", record_ids: [7] }],
            omitted_count: 0,
          },
          metadata: { status: "success", local_request: true, paid_request: false },
          tools: { used: false, calls: [] },
        },
      }}
      onDismiss={() => {}}
      onRetry={() => {}}
      onCancel={() => {}}
    />
  );

  await userEvent.click(screen.getByRole("button", { name: /preview exact action payload/i }));
  expect(await screen.findByText(/Exact payload before confirmation/i)).toBeInTheDocument();
  expect(screen.getByText(/incident:7/i)).toBeInTheDocument();

  const confirmButton = screen.getByRole("button", { name: /confirm action/i });
  expect(confirmButton).toBeDisabled();

  await userEvent.click(screen.getByLabelText(/I reviewed the exact payload/i));
  expect(confirmButton).not.toBeDisabled();
  await userEvent.click(confirmButton);

  expect(previewAiAction).toHaveBeenCalledWith(
    expect.objectContaining({
      action_type: "add_incident_note",
      payload: expect.objectContaining({ incident_id: 7 }),
    })
  );
  expect(confirmAiAction).toHaveBeenCalledWith(
    expect.objectContaining({
      action_type: "add_incident_note",
      confirm: true,
      confirmation_token: "token",
      payload_digest: "digest",
      target_fingerprint: "fingerprint",
    })
  );
  expect(await screen.findByText("real")).toBeInTheDocument();
  expect(screen.getByText("Incident note added.")).toBeInTheDocument();
});

test("AiResponsePanel blocks stale preview confirmation and supports rejection no-mutation state", async () => {
  previewAiAction.mockResolvedValue({
    status: "preview_ready",
    preview: {
      target_resource_keys: ["incident:7"],
      target_fingerprint: "fingerprint",
      payload_digest: "digest",
      confirmation_token: "token",
      required_role: "analyst_or_super_admin",
      payload: { incident_id: 7, note_text: "Reviewed note" },
      stale: true,
    },
  });

  render(
    <AiResponsePanel
      userRole="analyst"
      state={{
        status: "success",
        title: "Draft incident note",
        response: {
          draft: {
            draft_type: "incident_note",
            title: "Incident note draft",
            generated_at: "2026-07-19T00:00:00Z",
            labels: { ai_generated: true, read_only: true, persisted: false, applied: false, approval_required_before_apply: true },
            validation: { valid: true, errors: [] },
            payload: { summary: "Reviewed note", evidence: [], uncertainty: "", recommended_next_steps: [] },
          },
          context: { sources: [{ source_type: "incident", record_ids: [7] }], omitted_count: 0 },
          metadata: { status: "success" },
          tools: { used: false, calls: [] },
        },
      }}
      onDismiss={() => {}}
      onRetry={() => {}}
      onCancel={() => {}}
    />
  );

  await userEvent.click(screen.getByRole("button", { name: /preview exact action payload/i }));
  expect(await screen.findByText(/This preview is stale/i)).toBeInTheDocument();
  await userEvent.click(screen.getByLabelText(/I reviewed the exact payload/i));
  expect(screen.getByRole("button", { name: /confirm action/i })).toBeDisabled();

  await userEvent.click(screen.getByRole("button", { name: /reject action/i }));
  expect(await screen.findByText("rejected")).toBeInTheDocument();
  expect(screen.getByText("No production change made.")).toBeInTheDocument();
  expect(confirmAiAction).not.toHaveBeenCalled();
});
