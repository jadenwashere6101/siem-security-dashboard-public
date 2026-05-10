import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const listFallback = { items: [], limit: 50, enabled: null };
const execListFallback = { items: [], limit: 50, playbook_id: null, status: null };

export async function listPlaybooks({ enabled, limit } = {}) {
  const params = new URLSearchParams();
  if (enabled === true) {
    params.set("enabled", "true");
  } else if (enabled === false) {
    params.set("enabled", "false");
  }
  if (limit !== undefined && limit !== null && limit !== "") {
    params.set("limit", String(limit));
  }
  const query = params.toString();
  const res = await fetch(buildSiemPath(`/playbooks${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, listFallback);
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load playbooks", ["error", "message"])
    );
  }
  return data;
}

export async function getPlaybook(playbookId) {
  const encoded = encodeURIComponent(playbookId);
  const res = await fetch(buildSiemPath(`/playbooks/${encoded}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load playbook definition", ["error", "message"])
    );
  }
  return data;
}

export async function listPlaybookExecutions({ playbookId, status, limit } = {}) {
  const params = new URLSearchParams();
  if (playbookId) {
    params.set("playbook_id", playbookId);
  }
  if (status) {
    params.set("status", status);
  }
  if (limit !== undefined && limit !== null && limit !== "") {
    params.set("limit", String(limit));
  }
  const query = params.toString();
  const res = await fetch(
    buildSiemPath(`/playbook-executions${query ? `?${query}` : ""}`),
    { credentials: "include" }
  );
  const data = await parseJsonResponse(res, execListFallback);
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load playbook executions", ["error", "message"])
    );
  }
  return data;
}

export async function getPlaybookExecution(executionId) {
  const res = await fetch(buildSiemPath(`/playbook-executions/${executionId}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load playbook execution", ["error", "message"])
    );
  }
  return data;
}

export async function createPlaybookDefinition(payload) {
  const res = await fetch(buildSiemPath("/playbooks"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to create playbook definition", ["error", "message"])
    );
  }
  return data;
}

export async function updatePlaybookDefinition(playbookId, payload) {
  const encoded = encodeURIComponent(playbookId);
  const res = await fetch(buildSiemPath(`/playbooks/${encoded}`), {
    method: "PUT",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to update playbook definition", ["error", "message"])
    );
  }
  return data;
}

export async function setPlaybookDefinitionEnabled(playbookId, enabled) {
  const encoded = encodeURIComponent(playbookId);
  const res = await fetch(buildSiemPath(`/playbooks/${encoded}/enabled`), {
    method: "PATCH",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ enabled }),
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to update playbook enabled status", ["error", "message"])
    );
  }
  return data;
}
