import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import AnalystWorkspace from "./AnalystWorkspace";

const longToken = "very-long-investigation-token-without-natural-breaks-".repeat(4);

const workspaceState = {
  workspace: { id: 1, visibility: "private" },
  items: [{ id: 4, item_type: "alert", referenced_object_type: "alert", referenced_object_id: "7", label: `Alert #7 ${longToken}` }],
  investigations: [
    {
      id: 8,
      title: "Credential spray review",
      status: "investigating",
      linked_alert_id: 7,
      linked_source_ip: "203.0.113.7",
      confidence: "medium",
      disposition: "undetermined",
      summary: "Multiple failed logins from one source.",
      conclusion: "",
      last_activity_at: "2026-07-29T20:05:00Z",
    },
    {
      id: 9,
      title: "Older private investigation",
      status: "open",
      confidence: "low",
      disposition: "needs_monitoring",
    },
  ],
  notes: [{ id: 1, body: `Unassigned note ${longToken}` }],
  hypotheses: [{ id: 2, title: `Unassigned hypothesis ${longToken}`, status: "open" }],
  tasks: [{ id: 3, title: `Unassigned task ${longToken}`, status: "open" }],
  evidence: [{ id: 5, label: "Unassigned evidence", referenced_object_type: "alert", referenced_object_id: "7" }],
};

const activeInvestigationBundle = {
  workspace: { id: 1, visibility: "private" },
  investigation: workspaceState.investigations[0],
  source_context: {
    alert: {
      id: 7,
      alert_type: "failed_login_threshold",
      severity: "HIGH",
      source_ip: "203.0.113.7",
      message: "failed login burst",
      created_at: "2026-07-29T20:00:00Z",
    },
    incident: null,
    source_ip: "203.0.113.7",
    partial: [],
  },
  notes: [{ id: 10, body: `Check login source ${longToken}` }],
  hypotheses: [
    { id: 20, title: `Likely password spray ${longToken}`, status: "open", confidence: "medium" },
  ],
  tasks: [
    { id: 30, title: `Review MFA logs ${longToken}`, status: "open", hypothesis_id: 20, evidence_reference_id: 40 },
  ],
  evidence: [
    {
      id: 40,
      label: "Primary alert",
      referenced_object_type: "alert",
      referenced_object_id: "7",
      source: "investigation_drawer",
      rationale: "Primary trigger for this investigation.",
      relationship_type: "context",
      created_at: "2026-07-29T20:01:00Z",
    },
  ],
  hypothesis_evidence: [
    {
      id: 50,
      investigation_id: 8,
      hypothesis_id: 20,
      evidence_reference_id: 40,
      relationship_type: "supports",
      rationale: "Matches the failed login pattern.",
    },
  ],
  timeline: [
    { id: "investigation-created-8", kind: "analyst", label: "Investigation created", timestamp: "2026-07-29T20:02:00Z", detail: "Credential spray review" },
  ],
  unassigned: {
    items: workspaceState.items,
    notes: workspaceState.notes,
    hypotheses: workspaceState.hypotheses,
    tasks: workspaceState.tasks,
    evidence: workspaceState.evidence,
  },
};

test("AnalystWorkspace centers the active investigation and keeps legacy content secondary", async () => {
  const onSelectInvestigation = jest.fn();
  const onUpdateInvestigation = jest.fn();
  const onDeleteInvestigation = jest.fn();
  const onCreateNote = jest.fn();
  const onCreateHypothesis = jest.fn();
  const onCreateTask = jest.fn();
  const onDeleteNote = jest.fn();
  const onDeleteHypothesis = jest.fn();
  const onDeleteTask = jest.fn();
  const onUpdateTask = jest.fn();
  const onUpdateEvidence = jest.fn();
  const onDeleteEvidence = jest.fn();
  const onLinkEvidenceToHypothesis = jest.fn();
  const onUnlinkEvidenceFromHypothesis = jest.fn();
  const onOpenEvidenceSource = jest.fn();

  render(
    <AnalystWorkspace
      workspaceState={workspaceState}
      activeInvestigationBundle={activeInvestigationBundle}
      activeInvestigationId={8}
      onSelectInvestigation={onSelectInvestigation}
      onUpdateInvestigation={onUpdateInvestigation}
      onDeleteInvestigation={onDeleteInvestigation}
      onCreateNote={onCreateNote}
      onCreateHypothesis={onCreateHypothesis}
      onCreateTask={onCreateTask}
      onDeleteNote={onDeleteNote}
      onDeleteHypothesis={onDeleteHypothesis}
      onDeleteTask={onDeleteTask}
      onUpdateTask={onUpdateTask}
      onUpdateEvidence={onUpdateEvidence}
      onDeleteEvidence={onDeleteEvidence}
      onLinkEvidenceToHypothesis={onLinkEvidenceToHypothesis}
      onUnlinkEvidenceFromHypothesis={onUnlinkEvidenceFromHypothesis}
      onOpenEvidenceSource={onOpenEvidenceSource}
    />
  );

  expect(screen.getByRole("heading", { name: "Investigation workspace" })).toBeInTheDocument();
  expect(screen.getByText("Active investigation")).toBeInTheDocument();
  expect(screen.getAllByText("Credential spray review").length).toBeGreaterThan(1);
  expect(screen.getByText(/Source fact/i)).toBeInTheDocument();
  expect(screen.getAllByText(/Analyst-authored/i).length).toBeGreaterThan(1);
  expect(screen.getByText(/Alert #7: failed_login_threshold/i)).toBeInTheDocument();
  expect(screen.getByText(/Disposition is still undetermined/i)).toBeInTheDocument();
  expect(screen.getByText(/1 task still open/i)).toBeInTheDocument();
  expect(screen.getByText("Unassigned workspace content")).toBeInTheDocument();
  expect(screen.getByText(new RegExp(`Check login source ${longToken.slice(0, 24)}`))).toHaveStyle({ overflowWrap: "anywhere" });

  await userEvent.click(screen.getByRole("button", { name: /Older private investigation/i }));
  expect(onSelectInvestigation).toHaveBeenCalledWith(9);

  await userEvent.selectOptions(screen.getByLabelText("Status"), "closed");
  await userEvent.selectOptions(screen.getByLabelText("Confidence"), "high");
  await userEvent.selectOptions(screen.getByLabelText("Disposition"), "true_positive");
  await userEvent.clear(screen.getByLabelText("Investigation conclusion"));
  await userEvent.type(screen.getByLabelText("Investigation conclusion"), "Credential spray confirmed.");
  await userEvent.click(screen.getByRole("button", { name: "Save investigation updates" }));
  expect(onUpdateInvestigation).toHaveBeenCalledWith(8, expect.objectContaining({
    status: "closed",
    confidence: "high",
    disposition: "true_positive",
    conclusion: "Credential spray confirmed.",
  }));

  await userEvent.click(screen.getByRole("button", { name: "Open source" }));
  expect(onOpenEvidenceSource).toHaveBeenCalledWith(expect.objectContaining({ id: 40 }));

  await userEvent.clear(screen.getByLabelText("Rationale for Primary alert"));
  await userEvent.type(screen.getByLabelText("Rationale for Primary alert"), "Shows the first known trigger.");
  await userEvent.click(screen.getByRole("button", { name: "Save rationale" }));
  expect(onUpdateEvidence).toHaveBeenCalledWith(40, expect.objectContaining({ rationale: "Shows the first known trigger." }));

  await userEvent.click(screen.getByRole("button", { name: "Unlink" }));
  expect(onUnlinkEvidenceFromHypothesis).toHaveBeenCalledWith(50);

  await userEvent.click(screen.getByRole("button", { name: "Link evidence" }));
  expect(onLinkEvidenceToHypothesis).toHaveBeenCalledWith(8, expect.objectContaining({
    hypothesis_id: 20,
    evidence_reference_id: 40,
    relationship_type: "supports",
  }));

  await userEvent.click(screen.getByRole("button", { name: "Complete" }));
  expect(onUpdateTask).toHaveBeenCalledWith(30, { status: "done" });

  await userEvent.click(screen.getByRole("button", { name: "Delete investigation" }));
  expect(onDeleteInvestigation).toHaveBeenCalledWith(8);
  await userEvent.click(screen.getByRole("button", { name: "Delete hypothesis" }));
  expect(onDeleteHypothesis).toHaveBeenCalledWith(20);
  await userEvent.click(screen.getByRole("button", { name: "Delete task" }));
  expect(onDeleteTask).toHaveBeenCalledWith(30);
  await userEvent.click(screen.getByRole("button", { name: "Delete note" }));
  expect(onDeleteNote).toHaveBeenCalledWith(10);
});

test("AnalystWorkspace creates investigation-scoped notes, hypotheses, and tasks", async () => {
  const onCreateNote = jest.fn();
  const onCreateHypothesis = jest.fn();
  const onCreateTask = jest.fn();

  render(
    <AnalystWorkspace
      workspaceState={workspaceState}
      activeInvestigationBundle={activeInvestigationBundle}
      activeInvestigationId={8}
      onCreateNote={onCreateNote}
      onCreateHypothesis={onCreateHypothesis}
      onCreateTask={onCreateTask}
    />
  );

  await userEvent.type(screen.getByLabelText("New note"), "New investigation note");
  await userEvent.click(screen.getByRole("button", { name: "Add note" }));
  expect(onCreateNote).toHaveBeenCalledWith({ investigation_id: 8, body: "New investigation note" });

  await userEvent.type(screen.getByLabelText("New hypothesis"), "New investigation hypothesis");
  await userEvent.click(screen.getByRole("button", { name: "Add hypothesis" }));
  expect(onCreateHypothesis).toHaveBeenCalledWith({ investigation_id: 8, title: "New investigation hypothesis", confidence: "medium" });

  await userEvent.selectOptions(screen.getByLabelText("Task hypothesis"), "20");
  await userEvent.selectOptions(screen.getByLabelText("Task evidence"), "40");
  await userEvent.type(screen.getByLabelText("New task"), "New investigation task");
  await userEvent.click(screen.getByRole("button", { name: "Add task" }));
  expect(onCreateTask).toHaveBeenCalledWith({
    investigation_id: 8,
    title: "New investigation task",
    hypothesis_id: 20,
    evidence_reference_id: 40,
  });
});

test("AnalystWorkspace empty state guides analysts to start from source context", () => {
  render(<AnalystWorkspace workspaceState={{ workspace: { visibility: "private" }, items: [], investigations: [], notes: [], hypotheses: [], tasks: [], evidence: [] }} />);
  expect(screen.getByText(/Start from an alert, incident, or source context/i)).toBeInTheDocument();
  expect(screen.getByText(/Saved investigations appear here/i)).toBeInTheDocument();
});

test("AnalystWorkspace renders partial source context explicitly", () => {
  render(
    <AnalystWorkspace
      workspaceState={{ ...workspaceState, investigations: [workspaceState.investigations[0]] }}
      activeInvestigationId={8}
      activeInvestigationBundle={{
        ...activeInvestigationBundle,
        investigation: { ...activeInvestigationBundle.investigation, linked_alert_id: null, linked_incident_id: null, linked_source_ip: null },
        source_context: { alert: null, incident: null, source_ip: null, partial: ["linked alert unavailable"] },
        timeline: [],
      }}
    />
  );
  expect(screen.getByText(/No linked source context is available/i)).toBeInTheDocument();
});
