import {
  loadPfsenseIngestFilterMetrics,
  loadPfsenseIngestFilters,
  updatePfsenseIngestFilter,
} from "./pfsenseIngestFilterService";

beforeEach(() => {
  global.fetch = jest.fn();
});

test("loads effective policy with credentials", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ categories: {} }) });
  await loadPfsenseIngestFilters();
  expect(fetch).toHaveBeenCalledWith("/admin/pfsense-ingest-filters", expect.objectContaining({ credentials: "include" }));
});

test("loads process-local metrics", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ counts: {} }) });
  await loadPfsenseIngestFilterMetrics();
  expect(fetch).toHaveBeenCalledWith("/admin/pfsense-ingest-filters/metrics", expect.any(Object));
});

test("patches one validated category", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ enabled: true }) });
  await updatePfsenseIngestFilter("dns_traffic", true, {});
  expect(fetch).toHaveBeenCalledWith(
    "/admin/pfsense-ingest-filters/dns_traffic",
    expect.objectContaining({ method: "PATCH", body: JSON.stringify({ enabled: true, parameters: {} }) })
  );
});

test("surfaces safe backend errors", async () => {
  fetch.mockResolvedValue({ ok: false, json: async () => ({ error: "enabled must be a boolean" }) });
  await expect(updatePfsenseIngestFilter("dns_traffic", "yes", {})).rejects.toThrow("enabled must be a boolean");
});
