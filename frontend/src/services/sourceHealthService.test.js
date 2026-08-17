import { loadSourceHealth, loadSourceHealthMetrics } from "./sourceHealthService";
import { SOURCE_METADATA } from "../utils/sourceMetadata";

const responsePayload = {
  generated_at: "2026-07-12T15:00:00+00:00",
  windows: { last_hour_start: "2026-07-12T14:00:00+00:00", today_start: "2026-07-12T00:00:00+00:00", timezone: "UTC" },
  sources: SOURCE_METADATA.map((item) => ({
    source: item.source,
    source_type: item.sourceType,
    display_label: item.displayLabel,
    ingestion_mode: item.source === "azure_insights" ? "checkpoint" : "push",
    health_status: "unknown",
    health_basis: item.source === "azure_insights" ? "poll_checkpoint" : "event_ingestion_freshness",
    health_reason: item.source === "azure_insights" ? "checkpoint_missing" : "historical_backfill_incomplete",
    freshness_threshold_seconds: 900,
    health_basis_age_seconds: null,
    last_event_at: null,
    latest_ingestion_at: null,
    ever_seen: false,
    historical_backfill_complete: item.source === "azure_insights" ? null : false,
  })),
};

const metricsPayload = {
  generated_at: responsePayload.generated_at,
  cache_ttl_seconds: 300,
  windows: responsePayload.windows,
  sources: SOURCE_METADATA.map((item) => ({
    source: item.source,
    events_last_hour: 12,
    events_today: 345,
    total_events: item.source === "pfsense" ? 5873421 : 678,
  })),
};

beforeEach(() => { global.fetch = jest.fn(); });

test("loads and validates the authoritative source health contract", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => responsePayload });
  await expect(loadSourceHealth()).resolves.toEqual(responsePayload);
  expect(fetch).toHaveBeenCalledWith("/source-health", { credentials: "include" });
});

test("rejects malformed or reordered source responses", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ ...responsePayload, sources: responsePayload.sources.slice().reverse() }) });
  await expect(loadSourceHealth()).rejects.toThrow("Invalid source activity response");
});

test("rejects responses without authoritative UTC window boundaries", async () => {
  const payload = { ...responsePayload, windows: { ...responsePayload.windows } };
  delete payload.windows.today_start;
  global.fetch.mockResolvedValue({ ok: true, json: async () => payload });
  await expect(loadSourceHealth()).rejects.toThrow("Invalid source activity response");
});

test("uses existing API error conventions", async () => {
  fetch.mockResolvedValue({ ok: false, json: async () => ({ error: "forbidden" }) });
  await expect(loadSourceHealth()).rejects.toThrow("forbidden");
});

test("loads and validates independently cached source event metrics", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => metricsPayload });
  await expect(loadSourceHealthMetrics()).resolves.toEqual(metricsPayload);
  expect(fetch).toHaveBeenCalledWith("/source-health/metrics", { credentials: "include" });
});

test("rejects malformed, reordered, or unsafe source event counts", async () => {
  const malformed = {
    ...metricsPayload,
    sources: metricsPayload.sources.map((item, index) => (
      index === 0 ? { ...item, total_events: Number.MAX_SAFE_INTEGER + 1 } : item
    )),
  };
  fetch.mockResolvedValue({ ok: true, json: async () => malformed });
  await expect(loadSourceHealthMetrics()).rejects.toThrow("Invalid source event metrics response");
});
