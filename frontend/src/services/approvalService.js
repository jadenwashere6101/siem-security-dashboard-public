import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const listApprovals = async ({
  status,
  incidentId,
  queueId,
  limit = 50,
  offset = 0,
} = {}) => {
  const params = new URLSearchParams();
  if (status && status !== "all") params.set("status", status);
  if (incidentId !== undefined && incidentId !== null && incidentId !== "") {
    params.set("incident_id", String(incidentId));
  }
  if (queueId !== undefined && queueId !== null && queueId !== "") {
    params.set("queue_id", String(queueId));
  }
  if (limit && limit !== 50) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));

  const query = params.toString();
  const res = await fetch(buildSiemPath(`/approvals${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, { approvals: [], count: 0 });

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load approvals", ["error"])
    );
  }

  return data;
};

export const getApproval = async (approvalId) => {
  const res = await fetch(buildSiemPath(`/approvals/${approvalId}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load approval detail", ["error"])
    );
  }

  return data;
};

export const submitApprovalDecision = async (
  approvalId,
  { decision, reason } = {}
) => {
  const normalizedReason = reason === undefined || reason === null
    ? ""
    : String(reason).trim();

  const res = await fetch(buildSiemPath(`/approvals/${approvalId}/decision`), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ decision, reason: normalizedReason }),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to submit approval decision", ["error"])
    );
  }

  return data;
};
