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
  displaySettings,
}) {
  const hasEnoughTrendData = data.length >= 2;
  const formatBucketTimestamp = (value) =>
    formatTimestamp(value, displaySettings, "Unknown time");

  return (
    <section style={{ ...cardStyle, marginBottom: "24px" }}>
      <div style={cardHeaderStyle}>
        <h2 style={cardTitleStyle}>Alerts Over Time</h2>
      </div>

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

export default TimelineChart;
