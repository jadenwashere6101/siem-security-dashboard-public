import { loadSeverityResponseMatrix } from "./severityResponseMatrixService";

beforeEach(() => {
  global.fetch = jest.fn();
});

test("loads severity response matrix with credentials", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ rules: [] }) });
  await loadSeverityResponseMatrix();
  expect(fetch).toHaveBeenCalledWith(
    "/api/severity-response-matrix",
    expect.objectContaining({ credentials: "include" })
  );
});

test("surfaces backend matrix errors", async () => {
  fetch.mockResolvedValue({ ok: false, json: async () => ({ error: "forbidden" }) });
  await expect(loadSeverityResponseMatrix()).rejects.toThrow("forbidden");
});
