import {
  loadNistEvidence,
  loadNistRuns,
  queueNistExplanation,
} from "./nistEvidenceService";

function response(payload, ok = true) {
  return Promise.resolve({ ok, status: ok ? 200 : 400, json: () => Promise.resolve(payload) });
}

beforeEach(() => {
  global.fetch = jest.fn(() => response({}));
});

afterEach(() => {
  delete global.fetch;
});

test("run history uses bounded keyset query parameters", async () => {
  await loadNistRuns(7, {
    limit: 25,
    cursor: { before_created_at: "2026-08-12T10:00:00Z", before_id: 11 },
  });
  expect(fetch).toHaveBeenCalledWith(
    "/nist/evidence/boundaries/7/runs?limit=25&before_created_at=2026-08-12T10%3A00%3A00Z&before_id=11",
    expect.objectContaining({ credentials: "include", method: "GET" })
  );
});

test("evidence drill-down is explicitly paginated", async () => {
  await loadNistEvidence(11, "03.03.01", { limit: 25, offset: 50 });
  expect(fetch).toHaveBeenCalledWith(
    "/nist/evidence/runs/11/results/03.03.01/evidence?limit=25&offset=50",
    expect.objectContaining({ credentials: "include" })
  );
});

test("explanation submission sends only the caller-provided immutable binding IDs", async () => {
  const payload = {
    boundary_id: 7,
    run_id: 11,
    requirement_result_id: 20,
    requirement_id: "03.03.01",
    client_request_id: "55f5fa58-9dc3-4dda-b880-d950bcf56c62",
  };
  await queueNistExplanation(payload);
  expect(fetch).toHaveBeenCalledWith(
    "/nist/evidence/explanations",
    expect.objectContaining({
      method: "POST",
      credentials: "include",
      body: JSON.stringify(payload),
    })
  );
});
