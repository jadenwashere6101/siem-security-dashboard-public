import {
  ATTENTION_NAV_TARGETS,
  attentionNavTarget,
  buildRegistryNavigation,
  registryNavFromAlert,
  registryNavFromIncident,
  registryNavFromSourceIp,
} from "./responseNavigation";
import {
  formatCanonicalActionSuccess,
  summarizeAlertResponseState,
} from "./responseStateLabels";
import { keysOverlap } from "../context/ResponseSyncContext";

describe("responseNavigation", () => {
  test("builds registry navigation from source IP and alert", () => {
    expect(registryNavFromSourceIp("8.8.8.8")).toEqual(
      expect.objectContaining({
        sectionId: "response-registry",
        q: "8.8.8.8",
      })
    );
    expect(registryNavFromAlert({ id: 12, source_ip: "1.1.1.1" })).toEqual(
      expect.objectContaining({
        relatedAlertId: 12,
        q: "1.1.1.1",
      })
    );
    expect(registryNavFromIncident({ id: 9, source_ip: "9.9.9.9" }).relatedIncidentId).toBe(9);
  });

  test("maps SOC attention items to authoritative workspaces", () => {
    expect(attentionNavTarget("Pending approvals")).toEqual({
      sectionId: "soar-approvals",
      statusFilter: "pending",
    });
    expect(ATTENTION_NAV_TARGETS["Queue pressure"].sectionId).toBe("soar-queue");
    expect(buildRegistryNavigation({ view: "monitoring", q: "8.8.8.8" }).view).toBe(
      "monitoring"
    );
  });
});

describe("responseStateLabels", () => {
  test("summarizes alert response state", () => {
    expect(summarizeAlertResponseState({ response_action: "monitor" }).label).toBe(
      "Monitored"
    );
    expect(
      summarizeAlertResponseState({
        response_action: "block_ip",
        response_status: "awaiting_approval",
      }).label
    ).toBe("Pending approval");
  });

  test("formats canonical success with resource identifiers", () => {
    const message = formatCanonicalActionSuccess(
      {
        message: "Tracking recorded",
        blocked_ip_id: 44,
        registry_record_id: 7,
        enforcement: "none",
        idempotent: true,
      },
      "block_ip"
    );
    expect(message).toContain("Tracking recorded");
    expect(message).toContain("Blocklist ID 44");
    expect(message).toContain("Registry #7");
    expect(message).toContain("idempotent");
    expect(message).toContain("No firewall");
  });
});

describe("response sync key overlap", () => {
  test("detects overlapping invalidation keys", () => {
    expect(keysOverlap(["alert:1", "blocklist"], ["response_registry", "blocklist"])).toBe(
      true
    );
    expect(keysOverlap(["alert:1"], ["incident:2"])).toBe(false);
  });
});
