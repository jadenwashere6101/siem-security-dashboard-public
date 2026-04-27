import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

function SeverityChart({
  metrics,
  tooltipStyle,
  tooltipLabelStyle,
  tooltipItemStyle,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
}) {
  const severityChartData = [
    { name: "High", value: metrics.highCount },
    { name: "Medium", value: metrics.mediumCount },
    { name: "Low", value: metrics.lowCount },
  ].filter((entry) => entry.value > 0);

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <h2 style={cardTitleStyle}>Alerts by Severity</h2>
      </div>

      <div className="chart-container" style={{ height: "240px", padding: "20px" }}>
        {severityChartData.length === 0 ? (
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
            No severity data yet
          </div>
        ) : (
          <ResponsiveContainer width="100%" height="100%">
            <BarChart data={severityChartData} style={{ backgroundColor: "transparent" }}>
              <XAxis dataKey="name" stroke="#8b949e" />
              <YAxis stroke="#8b949e" allowDecimals={false} />
              <Tooltip
                contentStyle={tooltipStyle}
                labelStyle={tooltipLabelStyle}
                itemStyle={tooltipItemStyle}
                cursor={{ fill: "rgba(88, 166, 255, 0.08)" }}
                wrapperStyle={{ outline: "none", backgroundColor: "transparent" }}
              />
              <Bar
                dataKey="value"
                radius={[6, 6, 0, 0]}
                barSize={40}
                activeBar={{ fillOpacity: 0.94, stroke: "#cbd5f5", strokeWidth: 1 }}
              >
                {severityChartData.map((entry, index) => {
                  let color = "#8b949e";
                  if (entry.name === "High") color = "#ef6b63";
                  if (entry.name === "Medium") color = "#d9a441";
                  if (entry.name === "Low") color = "#57c26d";
                  return <Cell key={index} fill={color} />;
                })}
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        )}
      </div>
    </section>
  );
}

export default SeverityChart;
