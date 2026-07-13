import { loadSoarOperationsSummary } from "./soarOperationsService";

global.fetch = jest.fn();

beforeEach(() => {
  fetch.mockReset();
});

test("loads SOAR operations summary", async () => {
  fetch.mockResolvedValue({
    ok: true,
    json: () =>
      Promise.resolve({
        counts: { active_playbooks: 2 },
        running_playbooks: { count: 2, items: [] },
      }),
  });

  const data = await loadSoarOperationsSummary();

  expect(fetch).toHaveBeenCalledWith("/metrics/soar-operations", {
    credentials: "include",
  });
  expect(data.counts.active_playbooks).toBe(2);
});

test("throws friendly error when summary request fails", async () => {
  fetch.mockResolvedValue({
    ok: false,
    json: () => Promise.resolve({ error: "summary unavailable" }),
  });

  await expect(loadSoarOperationsSummary()).rejects.toThrow("summary unavailable");
});
