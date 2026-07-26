import React from "react";
import OperationalScopeToggle from "./OperationalScopeToggle";
import LoadingIndicator from "./LoadingIndicator";
import { SOURCE_METADATA } from "../utils/sourceMetadata";

function AlertsToolbar({
  filteredAlertsCount,
  resolvedAlertsCount,
  searchTerm,
  setSearchTerm,
  sortOption,
  setSortOption,
  operationalScope,
  setOperationalScope,
  severityFilter,
  setSeverityFilter,
  sourceFilter,
  setSourceFilter,
  ruleFilter = "all",
  setRuleFilter = () => {},
  ruleFilterOptions = [],
  statusFilter,
  setStatusFilter,
  exactSourceIp,
  exactTargetIp,
  exactAlertId,
  canResetFilters,
  onResetFilters,
  alertsPendingLabel,
  alertsBusy,
  multiAlertCsvExportHref,
  multiAlertReportHref,
  multiAlertPdfReportHref,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterWrapperStyle,
  filterLabelStyle,
  selectStyle,
}) {
  let activeContextLabel = "";
  if (exactTargetIp) {
    activeContextLabel = `Showing alerts targeting ${exactTargetIp}`;
  } else if (exactSourceIp) {
    activeContextLabel = `Showing alerts from source ${exactSourceIp}`;
  } else if (exactAlertId) {
    activeContextLabel = `Showing linked alert #${exactAlertId}`;
  }
  return (
    <div style={cardHeaderStyle}>
      <div>
        <h2 style={cardTitleStyle}>Recent Alerts</h2>

        <p style={cardSubtitleStyle}>
          Showing {filteredAlertsCount} alerts ({resolvedAlertsCount}{" "}
          resolved total)
        </p>
        {activeContextLabel ? (
          <div style={activeContextBannerStyle}>
            <span>{activeContextLabel}</span>
            <button
              type="button"
              onClick={onResetFilters}
              style={clearContextButtonStyle}
              disabled={!canResetFilters}
            >
              Clear context
            </button>
          </div>
        ) : null}
        {alertsPendingLabel ? (
          <LoadingIndicator label={alertsPendingLabel} style={alertsStatusStyle} />
        ) : null}

        <details style={exportMenuStyle}>
          <summary style={exportMenuTriggerStyle}>Export</summary>
          <div style={exportMenuPanelStyle}>
            <a href={multiAlertCsvExportHref} style={exportMenuOptionStyle}>
              Download Filtered Alerts (CSV)
            </a>
            <a href={multiAlertReportHref} style={exportMenuOptionStyle}>
              Download Filtered Incident Report (TXT)
            </a>
            <a
              href={multiAlertPdfReportHref}
              style={{
                ...exportMenuOptionStyle,
              }}
            >
              Download Filtered PDF Report
            </a>
          </div>
        </details>
      </div>

      <div style={filterWrapperStyle}>
        <OperationalScopeToggle
          value={operationalScope}
          onChange={setOperationalScope}
          label="Operational scope"
          compact
        />
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
          disabled={alertsBusy}
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
          disabled={alertsBusy}
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
          disabled={alertsBusy}
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
          disabled={alertsBusy}
          style={selectStyle}
        >
          <option value="all">All Sources</option>
          {SOURCE_METADATA.map((item) => (
            <option key={item.source} value={item.source}>{item.source}</option>
          ))}
        </select>
      </div>

      <div style={filterWrapperStyle}>
        <label htmlFor="ruleFilter" style={filterLabelStyle}>
          Detection Rule
        </label>
        <select
          id="ruleFilter"
          value={ruleFilter}
          onChange={(e) => setRuleFilter(e.target.value)}
          disabled={alertsBusy}
          style={selectStyle}
        >
          <option value="all">All Rules</option>
          {ruleFilterOptions.map((item) => (
            <option key={item.rule_id} value={item.rule_id}>
              {item.label || item.rule_id}
            </option>
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
          disabled={alertsBusy}
          style={selectStyle}
        >
          <option value="all">All</option>
          <option value="open">Open</option>
          <option value="resolved">Resolved</option>
        </select>
      </div>
      <div style={filterWrapperStyle}>
        <span style={filterLabelStyle}>Filters</span>
        <button
          type="button"
          onClick={onResetFilters}
          disabled={!canResetFilters || alertsBusy}
          style={{
            ...resetButtonStyle,
            opacity: !canResetFilters ? 0.55 : 1,
            cursor: !canResetFilters || alertsBusy ? "default" : "pointer",
          }}
        >
          Reset Filters
        </button>
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
const activeContextBannerStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  flexWrap: "wrap",
  marginTop: "12px",
  padding: "10px 12px",
  borderRadius: "12px",
  border: "1px solid rgba(217, 164, 65, 0.35)",
  backgroundColor: "rgba(217, 164, 65, 0.12)",
  color: "#f5d487",
  fontSize: "13px",
  fontWeight: "600",
};
const clearContextButtonStyle = {
  border: "1px solid rgba(245, 212, 135, 0.4)",
  backgroundColor: "transparent",
  color: "#f8e3a1",
  borderRadius: "999px",
  padding: "6px 10px",
  fontSize: "12px",
  fontWeight: "700",
};
const alertsStatusStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  marginTop: "10px",
  color: "#c9d1d9",
  fontSize: "13px",
};
const resetButtonStyle = {
  minWidth: "160px",
  padding: "10px 14px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#f0f6fc",
  fontSize: "13px",
  fontWeight: "700",
};

export default AlertsToolbar;
