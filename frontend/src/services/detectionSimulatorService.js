import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";
import { SIMULATOR_STAGE_DEFINITIONS } from "../utils/detectionSimulatorStages";

export const loadSimulatorRules = async () => {
  const res = await fetch(buildSiemPath("/detection-simulator/rules"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load detection rules", ["error"]));
  }
  if (!data || !Array.isArray(data.rules)) {
    throw new Error("Invalid detection rules response");
  }

  return data.rules;
};

const isValidSimulationResponse = (data) => {
  if (!data || typeof data !== "object" || Array.isArray(data)) return false;
  if (data.simulated !== true) return false;
  if (!data.stages || typeof data.stages !== "object") return false;
  return SIMULATOR_STAGE_DEFINITIONS.every((stageDef) => {
    const stage = data.stages[stageDef.id];
    return !!stage && typeof stage === "object" && typeof stage.status === "string";
  });
};

// This function only sends the analyst's exact selections to the backend and
// renders whatever comes back. It performs no parsing, no threshold
// evaluation, and no detection logic of its own.
export const runDetectionSimulation = async (payload) => {
  const res = await fetch(buildSiemPath("/detection-simulator/run"), {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: JSON.stringify(payload),
  });
  const data = await parseJsonResponse(res, {});

  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to run simulation", ["error"]));
  }
  if (!isValidSimulationResponse(data)) {
    throw new Error("Invalid simulation response");
  }

  return data;
};
