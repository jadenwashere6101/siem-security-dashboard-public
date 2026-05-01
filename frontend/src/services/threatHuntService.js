import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";

export const searchThreatHuntEvents = async ({
  sourceIpValue,
  sourceValue,
  eventTypeValue,
  startTimeValue,
  endTimeValue,
}) => {
  const params = new URLSearchParams();
  if (sourceIpValue.trim()) params.set("source_ip", sourceIpValue.trim());
  if (sourceValue) params.set("source", sourceValue);
  if (eventTypeValue) params.set("event_type", eventTypeValue);
  if (startTimeValue) params.set("start_time", new Date(startTimeValue).toISOString());
  if (endTimeValue) params.set("end_time", new Date(endTimeValue).toISOString());

  const searchPath = params.toString()
    ? `${buildSiemPath("/events/search")}?${params.toString()}`
    : buildSiemPath("/events/search");

  const res = await fetch(searchPath, {
    credentials: "include",
  });
  const data = await parseJsonResponse(res, []);

  if (!res.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to search events", ["error"]));
  }

  return data;
};
