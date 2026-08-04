import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

const requestJson = async (options = {}) => {
  const response = await fetch(buildSiemPath("/admin/ai-gateway-config"), {
    credentials: "include",
    ...options,
  });
  const data = await parseJsonResponse(response, {});
  if (!response.ok) {
    throw new Error(
      getApiErrorMessage(data, "Unable to access AI gateway configuration", ["error"])
    );
  }
  return data;
};

export const loadAiGatewayConfig = () => requestJson();

export const updateAiGatewayConfig = (configuration) =>
  requestJson({
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(configuration),
  });
