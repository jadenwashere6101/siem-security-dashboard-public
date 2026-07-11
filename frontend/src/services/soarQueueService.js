import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const loadSoarQueueStatus = async () => {
  const res = await fetch(buildSiemPath("/admin/soar/queue/status"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load SOAR queue status", ["error"])
    );
  }

  return data;
};

export const loadRecentSoarQueueItems = async ({ limit = 50, status } = {}) => {
  const params = new URLSearchParams();
  if (limit) params.set("limit", String(limit));
  if (status && status !== "all") params.set("status", status);

  const query = params.toString();
  const res = await fetch(
    buildSiemPath(`/admin/soar/queue/recent${query ? `?${query}` : ""}`),
    {
      credentials: "include",
    }
  );
  const data = await parseJsonResponse(res, { items: [] });

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load SOAR queue items", ["error"])
    );
  }

  return data;
};

export const loadSoarQueueItem = async (queueId) => {
  const res = await fetch(buildSiemPath(`/admin/soar/queue/${queueId}`), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to load SOAR queue item", ["error"])
    );
  }

  return data;
};

export const runSoarWorkerOnce = async ({ batchSize } = {}) => {
  const body = {};
  if (batchSize !== undefined && batchSize !== null) {
    body.batch_size = batchSize;
  }

  const res = await fetch(buildSiemPath("/admin/soar/worker/run-once"), {
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
      getApiErrorMessage(data, "Unable to process SOAR queue batch", ["error"])
    );
  }

  return data;
};
