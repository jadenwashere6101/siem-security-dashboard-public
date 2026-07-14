import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadDetectionRules = async () => {
  const res = await fetch(buildSiemPath("/admin/detection-rules"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, []);

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load detection rules", ["error"])
    );
  }

  return data;
};

export const loadPfsenseDetectionHealth = async ({ operationalScope } = {}) => {
  const params = new URLSearchParams();
  if (operationalScope && operationalScope !== "all_history") {
    params.set("operational_scope", operationalScope);
  }
  const query = params.toString();
  const res = await fetch(buildSiemPath(`/admin/detection-rules/pfsense-health${query ? `?${query}` : ""}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, []);

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load pfSense detection health", ["error"])
    );
  }

  return data;
};

export const updateDetectionRule = async (ruleId, parameters, active) => {
  const payload = {};
  if (parameters !== undefined) {
    payload.parameters = parameters;
  }
  if (active !== undefined) {
    payload.active = active;
  }

  const res = await fetch(buildSiemPath(`/admin/detection-rules/${encodeURIComponent(ruleId)}`), {
    method: "PATCH",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to update detection rule", ["error"])
    );
  }

  return data;
};
