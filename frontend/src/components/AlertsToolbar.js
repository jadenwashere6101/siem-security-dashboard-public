import React from "react";
import { SOURCE_METADATA } from "../utils/sourceMetadata";

function AlertsToolbar({
  filteredAlertsCount,
  resolvedAlertsCount,
  searchTerm,
  setSearchTerm,
  sortOption,
  setSortOption,
  severityFilter,
  setSeverityFilter,
  sourceFilter,
  setSourceFilter,
  statusFilter,
  setStatusFilter,
  multiAlertCsvExportHref,
  multiAlertReportHref,
  multiAlertPdfReportHref,
  downloadPdfReport,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterWrapperStyle,
  filterLabelStyle,
  selectStyle,
}) {
  return (
    <div style={cardHeaderStyle}>
      <div>
        <h2 style={cardTitleStyle}>Recent Alerts</h2>

        <p style={cardSubtitleStyle}>
          Showing {filteredAlertsCount} alerts ({resolvedAlertsCount}{" "}
          resolved total)
        </p>

        <details style={exportMenuStyle}>
          <summary style={exportMenuTriggerStyle}>Export</summary>
          <div style={exportMenuPanelStyle}>
            <a href={multiAlertCsvExportHref} style={exportMenuOptionStyle}>
              Download Filtered Alerts (CSV)
            </a>
            <a href={multiAlertReportHref} style={exportMenuOptionStyle}>
              Download Filtered Incident Report (TXT)
            </a>
            <button
              type="button"
              onClick={() =>
                downloadPdfReport(multiAlertPdfReportHref, "siem-alert-report.pdf")
              }
              style={{
                ...exportMenuOptionStyle,
                border: "none",
                width: "100%",
                backgroundColor: "transparent",
                cursor: "pointer",
                textAlign: "left",
              }}
            >
              Download Filtered PDF Report
            </button>
          </div>
        </details>
      </div>

      <div style={filterWrapperStyle}>
        <label htmlFor="searchAlerts" style={filterLabelStyle}>
          Search
        </label>
        <input
          id="searchAlerts"
          type="text"
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          placeholder="Search IP or message"
          style={{
            ...selectStyle,
            appearance: "none",
            WebkitAppearance: "none",
            MozAppearance: "none",
            paddingRight: "12px",
          }}
        />
      </div>

      <div style={filterWrapperStyle}>
        <label htmlFor="sortAlerts" style={filterLabelStyle}>
          Sort
        </label>
        <select
          id="sortAlerts"
          value={sortOption}
          onChange={(e) => setSortOption(e.target.value)}
          style={selectStyle}
        >
          <option value="newest">Newest</option>
          <option value="oldest">Oldest</option>
          <option value="severity">Severity</option>
        </select>
      </div>

      <div style={filterWrapperStyle}>
        <label htmlFor="severityFilter" style={filterLabelStyle}>
          Severity
        </label>
        <select
          id="severityFilter"
          value={severityFilter}
          onChange={(e) => setSeverityFilter(e.target.value)}
          style={selectStyle}
        >
          <option value="all">ALL</option>
          <option value="high">High</option>
          <option value="medium">Medium</option>
          <option value="low">Low</option>
        </select>
      </div>

      <div style={filterWrapperStyle}>
        <label htmlFor="sourceFilter" style={filterLabelStyle}>
          Source
        </label>
        <select
          id="sourceFilter"
          value={sourceFilter}
          onChange={(e) => setSourceFilter(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All Sources</option>
          {SOURCE_METADATA.map((item) => (
            <option key={item.source} value={item.source}>{item.source}</option>
          ))}
        </select>
      </div>

      <div style={filterWrapperStyle}>
        <label htmlFor="statusFilter" style={filterLabelStyle}>
          Status
        </label>
        <select
          id="statusFilter"
          value={statusFilter}
          onChange={(e) => setStatusFilter(e.target.value)}
          style={selectStyle}
        >
          <option value="all">All</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
        </select>
      </div>
    </div>
  );
}

const exportMenuStyle = {
  position: "relative",
  display: "inline-block",
  marginTop: "10px",
};
const exportMenuTriggerStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  listStyle: "none",
  padding: "6px 10px",
  borderRadius: "999px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "600",
  cursor: "pointer",
  userSelect: "none",
};
const exportMenuPanelStyle = {
  position: "absolute",
  top: "calc(100% + 8px)",
  left: 0,
  minWidth: "240px",
  padding: "8px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#111827",
  boxShadow: "0 12px 30px rgba(0,0,0,0.35)",
  zIndex: 5,
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};
const exportMenuOptionStyle = {
  display: "flex",
  alignItems: "center",
  padding: "8px 10px",
  borderRadius: "8px",
  color: "#dbeafe",
  textDecoration: "none",
  fontSize: "12px",
  fontWeight: "600",
  whiteSpace: "nowrap",
  backgroundColor: "transparent",
};

export default AlertsToolbar;
