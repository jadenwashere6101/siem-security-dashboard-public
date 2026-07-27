import React from "react";
import { render, screen, waitFor } from "@testing-library/react";

import ThreatHuntPanel from "./ThreatHuntPanel";

jest.mock("../services/threatHuntService", () => ({
  searchThreatHuntEvents: jest.fn(),
}));

function renderPanel(props = {}) {
  return render(
    <ThreatHuntPanel
      cardStyle={{}}
      cardHeaderStyle={{}}
      cardTitleStyle={{}}
      cardSubtitleStyle={{}}
      filterLabelStyle={{}}
      selectStyle={{}}
      displaySettings={{}}
      {...props}
    />
  );
}

test("restores Threat Hunt filters and emits lightweight history snapshots", async () => {
  const onHistoryStateChange = jest.fn();

  renderPanel({
    restoreRequest: {
      sectionId: "threat-hunt",
      nonce: 5,
      state: {
        threatHunt: {
          sourceIp: "203.0.113.10",
          source: "nginx",
          eventType: "unauthorized_access",
          startTime: "2026-05-01T10:00",
          endTime: "2026-05-01T11:00",
          expandedEventId: 44,
        },
      },
    },
    onHistoryStateChange,
  });

  await waitFor(() => expect(screen.getByLabelText("Source IP")).toHaveValue("203.0.113.10"));
  expect(screen.getByLabelText("Source")).toHaveValue("nginx");
  expect(screen.getByLabelText("Event Type")).toHaveValue("unauthorized_access");
  expect(screen.getByLabelText("Start Time (optional)")).toHaveValue("2026-05-01T10:00");
  expect(screen.getByLabelText("End Time (optional)")).toHaveValue("2026-05-01T11:00");
  await waitFor(() =>
    expect(onHistoryStateChange).toHaveBeenCalledWith(
      expect.objectContaining({
        sourceIp: "203.0.113.10",
        source: "nginx",
        eventType: "unauthorized_access",
        startTime: "2026-05-01T10:00",
        endTime: "2026-05-01T11:00",
        expandedEventId: 44,
      })
    )
  );
});
