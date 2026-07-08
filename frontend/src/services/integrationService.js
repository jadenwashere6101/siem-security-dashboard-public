import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const circuitControlErrorFields = ["message", "error"];

async function postCircuitControl(pathSuffix, body) {
  const res = await fetch(buildSiemPath(pathSuffix), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Circuit breaker control failed", circuitControlErrorFields)
    );
  }
  return data;
}

export async function getIntegrationStatus() {
  const res = await fetch(buildSiemPath("/integrations/status"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load integration status", ["error", "message"])
    );
  }
  return data;
}

export async function getNotificationReadiness() {
  const res = await fetch(buildSiemPath("/integrations/notification-readiness"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load notification readiness", ["error", "message"])
    );
  }
  return data;
}

export async function sendNotificationTest(adapterName) {
  const name = String(adapterName || "").trim();
  const res = await fetch(buildSiemPath(`/integrations/${encodeURIComponent(name)}/test-send`), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify({}),
  });
  const data = await parseJsonResponse(res, {});
  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Notification test failed", ["message", "error"])
    );
  }
  return data;
}

export async function resetIntegrationCircuitBreaker(adapterName, reason) {
  const name = String(adapterName || "").trim();
  return postCircuitControl(`/integrations/${encodeURIComponent(name)}/circuit-breaker/reset`, {
    reason,
  });
}

export async function forceOpenIntegrationCircuitBreaker(adapterName, reason) {
  const name = String(adapterName || "").trim();
  return postCircuitControl(
    `/integrations/${encodeURIComponent(name)}/circuit-breaker/force-open`,
    { reason }
  );
}

export async function enableHalfOpenIntegrationCircuitBreaker(
  adapterName,
  reason,
  overrideCooldown = false
) {
  const name = String(adapterName || "").trim();
  return postCircuitControl(
    `/integrations/${encodeURIComponent(name)}/circuit-breaker/enable-half-open`,
    {
      reason,
      override_cooldown: Boolean(overrideCooldown),
    }
  );
}
