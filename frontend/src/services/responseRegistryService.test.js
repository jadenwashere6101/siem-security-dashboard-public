import {
  executeRegistryCommand,
  loadRegistryDetail,
  loadRegistryRecords,
} from "./responseRegistryService";
import { buildSiemPath } from "../utils/siemPath";

describe("responseRegistryService", () => {
  beforeEach(() => {
    global.fetch = jest.fn();
  });

  afterEach(() => {
    jest.resetAllMocks();
  });

  test("loadRegistryRecords builds query params", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ items: [], total: 0 }),
    });

    await loadRegistryRecords({
      view: "monitoring",
      q: "1.2.3.4",
      sort: "updated_at_asc",
      limit: 25,
      offset: 25,
    });

    expect(global.fetch).toHaveBeenCalledWith(
      buildSiemPath(
        "/response-registry?view=monitoring&q=1.2.3.4&sort=updated_at_asc&limit=25&offset=25"
      ),
      expect.objectContaining({ credentials: "include" })
    );
  });

  test("loadRegistryDetail requests record path", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ record: { id: 9 } }),
    });

    const data = await loadRegistryDetail(9);
    expect(data.record.id).toBe(9);
    expect(global.fetch).toHaveBeenCalledWith(
      buildSiemPath("/response-registry/9"),
      expect.objectContaining({ credentials: "include" })
    );
  });

  test("executeRegistryCommand posts canonical action payload", async () => {
    global.fetch.mockResolvedValue({
      ok: true,
      json: async () => ({ success: true, outcome_label: "monitored" }),
    });

    await executeRegistryCommand({
      action: "monitor",
      indicatorValue: "8.8.8.8",
      reason: "watch",
      alertId: 42,
      incidentId: 7,
      playbookExecutionId: 55,
      approvalRequestId: 12,
      idempotencyKey: "k1",
    });

    expect(global.fetch).toHaveBeenCalledWith(
      buildSiemPath("/response-registry/commands"),
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({
          action: "monitor",
          indicator_value: "8.8.8.8",
          reason: "watch",
          expires_at: null,
          alert_id: 42,
          incident_id: 7,
          playbook_execution_id: 55,
          approval_request_id: 12,
          idempotency_key: "k1",
        }),
      })
    );
  });
});
