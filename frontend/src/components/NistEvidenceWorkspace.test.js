import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import NistEvidenceWorkspace, { NIST_STATUS_LABELS } from "./NistEvidenceWorkspace";
import {
  createNistBoundary,
  getNistExplanationRequest,
  loadNistBoundaries,
  loadNistEvidence,
  loadNistResults,
  loadNistRuns,
  nistExportUrl,
  queueNistExplanation,
  startNistAssessment,
  updateNistBoundary,
} from "../services/nistEvidenceService";

jest.mock("../services/nistEvidenceService", () => ({
  createNistBoundary: jest.fn(),
  getNistExplanationRequest: jest.fn(),
  loadNistBoundaries: jest.fn(),
  loadNistEvidence: jest.fn(),
  loadNistResults: jest.fn(),
  loadNistRuns: jest.fn(),
  nistExportUrl: jest.fn((runId, format) => `/nist/export/${runId}.${format}`),
  queueNistExplanation: jest.fn(),
  startNistAssessment: jest.fn(),
  updateNistBoundary: jest.fn(),
}));

const boundary = {
  id: 7,
  name: "Production enclave",
  description: "Declared production scope",
  selected_sources: ["pfsense", "azure_insights"],
  environments: ["prod"],
  default_window_hours: 24,
  is_active: true,
  scope_declaration: "Assessment scope is declared by an authorized user.",
};

const run = {
  id: 11,
  boundary_id: 7,
  framework_id: "nist_sp_800_171",
  framework_version: "rev3",
  catalog_version: "v1",
  catalog_hash: "a".repeat(64),
  collector_version: "v1",
  requested_window_start: "2026-08-12T09:00:00Z",
  requested_window_end: "2026-08-12T10:00:00Z",
  status: "completed_with_partial_evidence",
  summary_counts: {
    requirement_count: 12,
    catalog_version: "v1",
    by_collection_confidence: { healthy: 1, degraded: 11 },
    by_evidence_status: { evidence_available: 1, partial_evidence: 11 },
  },
  created_at: "2026-08-12T10:00:00Z",
};

const results = [
  {
    id: 20,
    run_id: 11,
    requirement_id: "03.03.01",
    requirement_name: "Event Logging",
    mapping_strength: "strong_siem_evidence",
    evidence_status: "evidence_available",
    collection_confidence: "healthy",
    reason_code: "qualifying_evidence_found",
    limitation: "SIEM-visible evidence only.",
    evidence_count: 30,
    omitted_count: 2,
  },
  {
    id: 21,
    run_id: 11,
    requirement_id: "03.03.02",
    requirement_name: "Audit Record Content",
    mapping_strength: "partial_siem_evidence",
    evidence_status: "partial_evidence",
    collection_confidence: "degraded",
    reason_code: "collection_degraded",
    limitation: "Collection degradation limits absence interpretation.",
    evidence_count: 0,
    omitted_count: 0,
  },
];

const references = [
  {
    id: 31,
    evidence_category: "alerts",
    evidence_type: "threshold_alert",
    canonical_source: "pfsense",
    source_type: "firewall",
    source_health_state: "healthy",
    entity_type: "alert",
    entity_id: "501",
    occurrence_timestamp: "2026-08-12T09:30:00Z",
    ingestion_timestamp: "2026-08-12T09:30:01Z",
    collection_timestamp: "2026-08-12T10:00:00Z",
    query_window_start: "2026-08-12T09:00:00Z",
    query_window_end: "2026-08-12T10:00:00Z",
    query_hash: "b".repeat(64),
    operational_classification: "real",
    is_truncated: true,
    omitted_count: 2,
    catalog_version: "v1",
    mapping_version: "v1",
    collector_version: "v1",
    evidence_summary: "A bounded persisted alert reference.",
  },
  {
    id: 32,
    evidence_category: "events",
    evidence_type: "normalized_event",
    canonical_source: "pfsense",
    source_type: "firewall",
    source_health_state: "healthy",
    entity_type: "event",
    entity_id: "9001",
    occurrence_timestamp: null,
    ingestion_timestamp: "2026-08-12T09:30:01Z",
    collection_timestamp: "2026-08-12T10:00:00Z",
    query_window_start: "2026-08-12T09:00:00Z",
    query_window_end: "2026-08-12T10:00:00Z",
    query_hash: "c".repeat(64),
    operational_classification: "real",
    is_truncated: false,
    omitted_count: 0,
    catalog_version: "v1",
    mapping_version: "v1",
    collector_version: "v1",
    evidence_summary: "Read-only event provenance.",
  },
];

function arrange() {
  nistExportUrl.mockImplementation((runId, format) => `/nist/export/${runId}.${format}`);
  loadNistBoundaries.mockResolvedValue({ items: [boundary] });
  loadNistRuns.mockResolvedValue({ items: [run], limit: 25, next_cursor: null });
  loadNistResults.mockResolvedValue({ items: results });
  loadNistEvidence.mockImplementation((_runId, _requirementId, { offset = 0 } = {}) =>
    Promise.resolve({ items: references, total: 30, limit: 25, offset })
  );
  createNistBoundary.mockResolvedValue(boundary);
  updateNistBoundary.mockResolvedValue(boundary);
  startNistAssessment.mockResolvedValue(run);
}

beforeEach(() => {
  jest.clearAllMocks();
  arrange();
  window.confirm = jest.fn(() => true);
});

test("renders persisted workspace, exact three-dimensional statuses, provenance, and bounded exports", async () => {
  const onOpenAlert = jest.fn();
  render(<NistEvidenceWorkspace userRole="analyst" onOpenAlert={onOpenAlert} />);

  expect(await screen.findByText("Evidence availability does not determine requirement satisfaction or compliance.")).toBeInTheDocument();
  expect((await screen.findAllByText("Production enclave")).length).toBeGreaterThan(0);
  expect((await screen.findAllByText("Event Logging")).length).toBeGreaterThan(0);
  expect(screen.getAllByText(NIST_STATUS_LABELS.mapping.strong_siem_evidence).length).toBeGreaterThan(0);
  expect(screen.getAllByText(NIST_STATUS_LABELS.evidence.evidence_available).length).toBeGreaterThan(0);
  expect(screen.getAllByText(NIST_STATUS_LABELS.confidence.healthy).length).toBeGreaterThan(0);
  expect(screen.getByText("1 healthy · 11 degraded")).toBeInTheDocument();
  expect(screen.getByText("1 available · 11 partial")).toBeInTheDocument();
  expect(screen.queryByText(/\[object Object\]/)).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Explain this result" })).toBeInTheDocument();
  expect(await screen.findByText("A bounded persisted alert reference.")).toBeInTheDocument();
  await waitFor(() => expect(screen.queryByText("Loading persisted evidence…")).not.toBeInTheDocument());
  expect(screen.queryByText("raw_payload")).not.toBeInTheDocument();
  expect(screen.getByRole("link", { name: "Export JSON" })).toHaveAttribute("href", "/nist/export/11.json");
  expect(screen.queryByRole("button", { name: "Run assessment" })).not.toBeInTheDocument();
  expect(screen.queryByRole("button", { name: "Create boundary" })).not.toBeInTheDocument();
  expect(startNistAssessment).not.toHaveBeenCalled();
  expect(queueNistExplanation).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "Open alert" }));
  expect(onOpenAlert).toHaveBeenCalledWith(501);
  expect(screen.queryByRole("button", { name: "Open event" })).not.toBeInTheDocument();

  await userEvent.click(screen.getByRole("button", { name: "Next evidence" }));
  await waitFor(() => expect(loadNistEvidence).toHaveBeenLastCalledWith(11, "03.03.01", { limit: 25, offset: 25 }));
  expect(await screen.findByText("26–30 of 30")).toBeInTheDocument();
});

test("admin boundary and assessment controls are explicit and never run on page load", async () => {
  render(<NistEvidenceWorkspace userRole="super_admin" />);
  expect(await screen.findByRole("button", { name: "Run assessment" })).toBeInTheDocument();
  await screen.findByText("A bounded persisted alert reference.");
  await waitFor(() => expect(screen.queryByText("Loading persisted evidence…")).not.toBeInTheDocument());
  expect(startNistAssessment).not.toHaveBeenCalled();

  await userEvent.click(screen.getByRole("button", { name: "Create boundary" }));
  expect(screen.getByRole("dialog", { name: "Create assessment boundary" })).toBeInTheDocument();
  expect(screen.getByLabelText("Name")).toHaveFocus();
  await userEvent.click(screen.getByRole("button", { name: "Cancel" }));

  await userEvent.click(screen.getByRole("button", { name: "Run assessment" }));
  expect(window.confirm).toHaveBeenCalled();
  await waitFor(() => expect(startNistAssessment).toHaveBeenCalledWith(7));
  await waitFor(() => expect(screen.getByRole("button", { name: "Run assessment" })).toBeEnabled());
});

test("explanation uses async lifecycle and renders only successful grounded prose", async () => {
  queueNistExplanation.mockResolvedValue({ request_id: "aiwf_nist_test", status: "queued" });
  getNistExplanationRequest.mockResolvedValue({
    status: "completed",
    terminal: true,
    result: {
      binding: { boundary_id: 7, run_id: 11, requirement_result_id: 20, requirement_id: "03.03.01" },
      explanation_status: "available",
      explanation: {
        summary: "The persisted alert supports the deterministic evidence package.",
        why_it_matters: "It identifies the referenced SIEM-visible record.",
        limitations: "Only the bounded supplied references are described.",
        additional_evidence_needed: ["Review evidence outside SIEM visibility."],
        citation_ids: [31],
      },
    },
  });
  render(<NistEvidenceWorkspace userRole="analyst" />);
  await screen.findAllByText("Event Logging");
  await screen.findByText("A bounded persisted alert reference.");
  await waitFor(() => expect(screen.queryByText("Loading persisted evidence…")).not.toBeInTheDocument());

  await userEvent.click(screen.getByRole("button", { name: "Explain this result" }));
  expect(await screen.findByText("The persisted alert supports the deterministic evidence package.")).toBeInTheDocument();
  expect(queueNistExplanation).toHaveBeenCalledWith(expect.objectContaining({
    boundary_id: 7,
    run_id: 11,
    requirement_result_id: 20,
    requirement_id: "03.03.01",
    client_request_id: expect.any(String),
  }));
});

test("provider failure leaves deterministic detail visible and stale selection discards queued response", async () => {
  let resolveQueue;
  queueNistExplanation.mockReturnValue(new Promise((resolve) => { resolveQueue = resolve; }));
  render(<NistEvidenceWorkspace userRole="analyst" />);
  await screen.findAllByText("Event Logging");
  await screen.findByText("A bounded persisted alert reference.");
  await waitFor(() => expect(screen.queryByText("Loading persisted evidence…")).not.toBeInTheDocument());

  await userEvent.click(screen.getByRole("button", { name: "Explain this result" }));
  expect(screen.getByText("Queued…")).toBeInTheDocument();
  await userEvent.click(screen.getByRole("button", { name: /03\.03\.02/i }));
  expect((await screen.findAllByText("Audit Record Content")).length).toBeGreaterThan(0);
  await waitFor(() => expect(loadNistEvidence).toHaveBeenLastCalledWith(11, "03.03.02", { limit: 25, offset: 0 }));
  await waitFor(() => expect(screen.queryByText("Loading persisted evidence…")).not.toBeInTheDocument());
  expect(screen.getByRole("heading", { name: "Audit Record Content" })).toHaveFocus();
  expect(screen.getAllByText(NIST_STATUS_LABELS.confidence.degraded).length).toBeGreaterThan(0);

  await act(async () => { resolveQueue({ request_id: "aiwf_stale" }); });
  expect(getNistExplanationRequest).not.toHaveBeenCalled();
  expect(screen.getByText("Collection degradation limits absence interpretation.")).toBeInTheDocument();

  queueNistExplanation.mockResolvedValue({ request_id: "aiwf_unavailable" });
  getNistExplanationRequest.mockResolvedValue({
    status: "degraded",
    terminal: true,
    result: { explanation_status: "unavailable", explanation: null },
  });
  await userEvent.click(screen.getByRole("button", { name: "Explain this result" }));
  expect(await screen.findByText("Explanation unavailable")).toBeInTheDocument();
  expect(screen.getByText("Collection degradation limits absence interpretation.")).toBeInTheDocument();
});

test("initial error is retryable and an empty persisted workspace remains usable", async () => {
  loadNistBoundaries.mockRejectedValueOnce(new Error("Boundary service unavailable"));
  render(<NistEvidenceWorkspace userRole="analyst" />);
  expect(await screen.findByRole("alert")).toHaveTextContent("Boundary service unavailable");

  loadNistBoundaries.mockResolvedValueOnce({ items: [] });
  await userEvent.click(screen.getByRole("button", { name: "Retry" }));
  expect(await screen.findByText("No active assessment boundaries are available.")).toBeInTheDocument();
  expect(startNistAssessment).not.toHaveBeenCalled();
  expect(queueNistExplanation).not.toHaveBeenCalled();
});

test("polling exposes running state before a grounded terminal response", async () => {
  queueNistExplanation.mockResolvedValue({ request_id: "aiwf_running" });
  getNistExplanationRequest
    .mockResolvedValueOnce({ status: "running", terminal: false })
    .mockResolvedValueOnce({
      status: "completed",
      terminal: true,
      result: {
        binding: { boundary_id: 7, run_id: 11, requirement_result_id: 20, requirement_id: "03.03.01" },
        explanation_status: "available",
        explanation: {
          summary: "Bounded explanation complete.",
          why_it_matters: "It describes the selected persisted evidence.",
          limitations: "Only supplied references are covered.",
          additional_evidence_needed: [],
          citation_ids: [31],
        },
      },
    });
  render(<NistEvidenceWorkspace userRole="analyst" />);
  await screen.findAllByText("Event Logging");
  await screen.findByText("A bounded persisted alert reference.");
  await waitFor(() => expect(screen.queryByText("Loading persisted evidence…")).not.toBeInTheDocument());
  await userEvent.click(screen.getByRole("button", { name: "Explain this result" }));
  expect(await screen.findByText("Running…")).toBeInTheDocument();
  expect(await screen.findByText("Bounded explanation complete.", {}, { timeout: 3000 })).toBeInTheDocument();
});
