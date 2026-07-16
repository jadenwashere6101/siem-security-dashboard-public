import {
  registryActionLabel,
  registryInvestigateTarget,
  registryOutcomeLabel,
  registryOutcomeTone,
  registryRecommendedNextStep,
} from "./responseRegistryPresentation";

describe("responseRegistryPresentation", () => {
  test("maps analyst-facing outcome labels and tones", () => {
    expect(
      registryOutcomeLabel({
        currentDisposition: "pending",
        latestOutcome: "awaiting_approval",
      })
    ).toBe("Awaiting Approval");
    expect(
      registryOutcomeLabel({
        currentDisposition: "monitored",
        latestRequestedAction: "monitor",
      })
    ).toBe("Monitoring");
    expect(
      registryOutcomeLabel({
        currentDisposition: "blocklist_tracked",
        enforcement: "tracking_only",
      })
    ).toBe("Tracking Only");
    expect(registryOutcomeLabel({ latestOutcome: "simulated", safeMetadata: { simulated: true } })).toBe(
      "Simulated"
    );
    expect(registryOutcomeLabel({ latestOutcome: "policy_blocked" })).toBe("Skipped");
    expect(registryOutcomeLabel({ latestOutcome: "failed" })).toBe("Failed");
    expect(registryOutcomeLabel({ latestOutcome: "succeeded" })).toBe("Executed");

    expect(registryOutcomeTone("Awaiting Approval")).toBe("warning");
    expect(registryOutcomeTone("Failed")).toBe("danger");
  });

  test("returns canonical investigate priority", () => {
    expect(
      registryInvestigateTarget(
        {
          relationships: {
            incidents: { primary_id: 77 },
            alerts: { primary_id: 42 },
          },
        },
        { sourceIp: "8.8.8.8" }
      )
    ).toEqual(
      expect.objectContaining({
        kind: "incident",
        id: 77,
      })
    );

    expect(
      registryInvestigateTarget(
        {
          relationships: {
            incidents: { primary_id: null },
            alerts: { primary_id: 42 },
          },
          record: { indicator_value: "8.8.8.8" },
        },
        {}
      )
    ).toEqual(
      expect.objectContaining({
        kind: "alert",
        id: 42,
        sourceIp: "8.8.8.8",
      })
    );

    expect(
      registryInvestigateTarget(
        {
          relationships: {
            incidents: { primary_id: null },
            alerts: { primary_id: null },
          },
          record: { indicator_value: "8.8.8.8" },
        },
        {}
      )
    ).toEqual(
      expect.objectContaining({
        kind: "source_ip",
        sourceIp: "8.8.8.8",
      })
    );
  });

  test("drives recommended next-step messaging deterministically", () => {
    expect(
      registryRecommendedNextStep({
        primary_approval_request: { status: "pending" },
        latest_event: { outcome: "awaiting_approval" },
      })
    ).toBe("Awaiting analyst approval.");

    expect(
      registryRecommendedNextStep({
        relationships: {
          incidents: { primary_id: 77 },
          alerts: { primary_id: 42 },
        },
      })
    ).toBe("Investigate related incident.");

    expect(
      registryRecommendedNextStep({
        relationships: {
          incidents: { primary_id: null },
          alerts: { primary_id: 42 },
        },
        record: { indicator_value: "8.8.8.8" },
      })
    ).toBe("Investigate originating alert.");

    expect(
      registryRecommendedNextStep({
        relationships: {
          incidents: { primary_id: null },
          alerts: { primary_id: null },
        },
        record: { current_disposition: "monitored", indicator_value: "8.8.8.8" },
      })
    ).toBe("Monitoring active.");
  });

  test("falls back to canonical action labels", () => {
    expect(registryActionLabel("flag_high_priority", null)).toBe("Escalated");
    expect(registryActionLabel(null, "monitored")).toBe("Monitored");
  });
});
