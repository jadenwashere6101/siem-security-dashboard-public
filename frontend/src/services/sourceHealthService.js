import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";
import { SOURCE_METADATA } from "../utils/sourceMetadata";

const REQUIRED_SOURCE_FIELDS = [
  "source",
  "source_type",
  "display_label",
  "last_event_at",
  "events_last_hour",
  "events_today",
  "total_events",
  "ever_seen",
];

export const isValidSourceHealthResponse = (data) => {
  if (!data || typeof data !== "object" || Array.isArray(data)) return false;
  if (typeof data.generated_at !== "string" || !data.windows || !Array.isArray(data.sources)) return false;
  if (
    data.windows.timezone !== "UTC" ||
    typeof data.windows.last_hour_start !== "string" ||
    typeof data.windows.today_start !== "string" ||
    data.sources.length !== SOURCE_METADATA.length
  ) return false;

  return data.sources.every((item, index) => {
    const expected = SOURCE_METADATA[index];
    if (!item || typeof item !== "object") return false;
    if (!REQUIRED_SOURCE_FIELDS.every((field) => Object.prototype.hasOwnProperty.call(item, field))) return false;
    return item.source === expected.source &&
      item.source_type === expected.sourceType &&
      item.display_label === expected.displayLabel &&
      (item.last_event_at === null || typeof item.last_event_at === "string") &&
      [item.events_last_hour, item.events_today, item.total_events].every(
        (value) => Number.isInteger(value) && value >= 0
      ) &&
      typeof item.ever_seen === "boolean";
  });
};

export const loadSourceHealth = async () => {
  const response = await fetch(buildSiemPath("/source-health"), {
    credentials: "include",
  });
  const data = await parseJsonResponse(response, {});
  if (!response.ok) {
    throw new Error(getApiErrorMessage(data, "Unable to load source activity", ["error"]));
  }
  if (!isValidSourceHealthResponse(data)) {
    throw new Error("Invalid source activity response");
  }
  return data;
};
