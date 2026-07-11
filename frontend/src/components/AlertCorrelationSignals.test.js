import { render, screen } from "@testing-library/react";

import AlertCorrelationSignals from "./AlertCorrelationSignals";

const detailSectionStyle = { marginTop: "10px" };
const signalRowStyle = {
  marginTop: "6px",
  padding: "8px 10px",
  borderRadius: "8px",
  backgroundColor: "#111827",
  border: "1px solid #30363d",
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
  fontSize: "12px",
  color: "#e6edf3",
};
const sourceTypeTextStyle = { color: "#8b949e", fontSize: "11px" };

test("section label uses an explicit readable dark-theme foreground under a black parent (no signals)", () => {
  render(
    <div style={{ color: "#000000" }}>
      <AlertCorrelationSignals
        alert={{ contributing_signals: [] }}
        detailSectionStyle={detailSectionStyle}
        signalRowStyle={signalRowStyle}
        sourceTypeTextStyle={sourceTypeTextStyle}
      />
    </div>
  );

  const label = screen.getByText("Behavioral Contributing Signals:");
  expect(label).toHaveStyle({ color: "#cbd5e1" });
  expect(label).not.toHaveStyle({ color: "inherit" });
  expect(screen.getByText("No contributing signals")).toHaveStyle({ color: "#8b949e" });
});

test("section label and signal rows remain readable under a black parent when signals are present", () => {
  render(
    <div style={{ color: "#000000" }}>
      <AlertCorrelationSignals
        alert={{
          contributing_signals: [
            { signal: "rapid_requests", label: "Rapid Requests", count: 12, weight: 2, total: 24 },
          ],
        }}
        detailSectionStyle={detailSectionStyle}
        signalRowStyle={signalRowStyle}
        sourceTypeTextStyle={sourceTypeTextStyle}
      />
    </div>
  );

  expect(screen.getByText("Behavioral Contributing Signals:")).toHaveStyle({ color: "#cbd5e1" });
  expect(screen.getByText("Rapid Requests").closest("div")).toHaveStyle({ color: "#e6edf3" });
  expect(screen.getByText(/count 12 · weight 2 · total 24/)).toHaveStyle({ color: "#8b949e" });
});
