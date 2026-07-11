import { buildAlertTimelineData } from "./alertDashboardData";

test("buildAlertTimelineData preserves UTC-hour bucket meaning, counts, and ordering", () => {
  const result = buildAlertTimelineData([
    { created_at: "2026-07-10T11:45:00Z" },
    { created_at: "2026-07-10T10:30:00Z" },
    { created_at: "2026-07-10T10:05:00Z" },
    { created_at: "invalid" },
  ]);

  expect(result).toEqual([
    { bucketStart: Date.UTC(2026, 6, 10, 10), count: 2 },
    { bucketStart: Date.UTC(2026, 6, 10, 11), count: 1 },
  ]);
  expect(result.every((bucket) => !("time" in bucket))).toBe(true);
});
