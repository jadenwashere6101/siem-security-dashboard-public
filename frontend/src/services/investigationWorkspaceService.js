import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

async function requestJson(path, { method = "GET", body } = {}) {
  const options = {
    method,
    credentials: "include",
    headers: body ? { "Content-Type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  };
  const res = await fetch(buildSiemPath(path), options);
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to update investigation workspace", ["error", "message"]));
  }
  return data;
}

export function loadAnalystWorkspace() {
  return requestJson("/analyst-workspace");
}

export function pinWorkspaceItem(payload) {
  return requestJson("/analyst-workspace/pins", { method: "POST", body: payload });
}

export function removeWorkspacePin(itemId) {
  return requestJson(`/analyst-workspace/pins/${itemId}`, { method: "DELETE" });
}

export function updateWorkspacePin(itemId, updates) {
  return requestJson(`/analyst-workspace/pins/${itemId}`, { method: "PATCH", body: updates });
}

export function reorderWorkspacePins(orderedItemIds, workspaceId = null) {
  return requestJson("/analyst-workspace/pins/reorder", {
    method: "POST",
    body: { ordered_item_ids: orderedItemIds || [], workspace_id: workspaceId },
  });
}

export function createInvestigation(payload) {
  return requestJson("/investigations", { method: "POST", body: payload });
}

export function updateInvestigation(investigationId, updates) {
  return requestJson(`/investigations/${investigationId}`, { method: "PATCH", body: updates });
}

export function createWorkspaceNote(payload) {
  return requestJson("/analyst-workspace/notes", { method: "POST", body: payload });
}

export function updateWorkspaceNote(noteId, updates) {
  return requestJson(`/analyst-workspace/notes/${noteId}`, { method: "PATCH", body: updates });
}

export function deleteWorkspaceNote(noteId) {
  return requestJson(`/analyst-workspace/notes/${noteId}`, { method: "DELETE" });
}

export function createWorkspaceHypothesis(payload) {
  return requestJson("/analyst-workspace/hypotheses", { method: "POST", body: payload });
}

export function updateWorkspaceHypothesis(hypothesisId, updates) {
  return requestJson(`/analyst-workspace/hypotheses/${hypothesisId}`, { method: "PATCH", body: updates });
}

export function deleteWorkspaceHypothesis(hypothesisId) {
  return requestJson(`/analyst-workspace/hypotheses/${hypothesisId}`, { method: "DELETE" });
}

export function createWorkspaceTask(payload) {
  return requestJson("/analyst-workspace/tasks", { method: "POST", body: payload });
}

export function updateWorkspaceTask(taskId, updates) {
  return requestJson(`/analyst-workspace/tasks/${taskId}`, { method: "PATCH", body: updates });
}

export function deleteWorkspaceTask(taskId) {
  return requestJson(`/analyst-workspace/tasks/${taskId}`, { method: "DELETE" });
}

export function createEvidenceReference(payload) {
  return requestJson("/analyst-workspace/evidence", { method: "POST", body: payload });
}

export function updateEvidenceReference(evidenceId, updates) {
  return requestJson(`/analyst-workspace/evidence/${evidenceId}`, { method: "PATCH", body: updates });
}

export function deleteEvidenceReference(evidenceId) {
  return requestJson(`/analyst-workspace/evidence/${evidenceId}`, { method: "DELETE" });
}
