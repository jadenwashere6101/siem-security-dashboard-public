import React from "react";

function DashboardMetrics({
  metrics,
  metricsGridStyle,
  metricCardStyle,
  metricLabelStyle,
  metricValueStyle,
}) {
  return (
    <section style={metricsGridStyle}>
      <div style={metricCardStyle}>
        <p style={metricLabelStyle}>Total Alerts</p>
        <h3 style={metricValueStyle}>{metrics.totalAlerts}</h3>
      </div>

      <div style={metricCardStyle}>
        <p style={metricLabelStyle}>High Severity</p>
        <h3 style={metricValueStyle}>{metrics.highCount}</h3>
      </div>

      <div style={metricCardStyle}>
        <p style={metricLabelStyle}>Unique Source IPs</p>
        <h3 style={metricValueStyle}>{metrics.uniqueIPs}</h3>
      </div>

      <div style={metricCardStyle}>
        <p style={metricLabelStyle}>Medium / Low</p>
        <h3 style={metricValueStyle}>
          {metrics.mediumCount} / {metrics.lowCount}
        </h3>
      </div>
    </section>
  );
}

export default DashboardMetrics;
