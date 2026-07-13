import { loadPfsenseWhyFired } from "./pfsenseAlertInvestigationService";

beforeEach(() => {
  global.fetch = jest.fn();
});

afterEach(() => {
  jest.restoreAllMocks();
});

test("loads why-fired evidence with credentials", async () => {
  const payload = { alert_id: 101, evidence: [] };
  fetch.mockResolvedValue({ ok: true, json: async () => payload });

  await expect(loadPfsenseWhyFired(101)).resolves.toEqual(payload);
  expect(fetch).toHaveBeenCalledWith("/alerts/101/why-fired", {
    credentials: "include",
  });
});
