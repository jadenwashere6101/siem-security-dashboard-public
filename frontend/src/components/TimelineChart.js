import React from "react";
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
} from "recharts";
import { formatTimestamp } from "../utils/displayFormatting";

function TimelineChart({
  data,
  tooltipStyle,
  tooltipLabelStyle,
  tooltipItemStyle,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  timelineRange,
  onTimelineRangeChange,
  timelineMeta,
  summaryPendingLabel,
  summaryBusy,
  displaySettings,
}) {
  const hasEnoughTrendData = data.length >= 2;
  const formatBucketTimestamp = (value) =>
    formatTimestamp(value, displaySettings, "Unknown time");
  const rangeOptions = [
    { value: "24h", label: "24 hours" },
    { value: "7d", label: "7 days" },
    { value: "30d", label: "30 days" },
    { value: "90d", label: "90 days" },
  ];
  const bucketLabel = timelineMeta?.bucket === "day" ? "Daily buckets" : timelineMeta?.bucket === "6 hours" ? "6-hour buckets" : "Hourly buckets";

  return (
    <section style={{ ...cardStyle, marginBottom: "24px" }}>
      <div style={cardHeaderStyle}>
        <div>
          <h2 style={cardTitleStyle}>Alerts Over Time</h2>
          <p style={{ margin: 0, color: "#8b949e", fontSize: "13px" }}>{bucketLabel}</p>
        </div>
        <div style={rangeControlRowStyle}>
          {rangeOptions.map((option) => {
            const selected = timelineRange === option.value;
            return (
              <button
                key={option.value}
                type="button"
                onClick={() => onTimelineRangeChange?.(option.value)}
                disabled={summaryBusy}
                aria-pressed={selected}
                style={{
                  ...rangeButtonStyle,
                  ...(selected ? rangeButtonActiveStyle : null),
                  opacity: summaryBusy && !selected ? 0.72 : 1,
                  cursor: summaryBusy ? "progress" : "pointer",
                }}
              >
                {option.label}
              </button>
            );
          })}
        </div>
      </div>
      {summaryPendingLabel ? (
        <div role="status" aria-live="polite" style={summaryStatusStyle}>
          <span style={summarySpinnerStyle} aria-hidden="true" />
          <span>{summaryPendingLabel}</span>
        </div>
      ) : null}

      <div className="chart-container" style={{ height: "220px", padding: "20px" }}>
        {!hasEnoughTrendData ? (
          <div
            style={{
              height: "100%",
              display: "flex",
              alignItems: "center",
              justifyContent: "center",
              color: "#8b949e",
              fontSize: "14px",
            }}
          >
            Not enough trend data yet
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={data} style={{ backgroundColor: "transparent" }}>
              <CartesianGrid stroke="#30363d" strokeDasharray="3 3" />
              <XAxis
                dataKey="bucketStart"
                stroke="#8b949e"
                tickFormatter={formatBucketTimestamp}
              />
              <YAxis stroke="#8b949e" allowDecimals={false} />
              <Tooltip
                contentStyle={tooltipStyle}
                labelStyle={tooltipLabelStyle}
                itemStyle={tooltipItemStyle}
                cursor={{ stroke: "#334155", strokeWidth: 1 }}
                wrapperStyle={{ outline: "none", backgroundColor: "transparent" }}
                labelFormatter={formatBucketTimestamp}
              />
              <Line
                type="monotone"
                dataKey="count"
                stroke="#d9a441"
                strokeWidth={3}
                dot={false}
                activeDot={{ r: 6, fill: "#e5e7eb", stroke: "#d9a441", strokeWidth: 2 }}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}

const rangeControlRowStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  flexWrap: "wrap",
};

const rangeButtonStyle = {
  border: "1px solid rgba(139, 148, 158, 0.28)",
  backgroundColor: "#0d1117",
  color: "#c9d1d9",
  borderRadius: "999px",
  padding: "7px 12px",
  fontSize: "12px",
  fontWeight: "700",
};

const rangeButtonActiveStyle = {
  borderColor: "rgba(217, 164, 65, 0.48)",
  backgroundColor: "rgba(217, 164, 65, 0.16)",
  color: "#f5d487",
};

const summaryStatusStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  padding: "0 20px 12px 20px",
  color: "#c9d1d9",
  fontSize: "13px",
};

const summarySpinnerStyle = {
  width: "14px",
  height: "14px",
  borderRadius: "999px",
  border: "2px solid rgba(201, 209, 217, 0.24)",
  borderTopColor: "#d9a441",
  borderRightColor: "transparent",
  animation: "workspace-spin 0.8s linear infinite",
};

export default TimelineChart;
