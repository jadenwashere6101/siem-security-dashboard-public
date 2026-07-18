import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import RepoArchitectureAssistantPanel from "./RepoArchitectureAssistantPanel";
import { getRepoAssistantStatus, sendRepoAssistantMessage } from "../services/repoAssistantService";

jest.mock("../services/repoAssistantService", () => ({
  getRepoAssistantStatus: jest.fn(),
  sendRepoAssistantMessage: jest.fn(),
}));

beforeEach(() => {
  jest.clearAllMocks();
  getRepoAssistantStatus.mockResolvedValue({ status: "available", indexed_files: 42 });
});

test("renders super-admin developer surface and repository index status", async () => {
  render(<RepoArchitectureAssistantPanel />);

  expect(screen.getByRole("heading", { name: /repo architecture assistant/i })).toBeInTheDocument();
  expect(screen.getByText(/super-admin developer tool/i)).toBeInTheDocument();
  expect(await screen.findByText(/42 files indexed/i)).toBeInTheDocument();
});

test("submits repo question, displays answer, citations, trust labels, metadata, and retrieval state", async () => {
  sendRepoAssistantMessage.mockResolvedValue({
    status: "success",
    answer: "Detection rules live in the catalog [engines/detection_rule_catalog.py:1-3].",
    insufficient_evidence: false,
    citations: [
      {
        path: "engines/detection_rule_catalog.py",
        line_start: 1,
        line_end: 3,
        trust_tier: 1,
        source_kind: "source",
        label: "current",
      },
    ],
    retrieval: { indexed_files: 42, matched_chunks: 2, refreshed: true, excluded_matches: [] },
    metadata: {
      provider: "ollama",
      model: "qwen3:4b-instruct",
      status: "success",
      local_request: true,
      paid_request: false,
      estimated_cost_usd: 0,
    },
    error: null,
  });

  render(<RepoArchitectureAssistantPanel />);
  expect(await screen.findByText(/42 files indexed/i)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText(/repository question/i), "Where do detection rules live?");
  await userEvent.click(screen.getByLabelText(/refresh index/i));
  await userEvent.click(screen.getByRole("button", { name: /ask repo ai/i }));

  expect(await screen.findByText(/detection rules live in the catalog/i)).toBeInTheDocument();
  expect(screen.getByText("ollama / qwen3:4b-instruct · success")).toBeInTheDocument();
  expect(screen.getByText("Local model · no API cost")).toBeInTheDocument();
  expect(screen.getByText(/Retrieval: 2 chunks from 42 files · refreshed/i)).toBeInTheDocument();
  expect(screen.getByText("engines/detection_rule_catalog.py:1-3")).toBeInTheDocument();
  expect(screen.getByText("Tier 1 · source · current")).toBeInTheDocument();
  expect(sendRepoAssistantMessage).toHaveBeenCalledWith(
    expect.objectContaining({
      message: "Where do detection rules live?",
      refresh: true,
    }),
    expect.objectContaining({ signal: expect.any(AbortSignal) })
  );
});

test("supports insufficient evidence, grounding failure, retry, cancel, and dismiss", async () => {
  let resolveRequest;
  sendRepoAssistantMessage
    .mockImplementationOnce(() => new Promise((resolve) => { resolveRequest = resolve; }))
    .mockRejectedValueOnce(Object.assign(new Error("Provider unavailable"), { payload: { status: "failed" } }))
    .mockResolvedValueOnce({
      status: "insufficient_evidence",
      answer: "I do not have enough current repository evidence to answer safely.",
      insufficient_evidence: true,
      citations: [],
      retrieval: { indexed_files: 42, matched_chunks: 0, refreshed: false, excluded_matches: [] },
      metadata: { status: "insufficient_evidence", provider: null, model: null },
      error: "No allowed current repository evidence matched the question.",
    })
    .mockResolvedValueOnce({
      status: "grounding_failure",
      answer: null,
      insufficient_evidence: true,
      citations: [],
      retrieval: { indexed_files: 42, matched_chunks: 1, refreshed: false, excluded_matches: [] },
      metadata: { status: "grounding_failure", provider: null, model: null },
      error: "AI answer did not include valid citations from retrieved repository evidence.",
    });

  render(<RepoArchitectureAssistantPanel />);
  expect(await screen.findByText(/42 files indexed/i)).toBeInTheDocument();
  await userEvent.type(screen.getByLabelText(/repository question/i), "Where is repo policy?");
  await userEvent.click(screen.getByRole("button", { name: /ask repo ai/i }));
  expect(screen.getByRole("status")).toHaveTextContent(/retrieving cited repository evidence/i);
  await userEvent.click(screen.getByRole("button", { name: /cancel/i }));
  resolveRequest({ status: "success", answer: "late", citations: [], retrieval: {}, metadata: {} });
  await waitFor(() => expect(screen.queryByText("late")).not.toBeInTheDocument());

  await userEvent.clear(screen.getByLabelText(/repository question/i));
  await userEvent.type(screen.getByLabelText(/repository question/i), "Retry case");
  await userEvent.click(screen.getByRole("button", { name: /ask repo ai/i }));
  expect(await screen.findByText("Provider unavailable")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /retry/i }));
  expect(await screen.findByText(/not have enough current repository evidence/i)).toBeInTheDocument();
  expect(screen.getByText("No allowed current repository evidence matched the question.")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /dismiss/i }));
  expect(screen.queryByText(/not have enough current repository evidence/i)).not.toBeInTheDocument();

  await userEvent.type(screen.getByLabelText(/repository question/i), "Grounding failure");
  await userEvent.click(screen.getByRole("button", { name: /ask repo ai/i }));
  expect(await screen.findByText(/blocked because its citations did not match/i)).toBeInTheDocument();
});
