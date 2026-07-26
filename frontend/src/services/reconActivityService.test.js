import {
  loadReconActivities,
  loadReconActivityAlerts,
} from "./reconActivityService";

beforeEach(() => {
  global.fetch = jest.fn();
});

test("loadReconActivities sends paginated recon filters", async () => {
  global.fetch.mockResolvedValue({
    ok: true,
    json: async () => ({ items: [], total: 0, limit: 20, offset: 40 }),
  });

  await loadReconActivities({
    limit: 20,
    offset: 40,
    status: "open",
    severity: "high",
    confidence: "high",
    classification: "campaign_recon",
    search: "203.0.113.44",
    timeRange: "90d",
    sort: "severity_desc",
  });

  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toContain("/recon-activities?");
  expect(url).toContain("limit=20");
  expect(url).toContain("offset=40");
  expect(url).toContain("status=open");
  expect(url).toContain("severity=high");
  expect(url).toContain("confidence=high");
  expect(url).toContain("classification=campaign_recon");
  expect(url).toContain("search=203.0.113.44");
  expect(url).toContain("time_range=90d");
  expect(url).toContain("sort=severity_desc");
  expect(options).toEqual({ credentials: "include" });
});

test("loadReconActivityAlerts sends bounded linked-alert pagination", async () => {
  global.fetch.mockResolvedValue({
    ok: true,
    json: async () => ({ items: [], total: 14, limit: 10, offset: 10 }),
  });

  await loadReconActivityAlerts(90, { limit: 10, offset: 10, sort: "oldest" });

  const [url, options] = global.fetch.mock.calls[0];
  expect(url).toBe("/recon-activities/90/alerts?limit=10&offset=10&sort=oldest");
  expect(options).toEqual({ credentials: "include" });
});
