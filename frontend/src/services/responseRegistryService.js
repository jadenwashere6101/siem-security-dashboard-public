import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const REGISTRY_VIEWS = [
  { id: "all", label: "All" },
  { id: "monitoring", label: "Monitoring" },
  { id: "blocklist_tracking", label: "Blocklist Tracking" },
  { id: "escalated", label: "Escalated" },
  { id: "pending", label: "Pending" },
  { id: "failed_rejected", label: "Failed/Rejected" },
  { id: "history", label: "History" },
];

export const loadRegistryRecords = async ({
  view = "all",
  q,
  exactIndicator,
  disposition,
  dispositions,
  origin,
  outcome,
  enforcement,
  requestedAction,
  actorUserId,
  relatedAlertId,
  relatedIncidentId,
  updatedAfter,
  updatedBefore,
  sort = "updated_at_desc",
  limit = 50,
  offset = 0,
} = {}) => {
  const params = new URLSearchParams();
  if (view) params.set("view", view);
  if (q) params.set("q", q);
  if (exactIndicator) params.set("exact_indicator", exactIndicator);
  if (disposition && disposition !== "all") params.set("disposition", disposition);
  if (dispositions) params.set("dispositions", dispositions);
  if (origin) params.set("origin", origin);
  if (outcome) params.set("outcome", outcome);
  if (enforcement) params.set("enforcement", enforcement);
  if (requestedAction) params.set("requested_action", requestedAction);
  if (actorUserId) params.set("actor_user_id", String(actorUserId));
  if (relatedAlertId) params.set("related_alert_id", String(relatedAlertId));
  if (relatedIncidentId) params.set("related_incident_id", String(relatedIncidentId));
  if (updatedAfter) params.set("updated_after", updatedAfter);
  if (updatedBefore) params.set("updated_before", updatedBefore);
  if (sort) params.set("sort", sort);
  if (limit && limit !== 50) params.set("limit", String(limit));
  if (offset) params.set("offset", String(offset));

  const query = params.toString();
  const res = await fetch(
    buildSiemPath(`/response-registry${query ? `?${query}` : ""}`),
    { credentials: "include" }
  );
  const data = await parseJsonResponse(res, { items: [], total: 0 });

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load response registry", ["error", "message"])
    );
  }

  return data;
};

export const loadRegistryDetail = async (registryId) => {
  const res = await fetch(buildSiemPath(`/response-registry/${registryId}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load registry detail", ["error", "message"])
    );
  }

  return data;
};

export const executeRegistryCommand = async ({
  action,
  indicatorValue,
  reason,
  expiresAt,
  alertId,
  incidentId,
  playbookExecutionId,
  approvalRequestId,
  idempotencyKey,
}) => {
  const res = await fetch(buildSiemPath("/response-registry/commands"), {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      action,
      indicator_value: indicatorValue,
      reason,
      expires_at: expiresAt || null,
      alert_id: alertId || null,
      incident_id: incidentId || null,
      playbook_execution_id: playbookExecutionId || null,
      approval_request_id: approvalRequestId || null,
      idempotency_key: idempotencyKey || null,
    }),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(
        data,
        data.message || "Unable to execute registry command",
        ["error", "message"]
      )
    );
  }

  return data;
};
