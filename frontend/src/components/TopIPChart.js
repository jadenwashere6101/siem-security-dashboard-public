import React from "react";
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from "recharts";

function TopIPChart({
  data,
  tooltipStyle,
  tooltipLabelStyle,
  tooltipItemStyle,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
}) {
  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <h2 style={cardTitleStyle}>Top Source IPs</h2>
      </div>

      <div className="chart-container" style={{ height: "240px", padding: "20px" }}>
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} barCategoryGap="30%" style={{ backgroundColor: "transparent" }}>
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
              fill="#6aaefc"
              radius={[6, 6, 0, 0]}
              barSize={40}
              activeBar={{ fillOpacity: 0.94, stroke: "#cbd5f5", strokeWidth: 1 }}
            />
          </BarChart>
        </ResponsiveContainer>
      </div>
    </section>
  );
}

export default TopIPChart;
