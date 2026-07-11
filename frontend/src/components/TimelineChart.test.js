import { render, screen } from "@testing-library/react";

import TimelineChart from "./TimelineChart";

jest.mock("recharts", () => ({
  ResponsiveContainer: ({ children }) => <div>{children}</div>,
  LineChart: ({ children, data }) => (
    <div>
      <span data-testid="chart-data">{JSON.stringify(data)}</span>
      {children}
    </div>
  ),
  CartesianGrid: () => null,
  XAxis: ({ tickFormatter }) => (
    <span data-testid="axis-label">{tickFormatter(Date.UTC(2026, 6, 10, 22))}</span>
  ),
  YAxis: () => null,
  Tooltip: ({ labelFormatter }) => (
    <span data-testid="tooltip-label">{labelFormatter(Date.UTC(2026, 6, 10, 22))}</span>
  ),
  Line: () => null,
}));

const baseProps = {
  data: [
    { bucketStart: Date.UTC(2026, 6, 10, 21), count: 1 },
    { bucketStart: Date.UTC(2026, 6, 10, 22), count: 2 },
  ],
  tooltipStyle: {},
  tooltipLabelStyle: {},
  tooltipItemStyle: {},
  cardStyle: {},
  cardHeaderStyle: {},
  cardTitleStyle: {},
};

test("formats axis and tooltip labels with UTC 12-hour preferences", () => {
  render(
    <TimelineChart
      {...baseProps}
      displaySettings={{ timezoneMode: "utc", timestampFormat: "12h" }}
    />
  );

  expect(screen.getByTestId("axis-label")).toHaveTextContent("10:00 PM UTC");
  expect(screen.getByTestId("tooltip-label")).toHaveTextContent("10:00 PM UTC");
  expect(screen.getByTestId("chart-data")).toHaveTextContent('"count":2');
});

test("updates rendered labels when timestamp preferences change", () => {
  const { rerender } = render(
    <TimelineChart
      {...baseProps}
      displaySettings={{ timezoneMode: "utc", timestampFormat: "12h" }}
    />
  );

  rerender(
    <TimelineChart
      {...baseProps}
      displaySettings={{ timezoneMode: "utc", timestampFormat: "24h" }}
    />
  );

  expect(screen.getByTestId("axis-label")).toHaveTextContent("22:00 UTC");
  expect(screen.getByTestId("axis-label")).not.toHaveTextContent("PM");
});
