import { loadSourceHealth } from "./sourceHealthService";
import { SOURCE_METADATA } from "../utils/sourceMetadata";

const responsePayload = {
  generated_at: "2026-07-12T15:00:00+00:00",
  windows: { last_hour_start: "2026-07-12T14:00:00+00:00", today_start: "2026-07-12T00:00:00+00:00", timezone: "UTC" },
  sources: SOURCE_METADATA.map((item) => ({
    source: item.source,
    source_type: item.sourceType,
    display_label: item.displayLabel,
    last_event_at: null,
    events_last_hour: 0,
    events_today: 0,
    total_events: 0,
    ever_seen: false,
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
