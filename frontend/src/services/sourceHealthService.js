import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";
import { SOURCE_METADATA } from "../utils/sourceMetadata";

const REQUIRED_SOURCE_FIELDS = [
  "source",
  "source_type",
  "display_label",
  "ingestion_mode",
  "health_status",
  "health_basis",
  "health_reason",
  "freshness_threshold_seconds",
  "health_basis_age_seconds",
  "last_event_at",
  "latest_ingestion_at",
  "ever_seen",
  "historical_backfill_complete",
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
      ["push", "checkpoint"].includes(item.ingestion_mode) &&
      ["healthy", "degraded", "unknown"].includes(item.health_status) &&
      typeof item.health_basis === "string" &&
      typeof item.health_reason === "string" &&
      Number.isInteger(item.freshness_threshold_seconds) &&
      item.freshness_threshold_seconds > 0 &&
      (item.health_basis_age_seconds === null || Number.isInteger(item.health_basis_age_seconds)) &&
      (item.last_event_at === null || typeof item.last_event_at === "string") &&
      (item.latest_ingestion_at === null || typeof item.latest_ingestion_at === "string") &&
      typeof item.ever_seen === "boolean" &&
      (item.historical_backfill_complete === null || typeof item.historical_backfill_complete === "boolean");
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
