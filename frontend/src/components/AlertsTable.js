import React, { useState } from "react";
import AlertDetailsPanel from "./AlertDetailsPanel";
import AlertResponseIndicator from "./AlertResponseIndicator";
import AlertsToolbar from "./AlertsToolbar";
import {
  buildSelectedAlertTimeline,
  getCorrelationAlertTypes,
  getReputationBadgeStyle,
  getSourceBadgeMeta,
  isCorrelationAlert,
} from "../utils/alertDisplay";
import { buildSiemPath } from "../utils/siemPath";

// ============================================================================
// Imports / Utilities
// ============================================================================

const MAX_ALERT_NOTE_LENGTH = 2000;

function AlertsTable({
  alerts,
  canTakeAlertActions,
  setAlerts,
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
  selectedAlertId,
  setSelectedAlertId,
  getSeverityBadgeStyle,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterWrapperStyle,
  filterLabelStyle,
  selectStyle,
  emptyStateStyle,
  emptyStateTextStyle,
  tableWrapperStyle,
  tableStyle,
  headerCellStyle,
  bodyCellStyle,
  onUpdateStatus,
  monoCellStyle,
  tableRowStyle,
  expandedCellStyle,
  expandedContentStyle,
  expandedLabelStyle,
  expandedTextStyle,
}) {
  // ==========================================================================
  // Component State / Derived Values
  // ==========================================================================

  const [responseLogs, setResponseLogs] = useState({});
  const [alertNotes, setAlertNotes] = useState({});
  const [noteDrafts, setNoteDrafts] = useState({});
  const [loadingNotesForAlertId, setLoadingNotesForAlertId] = useState(null);
  const [addingNoteForAlertId, setAddingNoteForAlertId] = useState(null);
  const [executingActionId, setExecutingActionId] = useState(null);
  const [toastMessage, setToastMessage] = useState("");
  const [toastType, setToastType] = useState("info");
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [hoveredAlertId, setHoveredAlertId] = useState(null);
  const [collapsedGroups, setCollapsedGroups] = useState({});

  // ==========================================================================
  // Inline Styles
  // ==========================================================================
  // Large style clusters stay in-file for now to avoid changing props or JSX
  // structure during this readability-only pass.

  const exportRowStyle = {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    marginTop: "10px",
    flexWrap: "wrap",
  };
  const exportLabelStyle = {
    color: "#9ca3af",
    fontSize: "12px",
    fontWeight: "700",
    letterSpacing: "0.04em",
    textTransform: "uppercase",
  };
  const inlineExportLinkStyle = {
    display: "inline-flex",
    alignItems: "center",
    color: "#93c5fd",
    textDecoration: "none",
    fontSize: "12px",
    fontWeight: "700",
    letterSpacing: "0.02em",
  };
  const exportDividerStyle = {
    color: "#4b5563",
    fontSize: "12px",
  };
  const mitreSectionStyle = {
    margin: "12px 0 10px",
    padding: "10px 12px",
    borderRadius: "10px",
    border: "1px solid #30363d",
    backgroundColor: "#111827",
  };
  const mitreHeaderRowStyle = {
    display: "flex",
    alignItems: "center",
    gap: "8px",
    flexWrap: "wrap",
    marginBottom: "6px",
  };
  const mitreTechniqueBadgeStyle = {
    display: "inline-flex",
    alignItems: "center",
    justifyContent: "center",
    padding: "4px 8px",
    borderRadius: "999px",
    backgroundColor: "rgba(59, 130, 246, 0.14)",
    border: "1px solid rgba(59, 130, 246, 0.3)",
    color: "#93c5fd",
    fontSize: "11px",
    fontWeight: "700",
    letterSpacing: "0.03em",
  };
  const mitreTechniqueNameStyle = {
    color: "#e6edf3",
    fontSize: "13px",
    fontWeight: "600",
  };
const mitreTacticStyle = {
  margin: 0,
  color: "#9ca3af",
  fontSize: "12px",
};
const sourceBadgeStackStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};
const sourceBadgeStyle = {
  display: "inline-block",
  width: "fit-content",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};
const sourceTypeTextStyle = {
  color: "#8b949e",
  fontSize: "11px",
};
const detailLabelTextStyle = {
  color: "#cbd5e1",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.02em",
};
const detailValueTextStyle = {
  color: "#e6edf3",
  fontSize: "14px",
};
const expandedSecondaryTextStyle = {
  color: "#8b949e",
  fontSize: "12px",
};
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
const correlationBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "6px",
  width: "fit-content",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "800",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  color: "#fde68a",
  backgroundColor: "rgba(245, 158, 11, 0.12)",
  border: "1px solid rgba(245, 158, 11, 0.34)",
};
const correlationPanelStyle = {
  margin: "12px 0 10px",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid rgba(245, 158, 11, 0.32)",
  backgroundColor: "rgba(120, 53, 15, 0.18)",
};
const correlationListStyle = {
  margin: "8px 0 0",
  paddingLeft: "18px",
  color: "#fef3c7",
  fontSize: "12px",
};
const targetedAlertPanelStyle = {
  margin: "12px 0 10px",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid rgba(239, 68, 68, 0.28)",
  backgroundColor: "rgba(69, 10, 10, 0.16)",
};
const groupHeaderRowStyle = {
  backgroundColor: "#101722",
  borderTop: "1px solid #30363d",
  borderBottom: "1px solid #253041",
  cursor: "pointer",
};
const groupHeaderCellStyle = {
  ...bodyCellStyle,
  padding: "10px 14px",
  backgroundColor: "#101722",
};
const groupHeaderContentStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
};
const groupHeaderMetaStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  flexWrap: "wrap",
};
const groupHeaderTitleStyle = {
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "700",
};
const groupHeaderSubtextStyle = {
  color: "#94a3b8",
  fontSize: "11px",
};
const groupCountBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  color: "#cbd5e1",
  backgroundColor: "rgba(148, 163, 184, 0.12)",
  border: "1px solid rgba(148, 163, 184, 0.22)",
};
const detailSectionStyle = {
  marginTop: "10px",
};
  const severityRank = {
    critical: 1,
    high: 2,
    medium: 3,
    low: 4,
  };

  // ==========================================================================
  // Event Handlers
  // ==========================================================================

  const showToast = (message, type = "info") => {
    setToastMessage(message);
    setToastType(type);
    setTimeout(() => {
      setToastMessage("");
      setToastType("info");
    }, type === "error" ? 5500 : 2500);
  };

  const getAccessDeniedMessage = () =>
    "🔒 Access denied — elevated privileges required\nThis attempt was logged in the audit trail.";

  const isAdminRequiredError = (message) =>
    /admin role required|super admin role required|analyst or super admin role required|forbidden/i.test(message || "");

  // Shared action button styling for permission-aware controls.
  const getActionButtonStyle = (baseStyle, restrictedAccent) => {
    if (canTakeAlertActions) {
      return baseStyle;
    }

    return {
      ...baseStyle,
      backgroundColor: "#161b22",
      color: "#c9d1d9",
      border: "1px solid #30363d",
      boxShadow: "none",
      opacity: 0.9,
    };
  };

  // ==========================================================================
  // Response Actions / Notes
  // ==========================================================================

  const fetchResponseLog = async (alertId) => {
    try {
      const res = await fetch(buildSiemPath(`/alerts/${alertId}/response-log`), {
        credentials: "include",
      });

      const data = await res.json();

      setResponseLogs(prev => ({
        ...prev,
        [alertId]: data
      }));

    } catch (err) {
      console.error("Error fetching response log:", err);
    }
  };

  const fetchAlertNotes = async (alertId) => {
    try {
      setLoadingNotesForAlertId(alertId);
      const res = await fetch(buildSiemPath(`/alerts/${alertId}/notes`), {
        credentials: "include",
      });

      const data = await res.json().catch(() => []);

      if (!res.ok) {
        const errorMessage = data.error || "Unable to load notes";
        throw new Error(errorMessage);
      }

      setAlertNotes((prev) => ({
        ...prev,
        [alertId]: Array.isArray(data) ? data : [],
      }));
    } catch (err) {
      console.error("Error fetching alert notes:", err);
      showToast(err.message || "Unable to load notes", "error");
    } finally {
      setLoadingNotesForAlertId(null);
    }
  };

  const formatNoteTimestamp = (value) => {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return value;
    }

    return new Intl.DateTimeFormat("en-US", {
      month: "short",
      day: "2-digit",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "UTC",
      timeZoneName: "short",
    }).format(date);
  };

  const addAlertNote = async (alertId) => {
    const noteText = (noteDrafts[alertId] || "").trim();
    if (!noteText) {
      showToast("Note text is required", "error");
      return;
    }

    try {
      setAddingNoteForAlertId(alertId);
      const res = await fetch(buildSiemPath(`/alerts/${alertId}/notes`), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ note_text: noteText }),
      });

      const data = await res.json().catch(() => ({}));

      if (!res.ok) {
        const errorMessage = data.error || "Unable to add note";
        throw new Error(errorMessage);
      }

      setNoteDrafts((prev) => ({
        ...prev,
        [alertId]: "",
      }));
      await fetchAlertNotes(alertId);
      showToast("Note added successfully");
    } catch (err) {
      console.error("Error adding alert note:", err);
      showToast(err.message || "Unable to add note", "error");
    } finally {
      setAddingNoteForAlertId(null);
    }
  };

  // ==========================================================================
  // Export / Report Actions
  // ==========================================================================

  const downloadPdfReport = async (url, filename) => {
    try {
      const response = await fetch(url, {
        credentials: "include",
      });

      if (!response.ok) {
        throw new Error("Unable to download PDF report");
      }

      const pdfBlob = await response.blob();
      const objectUrl = window.URL.createObjectURL(pdfBlob);
      const downloadLink = document.createElement("a");

      downloadLink.href = objectUrl;
      downloadLink.download = filename;
      downloadLink.style.display = "none";
      downloadLink.rel = "noopener";
      document.body.appendChild(downloadLink);
      downloadLink.click();
      document.body.removeChild(downloadLink);
      window.setTimeout(() => {
        window.URL.revokeObjectURL(objectUrl);
      }, 1000);
    } catch (err) {
      console.error("Error downloading PDF report:", err);
      showToast("Unable to download PDF report", "error");
    }
  };

  const executeAction = async (alertId, action) => {
    try {
      setExecutingActionId(alertId);

      const executeRes = await fetch(buildSiemPath(`/alerts/${alertId}/execute`), {
        method: "POST",
        credentials: "include",
        headers: {
          "Content-Type": "application/json"
        },
        body: JSON.stringify({ action })
      });

      if (!executeRes.ok) {
        const errorData = await executeRes.json().catch(() => ({}));
        throw new Error(errorData.message || errorData.error || "Action failed");
      }

      // refresh response log for that alert
      await fetchResponseLog(alertId);

      // refresh alerts without reloading page
      const res = await fetch(buildSiemPath("/alerts"), {
        credentials: "include",
      });

      if (!res.ok) {
        throw new Error("Failed to refresh alerts");
      }

      const data = await res.json();

      if (!Array.isArray(data)) {
        throw new Error("Invalid alerts response");
      }

      setAlerts(data);

      showToast(`Action "${action}" executed successfully`);
    } catch (err) {
      console.error("Error executing action:", err);
      showToast(
        isAdminRequiredError(err.message)
          ? getAccessDeniedMessage()
          : err.message || "Action failed",
        isAdminRequiredError(err.message) ? "error" : "info"
      );
    } finally {
      setExecutingActionId(null);
    }
  };

  // ==========================================================================
  // Badge / Display Helpers
  // ==========================================================================

  // Filtered/resolved alert collections used by the table and summary UI.
  const filteredAlerts = alerts;

  const resolvedAlerts = alerts.filter(
    (alert) => alert.status === "resolved"
  );

  // Derived export links stay local to the table header controls.
  const reportQuery = new URLSearchParams();
  if (searchTerm) {
    reportQuery.set("search", searchTerm);
  }
  if (severityFilter && severityFilter !== "all") {
    reportQuery.set("severity", severityFilter);
  }
  if (statusFilter && statusFilter !== "all") {
    reportQuery.set("status", statusFilter);
  }
  const multiAlertReportHref = buildSiemPath(
    `/alerts/report${reportQuery.toString() ? `?${reportQuery.toString()}` : ""}`
  );
  const multiAlertCsvExportHref = buildSiemPath(
    `/alerts/export/csv${reportQuery.toString() ? `?${reportQuery.toString()}` : ""}`
  );
  const multiAlertPdfReportHref = buildSiemPath(
    `/alerts/report/pdf${reportQuery.toString() ? `?${reportQuery.toString()}` : ""}`
  );

  const getTargetedAlertMeta = (alertType) => {
    if (alertType === "spray_then_success_pattern") {
      return {
        badge: "Attack Chain",
        description: "Password spray followed by successful login",
        rowStyle: {
          backgroundColor: "#251212",
          borderLeft: "3px solid rgba(239, 68, 68, 0.95)",
        },
        badgeStyle: {
          color: "#fecaca",
          backgroundColor: "rgba(239, 68, 68, 0.16)",
          border: "1px solid rgba(239, 68, 68, 0.34)",
        },
      };
    }

    if (alertType === "web_to_app_attack_pattern") {
      return {
        badge: "Web → App Attack",
        description: "Web layer errors followed by application authentication activity",
        rowStyle: {
          backgroundColor: "#221711",
          borderLeft: "3px solid rgba(249, 115, 22, 0.92)",
        },
        badgeStyle: {
          color: "#fdba74",
          backgroundColor: "rgba(249, 115, 22, 0.14)",
          border: "1px solid rgba(249, 115, 22, 0.32)",
        },
      };
    }

    if (alertType === "cloud_app_error_pattern") {
      return {
        badge: "Cloud + Web",
        description: "Cloud and web application errors correlated across services",
        rowStyle: {
          backgroundColor: "#1d1811",
          borderLeft: "3px solid rgba(245, 158, 11, 0.86)",
        },
        badgeStyle: {
          color: "#fde68a",
          backgroundColor: "rgba(245, 158, 11, 0.12)",
          border: "1px solid rgba(245, 158, 11, 0.28)",
        },
      };
    }

    if (alertType === "correlated_activity") {
      return {
        badge: "Correlation",
        description: "Multi-source / multi-signal activity grouped into a higher-confidence alert.",
        rowStyle: {
          backgroundColor: "#19150d",
          borderLeft: "3px solid rgba(245, 158, 11, 0.9)",
        },
        badgeStyle: correlationBadgeStyle,
      };
    }

    return null;
  };

  // ==========================================================================
  // Timeline / Alert Details
  // ==========================================================================

  // Timeline is built from the currently selected alert and the already-loaded
  // alert collection. No extra API request is made for this view.
  const selectedAlertTimeline = buildSelectedAlertTimeline(selectedAlert, alerts);

  const groupedFilteredAlerts = [];
  const groupedFilteredAlertsMap = new Map();

  // Grouping happens after upstream filtering/sorting so table behavior stays intact.
  filteredAlerts.forEach((alert) => {
    const groupKey = alert.source_ip || "Unknown IP";
    const existingGroup = groupedFilteredAlertsMap.get(groupKey);

    if (existingGroup) {
      existingGroup.alerts.push(alert);
      return;
    }

    const nextGroup = {
      sourceIp: groupKey,
      alerts: [alert],
    };

    groupedFilteredAlertsMap.set(groupKey, nextGroup);
    groupedFilteredAlerts.push(nextGroup);
  });

  // Each group keeps a primary row plus a highest-severity summary for the
  // collapsed table view.
  groupedFilteredAlerts.forEach((group) => {
    const highestSeverityAlert = group.alerts.reduce((currentHighest, candidate) => {
      if (!currentHighest) {
        return candidate;
      }

      const currentRank = severityRank[currentHighest.severity] || 99;
      const candidateRank = severityRank[candidate.severity] || 99;

      return candidateRank < currentRank ? candidate : currentHighest;
    }, null);

    group.primaryAlert = group.alerts[0];
    group.highestSeverity = highestSeverityAlert?.severity || "unknown";
    group.locationLabel =
      group.primaryAlert?.city && group.primaryAlert?.country
        ? `${group.primaryAlert.city}, ${group.primaryAlert.country}`
        : "Location unavailable";
  });

  // Row-level actions stay local so clicks do not leak into parent row selection.
  const toggleGroup = (groupKey) => {
    setCollapsedGroups((current) => ({
      ...current,
      [groupKey]: !current[groupKey],
    }));
  };

  const handleResolve = async (e, alertId) => {
    e.stopPropagation();
    const result = await onUpdateStatus(alertId, "resolved");

    if (!result?.ok) {
      showToast(
        isAdminRequiredError(result?.message)
          ? getAccessDeniedMessage()
          : result?.message || "Access denied",
        isAdminRequiredError(result?.message) ? "error" : "info"
      );
    }
  };

  // ==========================================================================
  // Rendered Table / JSX
  // ==========================================================================

  return (
    <>
      {toastMessage && (
        <div
          style={{
            position: "fixed",
            top: "20px",
            right: "20px",
            backgroundColor: toastType === "error" ? "#2d1117" : "#111827",
            color: toastType === "error" ? "#ffb4b4" : "#fff",
            padding: "10px 14px",
            borderRadius: "8px",
            border: toastType === "error" ? "1px solid #f85149" : "1px solid #374151",
            boxShadow: "0 4px 12px rgba(0,0,0,0.3)",
            zIndex: 9999,
            fontSize: "14px",
            fontWeight: "600",
            whiteSpace: "pre-line",
            maxWidth: "340px",
            lineHeight: "1.45",
          }}
        >
          {toastMessage}
        </div>
      )}

      <section style={cardStyle}>
        <AlertsToolbar
          filteredAlertsCount={filteredAlerts.length}
          resolvedAlertsCount={resolvedAlerts.length}
          searchTerm={searchTerm}
          setSearchTerm={setSearchTerm}
          sortOption={sortOption}
          setSortOption={setSortOption}
          severityFilter={severityFilter}
          setSeverityFilter={setSeverityFilter}
          sourceFilter={sourceFilter}
          setSourceFilter={setSourceFilter}
          statusFilter={statusFilter}
          setStatusFilter={setStatusFilter}
          multiAlertCsvExportHref={multiAlertCsvExportHref}
          multiAlertReportHref={multiAlertReportHref}
          multiAlertPdfReportHref={multiAlertPdfReportHref}
          downloadPdfReport={downloadPdfReport}
          cardHeaderStyle={cardHeaderStyle}
          cardTitleStyle={cardTitleStyle}
          cardSubtitleStyle={cardSubtitleStyle}
          filterWrapperStyle={filterWrapperStyle}
          filterLabelStyle={filterLabelStyle}
          selectStyle={selectStyle}
        />

        {filteredAlerts.length === 0 ? (
          <div style={emptyStateStyle}>
            <p style={emptyStateTextStyle}>
              No alerts found for the selected filters.
            </p>
          </div>
        ) : (
          <div style={tableWrapperStyle}>
            <div
              style={{
                maxHeight: "500px",
                overflowY: "auto",
                overflowX: "auto",
                width: "100%",
              }}
            >
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={headerCellStyle}>ID</th>
                  <th style={headerCellStyle}>Type</th>
                  <th style={headerCellStyle}>Source</th>
                  <th style={headerCellStyle}>Source IP</th>
                  <th style={headerCellStyle}>Behavior</th>
                  <th style={headerCellStyle}>Severity</th>
                  <th style={headerCellStyle}>Message</th>
                  <th style={headerCellStyle}>Created At</th>
                  <th style={headerCellStyle}>Action</th>
                </tr>
              </thead>

            <tbody>
              {groupedFilteredAlerts.map((group) => (
                <React.Fragment key={group.sourceIp}>
                  <tr
                    style={groupHeaderRowStyle}
                    onClick={() => toggleGroup(group.sourceIp)}
                    title={collapsedGroups[group.sourceIp] ? "Expand group" : "Collapse group"}
                  >
                    <td colSpan="9" style={groupHeaderCellStyle}>
                      <div style={groupHeaderContentStyle}>
                        <div style={groupHeaderMetaStyle}>
                          <span style={groupHeaderTitleStyle}>
                            {collapsedGroups[group.sourceIp] ? "▸" : "▾"} {group.sourceIp}
                          </span>
                          <span style={groupHeaderSubtextStyle}>{group.locationLabel}</span>
                          <span style={groupCountBadgeStyle}>
                            {group.alerts.length} {group.alerts.length === 1 ? "alert" : "alerts"}
                          </span>
                        </div>
                        <div style={groupHeaderMetaStyle}>
                          <span style={groupHeaderSubtextStyle}>Highest severity</span>
                          <span style={getSeverityBadgeStyle(group.highestSeverity)}>
                            {group.highestSeverity}
                          </span>
                        </div>
                      </div>
                    </td>
                  </tr>

                  {!collapsedGroups[group.sourceIp] &&
                    group.alerts.map((alert) => {
                      const sourceBadge = getSourceBadgeMeta(alert.source, alert.source_type);
                      const correlationAlert = isCorrelationAlert(alert);
                      const targetedAlertMeta = getTargetedAlertMeta(alert.alert_type);
                      const correlatedAlertTypes = getCorrelationAlertTypes(alert);

                      return (
                      <React.Fragment key={alert.id}>
                        <tr
                          style={{
                            ...tableRowStyle,
                            cursor: "pointer",
                            backgroundColor:
                              selectedAlertId === alert.id
                                ? targetedAlertMeta
                                  ? targetedAlertMeta.rowStyle.backgroundColor === "#19150d"
                                    ? "#1f1a11"
                                    : targetedAlertMeta.rowStyle.backgroundColor
                                  : "#111827"
                                : targetedAlertMeta
                                  ? targetedAlertMeta.rowStyle.backgroundColor
                                  : hoveredAlertId === alert.id
                                    ? "#1b2230"
                                    : "#161b22",
                            borderLeft: targetedAlertMeta
                              ? targetedAlertMeta.rowStyle.borderLeft
                              : tableRowStyle.borderLeft,
                            transition: "background-color 120ms ease",
                          }}
                          onMouseEnter={() => setHoveredAlertId(alert.id)}
                          onMouseLeave={() => setHoveredAlertId(null)}
                          onClick={() => {
                            if (selectedAlertId === alert.id) {
                              setSelectedAlertId(null);
                              setSelectedAlert(null);
                            } else {
                              setSelectedAlertId(alert.id);
                              setSelectedAlert(alert);
                              fetchResponseLog(alert.id);
                              if (canTakeAlertActions) {
                                fetchAlertNotes(alert.id);
                              }
                            }
                          }}
                        >
                          <td style={bodyCellStyle}>{alert.id}</td>

                          <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                            <div style={sourceBadgeStackStyle}>
                              <span>{alert.alert_type}</span>
                              {targetedAlertMeta?.badge && (
                                <span style={targetedAlertMeta.badgeStyle} title={targetedAlertMeta.description || targetedAlertMeta.badge}>
                                  {targetedAlertMeta.badge}
                                </span>
                              )}
                            </div>
                          </td>

                          <td style={bodyCellStyle}>
                            <div style={sourceBadgeStackStyle}>
                              <span style={{ ...sourceBadgeStyle, ...sourceBadge.style }} title={`Source: ${sourceBadge.label}`}>
                                {sourceBadge.label}
                              </span>
                              <span style={sourceTypeTextStyle}>{sourceBadge.subLabel}</span>
                            </div>
                          </td>

                          <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                            <div>{alert.source_ip}</div>
                            <div style={{ fontSize: "12px", color: "#666", marginTop: "4px" }}>
                              {alert.city && alert.country
                                ? `${alert.city}, ${alert.country}`
                                : "Location unavailable"}
                            </div>
                          </td>

                          <td style={bodyCellStyle}>
                            <div style={sourceBadgeStackStyle}>
                              <span
                                style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(alert.reputation_label) }}
                                title={`Behavioral reputation: ${alert.reputation_label || "Normal"} (${alert.reputation_score ?? 0})`}
                              >
                                {alert.reputation_label || "Normal"}
                              </span>
                              <span style={sourceTypeTextStyle}>Score {alert.reputation_score ?? 0}</span>
                            </div>
                          </td>

                          <td style={bodyCellStyle}>
                            <div>
                              <span style={getSeverityBadgeStyle(alert.severity)}>
                                {alert.severity}
                              </span>
                            </div>
                          </td>

                          <td style={bodyCellStyle}>{alert.message}</td>

                          <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                            {alert.created_at}
                          </td>

                          <td style={bodyCellStyle}>
                            <div
                              style={{
                                display: "flex",
                                alignItems: "center",
                                gap: "10px",
                                flexWrap: "wrap",
                              }}
                            >
                              <AlertResponseIndicator responseAction={alert.response_action} />
                              {alert.status === "open" && (
                                <button
                                  onClick={(e) => handleResolve(e, alert.id)}
                                  title={canTakeAlertActions ? "Resolve alert" : "Requires elevated privileges"}
                                  style={getActionButtonStyle(
                                    {
                                      padding: "6px 10px",
                                      backgroundColor: "#238636",
                                      color: "white",
                                      border: "none",
                                      borderRadius: "6px",
                                      cursor: "pointer",
                                      fontWeight: "700",
                                      transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
                                    },
                                    "#f59e0b"
                                  )}
                                >
                                  {canTakeAlertActions ? "Resolve" : "🔒 Resolve"}
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>

                        {selectedAlertId === alert.id && (
                          <tr onClick={(e) => e.stopPropagation()}>
                            <td colSpan="9" style={expandedCellStyle}>
                              <div style={expandedContentStyle}>
                          <p style={{ ...expandedLabelStyle, marginBottom: "10px" }}>Alert Details</p>

                          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                            <strong style={detailLabelTextStyle}>ID:</strong>{" "}
                            <span style={detailValueTextStyle}>{alert.id}</span>
                          </p>

                          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                            <strong style={detailLabelTextStyle}>Type:</strong>{" "}
                            <span style={detailValueTextStyle}>{alert.alert_type}</span>
                          </p>

                          {targetedAlertMeta && (
                            <div style={correlationAlert ? correlationPanelStyle : targetedAlertPanelStyle}>
                              <p style={expandedLabelStyle}>
                                {correlationAlert ? "Correlation Alert" : "Targeted Correlation Alert"}
                              </p>
                              <div style={{ marginBottom: "8px" }}>
                                <span style={targetedAlertMeta.badgeStyle}>{targetedAlertMeta.badge}</span>
                              </div>
                              <p style={expandedTextStyle}>
                                {targetedAlertMeta.description}
                              </p>
                              {correlationAlert && correlatedAlertTypes.length > 0 ? (
                                <div>
                                  <p style={expandedTextStyle}>
                                    <strong>Involved Alert Types:</strong>
                                  </p>
                                  <ul style={correlationListStyle}>
                                    {correlatedAlertTypes.map((alertType) => (
                                      <li key={alertType}>
                                        <span style={{ ...monoCellStyle, fontSize: "12px" }}>
                                          {alertType}
                                        </span>
                                      </li>
                                    ))}
                                  </ul>
                                </div>
                              ) : (
                                <p style={expandedTextStyle}>
                                  <strong>{correlationAlert ? "Correlation Message" : "Alert Message"}:</strong> {alert.message}
                                </p>
                              )}
                            </div>
                          )}

                          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                            <strong style={detailLabelTextStyle}>Source:</strong>{" "}
                            <span style={detailValueTextStyle}>{sourceBadge.label}</span>{" "}
                            <span style={expandedSecondaryTextStyle}>
                              ({sourceBadge.subLabel})
                            </span>
                          </p>

                          <div style={detailSectionStyle}>
                            <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                              <strong style={detailLabelTextStyle}>Source IP:</strong>{" "}
                              <span style={{ ...monoCellStyle, ...detailValueTextStyle }}>
                                {alert.source_ip}
                              </span>
                            </p>

                            <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                              <strong style={detailLabelTextStyle}>Location:</strong>{" "}
                              <span style={detailValueTextStyle}>{alert.city && alert.country
                                ? `${alert.city}, ${alert.country}`
                                : "Location unavailable"}</span>
                            </p>
                          </div>

                          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                            <strong style={detailLabelTextStyle}>Severity:</strong>{" "}
                            <span style={detailValueTextStyle}>{alert.severity}</span>
                          </p>

                          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                            <strong style={detailLabelTextStyle}>Message:</strong>{" "}
                            <span style={detailValueTextStyle}>{alert.message}</span>
                          </p>

                          {(alert.mitre_technique_id || alert.mitre_technique_name || alert.mitre_tactic) && (
                            <div style={mitreSectionStyle}>
                              <p style={expandedLabelStyle}>MITRE ATT&CK</p>
                              <div style={mitreHeaderRowStyle}>
                                {alert.mitre_technique_id && (
                                  <span style={mitreTechniqueBadgeStyle}>
                                    {alert.mitre_technique_id}
                                  </span>
                                )}
                                {alert.mitre_technique_name && (
                                  <span style={mitreTechniqueNameStyle}>
                                    {alert.mitre_technique_name}
                                  </span>
                                )}
                              </div>
                              {alert.mitre_tactic && (
                                <p style={mitreTacticStyle}>
                                  <strong>Tactic:</strong> {alert.mitre_tactic}
                                </p>
                              )}
                            </div>
                          )}

                          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                            <strong style={detailLabelTextStyle}>Behavioral Reputation:</strong>{" "}
                            <span
                              style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(alert.reputation_label) }}
                              title={`Behavioral reputation: ${alert.reputation_label || "Normal"} (${alert.reputation_score ?? 0})`}
                            >
                              {alert.reputation_label || "Normal"} ({alert.reputation_score ?? 0})
                            </span>
                          </p>
                          <p style={expandedSecondaryTextStyle}>
                            Internal SIEM-generated behavioral score
                          </p>
                          <p style={{ marginTop: "8px" }}>
                            {alert.reputation_summary || "No reputation details available"}
                          </p>
                          <div style={detailSectionStyle}>
                            <strong>Contributing Signals:</strong>
                            {Array.isArray(alert.contributing_signals) && alert.contributing_signals.length > 0 ? (
                              alert.contributing_signals.map((signal) => (
                                <div key={signal.signal} style={signalRowStyle}>
                                  <span>{signal.label}</span>
                                  <span style={sourceTypeTextStyle}>
                                    count {signal.count} · weight {signal.weight} · total {signal.total}
                                  </span>
                                </div>
                              ))
                            ) : (
                              <div style={{ fontSize: "12px", color: "#8b949e", marginTop: "4px" }}>
                                No contributing signals
                              </div>
                            )}
                          </div>

                          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                            <strong style={detailLabelTextStyle}>Response Action:</strong>{" "}
                            <span style={detailValueTextStyle}>{alert.response_action || "Not set"}</span>
                          </p>
                          <p style={{ ...expandedTextStyle, marginBottom: "6px" }}>
                            <strong style={detailLabelTextStyle}>Response Status:</strong>{" "}
                            <span style={detailValueTextStyle}>{alert.response_status || "Not set"}</span>
                          </p>

                          <div style={exportRowStyle}>
                            <span style={exportLabelStyle}>Export:</span>
                            <a
                              href={buildSiemPath(`/alerts/${alert.id}/report`)}
                              style={inlineExportLinkStyle}
                              onClick={(e) => e.stopPropagation()}
                            >
                              Download Incident Report (TXT)
                            </a>
                            <span style={exportDividerStyle}>|</span>
                            <button
                              type="button"
                              style={{
                                ...inlineExportLinkStyle,
                                border: "none",
                                backgroundColor: "transparent",
                                padding: 0,
                                cursor: "pointer",
                              }}
                              onClick={(e) => {
                                e.stopPropagation();
                                downloadPdfReport(
                                  buildSiemPath(`/alerts/${alert.id}/report/pdf`),
                                  `siem-alert-${alert.id}-report.pdf`
                                );
                              }}
                            >
                              Download PDF Report
                            </button>
                          </div>

                          <div style={{ marginTop: "10px" }}>
                            <strong>Response Log:</strong>

                            {responseLogs[alert.id] && responseLogs[alert.id].length > 0 ? (
                              responseLogs[alert.id].map((log) => {
                                let color = "#999";

                                if (log.action === "block_ip") color = "#ff4d4f";
                                else if (log.action === "flag_high_priority") color = "#faad14";
                                else if (log.action === "monitor") color = "#52c41a";

                                return (
                                  <div
                                    key={log.id}
                                    style={{
                                      marginTop: "5px",
                                      padding: "6px",
                                      borderRadius: "6px",
                                      backgroundColor: "#1e1e1e",
                                      color: "#fff",
                                      fontSize: "12px",
                                      display: "flex",
                                      justifyContent: "space-between"
                                    }}
                                  >
                                    <span>
                                      <strong style={{ color }}>{log.action.toUpperCase()}</strong>
                                      {" \u2192 "}
                                      {log.status}
                                    </span>

                                    <span style={{ opacity: 0.7 }}>
                                      {new Date(log.executed_at).toLocaleTimeString()}
                                    </span>
                                  </div>
                                );
                              })
                            ) : (
                              <div style={{ fontSize: "12px", opacity: 0.6 }}>
                                No response actions logged
                              </div>
                            )}
                          </div>

                          <div style={{ marginTop: "10px" }}>
                            <strong>Manual Actions:</strong>
                            {!canTakeAlertActions && (
                              <div style={{ fontSize: "12px", color: "#8b949e", marginTop: "4px" }}>
                                Requires elevated privileges
                              </div>
                            )}

                            <div style={{ display: "flex", gap: "8px", marginTop: "6px", flexWrap: "wrap" }}>
                              <button
                                onClick={() => executeAction(alert.id, "block_ip")}
                                onMouseOver={(e) => e.target.style.opacity = "0.85"}
                                onMouseOut={(e) => e.target.style.opacity = "1"}
                                disabled={executingActionId === alert.id}
                                title={canTakeAlertActions ? "Block IP" : "Requires elevated privileges"}
                                style={{
                                  ...getActionButtonStyle(
                                    {
                                      backgroundColor: "#ff4d4f",
                                      color: "white",
                                      border: "none",
                                      padding: "6px 10px",
                                      borderRadius: "6px",
                                      cursor: executingActionId === alert.id ? "not-allowed" : "pointer",
                                      fontWeight: "bold",
                                      opacity: executingActionId === alert.id ? 0.6 : 1,
                                      transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
                                    },
                                    "#ff4d4f"
                                  ),
                                  opacity: executingActionId === alert.id ? 0.6 : 1,
                                }}
                              >
                                {executingActionId === alert.id ? "Executing..." : canTakeAlertActions ? "Block IP" : "🔒 Block IP"}
                              </button>

                              <button
                                onClick={() => executeAction(alert.id, "flag_high_priority")}
                                onMouseOver={(e) => e.target.style.opacity = "0.85"}
                                onMouseOut={(e) => e.target.style.opacity = "1"}
                                disabled={executingActionId === alert.id}
                                title={canTakeAlertActions ? "Escalate" : "Requires elevated privileges"}
                                style={{
                                  ...getActionButtonStyle(
                                    {
                                      backgroundColor: "#faad14",
                                      color: "black",
                                      border: "none",
                                      padding: "6px 10px",
                                      borderRadius: "6px",
                                      cursor: executingActionId === alert.id ? "not-allowed" : "pointer",
                                      fontWeight: "bold",
                                      opacity: executingActionId === alert.id ? 0.6 : 1,
                                      transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
                                    },
                                    "#f59e0b"
                                  ),
                                  opacity: executingActionId === alert.id ? 0.6 : 1,
                                }}
                              >
                                {executingActionId === alert.id ? "Executing..." : canTakeAlertActions ? "Escalate" : "🔒 Escalate"}
                              </button>

                              <button
                                onClick={() => executeAction(alert.id, "monitor")}
                                onMouseOver={(e) => e.target.style.opacity = "0.85"}
                                onMouseOut={(e) => e.target.style.opacity = "1"}
                                disabled={executingActionId === alert.id}
                                title={canTakeAlertActions ? "Monitor" : "Requires elevated privileges"}
                                style={{
                                  ...getActionButtonStyle(
                                    {
                                      backgroundColor: "#52c41a",
                                      color: "white",
                                      border: "none",
                                      padding: "6px 10px",
                                      borderRadius: "6px",
                                      cursor: executingActionId === alert.id ? "not-allowed" : "pointer",
                                      fontWeight: "bold",
                                      opacity: executingActionId === alert.id ? 0.6 : 1,
                                      transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
                                    },
                                    "#22c55e"
                                  ),
                                  opacity: executingActionId === alert.id ? 0.6 : 1,
                                }}
                              >
                                {executingActionId === alert.id ? "Executing..." : canTakeAlertActions ? "Monitor" : "🔒 Monitor"}
                              </button>
                            </div>
                          </div>

                          <p style={{ ...expandedTextStyle, marginBottom: "0" }}>
                            <strong style={detailLabelTextStyle}>Created At:</strong>{" "}
                            <span style={{ ...monoCellStyle, ...detailValueTextStyle }}>
                              {alert.created_at}
                            </span>
                          </p>
                              </div>
                            </td>
                          </tr>
                        )}
                      </React.Fragment>
                      );
                    })}
                </React.Fragment>
              ))}
            </tbody>
          </table>
        </div>
        </div>
      )}
      </section>

      {statusFilter === "all" && resolvedAlerts.length > 0 && (
        <section
          style={{
            ...cardStyle,
            marginTop: "24px",
          }}
        >
          <div style={cardHeaderStyle}>
            <h2 style={cardTitleStyle}>Resolved Alerts</h2>
          </div>

          <div style={tableWrapperStyle}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={headerCellStyle}>Type</th>
                  <th style={headerCellStyle}>Severity</th>
                  <th style={headerCellStyle}>Source IP</th>
                  <th style={headerCellStyle}>Message</th>
                  <th style={headerCellStyle}>Time</th>
                </tr>
              </thead>

              <tbody>
                {resolvedAlerts.map((alert) => (
                  <tr key={alert.id}>
                    <td style={bodyCellStyle}>{alert.alert_type}</td>
                    <td style={bodyCellStyle}>{alert.severity}</td>
                    <td style={bodyCellStyle}>
                      <div>{alert.source_ip}</div>
                      <div style={{ fontSize: "12px", color: "#666", marginTop: "4px" }}>
                        {alert.city && alert.country
                          ? `${alert.city}, ${alert.country}`
                          : "Location unavailable"}
                      </div>
                    </td>
                    <td style={bodyCellStyle}>{alert.message}</td>
                    <td style={bodyCellStyle}>{alert.created_at}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {selectedAlert && (
        <div
          style={{
            position: "fixed",
            top: 0,
            right: 0,
            width: "420px",
            height: "100vh",
            backgroundColor: "#0f172a",
            color: "#fff",
            boxShadow: "-4px 0 20px rgba(0,0,0,0.35)",
            zIndex: 9998,
            borderLeft: "1px solid #1f2937",
            display: "flex",
            flexDirection: "column"
          }}
        >
          <div
            onWheel={(e) => {
              e.stopPropagation();
            }}
            style={{
              height: "100%",
              overflowY: "auto",
              overflowX: "hidden",
              WebkitOverflowScrolling: "touch",
              padding: "20px"
            }}
          >
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "center",
                marginBottom: "16px"
              }}
            >
              <h2 style={{ margin: 0, fontSize: "20px" }}>Alert Details</h2>

              <button
                onClick={() => {
                  setSelectedAlert(null);
                  setSelectedAlertId(null);
                }}
                style={{
                  background: "transparent",
                  color: "#fff",
                  border: "none",
                  fontSize: "22px",
                  cursor: "pointer"
                }}
              >
                ×
              </button>
            </div>

            <AlertDetailsPanel
              selectedAlert={selectedAlert}
              selectedAlertTimeline={selectedAlertTimeline}
              getSourceBadgeMeta={getSourceBadgeMeta}
              getTargetedAlertMeta={getTargetedAlertMeta}
              isCorrelationAlert={isCorrelationAlert}
              getCorrelationAlertTypes={getCorrelationAlertTypes}
              correlationPanelStyle={correlationPanelStyle}
              targetedAlertPanelStyle={targetedAlertPanelStyle}
              expandedLabelStyle={expandedLabelStyle}
              expandedTextStyle={expandedTextStyle}
              monoCellStyle={monoCellStyle}
              correlationListStyle={correlationListStyle}
              signalRowStyle={signalRowStyle}
              sourceTypeTextStyle={sourceTypeTextStyle}
            />
            <p><strong>Response Action:</strong> {selectedAlert.response_action || "N/A"}</p>
            <p><strong>Response Status:</strong> {selectedAlert.response_status || "N/A"}</p>

            <div style={{ marginTop: "20px" }}>
              <strong>Response Log:</strong>

              {responseLogs[selectedAlert.id] && responseLogs[selectedAlert.id].length > 0 ? (
                responseLogs[selectedAlert.id].map((log) => {
                  let color = "#999";

                  if (log.action === "block_ip") color = "#ff4d4f";
                  else if (log.action === "flag_high_priority") color = "#faad14";
                  else if (log.action === "monitor") color = "#52c41a";

                  return (
                    <div
                      key={log.id}
                      style={{
                        marginTop: "8px",
                        padding: "8px",
                        borderRadius: "8px",
                        backgroundColor: "#1e293b",
                        fontSize: "12px",
                        display: "flex",
                        justifyContent: "space-between"
                      }}
                    >
                      <span>
                        <strong style={{ color }}>{log.action.toUpperCase()}</strong>
                        {" \u2192 "}
                        {log.status}
                      </span>
                      <span style={{ opacity: 0.7 }}>
                        {new Date(log.executed_at).toLocaleTimeString()}
                      </span>
                    </div>
                  );
                })
              ) : (
                <div style={{ marginTop: "8px", fontSize: "12px", opacity: 0.7 }}>
                  No response actions logged
                </div>
              )}
            </div>

            <div style={{ marginTop: "20px" }}>
              <strong>Manual Actions:</strong>
              {!canTakeAlertActions && (
                <div style={{ marginTop: "6px", fontSize: "12px", color: "#94a3b8" }}>
                  Requires elevated privileges
                </div>
              )}

              <div style={{ display: "flex", gap: "8px", marginTop: "8px", flexWrap: "wrap" }}>
                <button
                  onClick={() => executeAction(selectedAlert.id, "block_ip")}
                  title={canTakeAlertActions ? "Block IP" : "Requires elevated privileges"}
                  style={getActionButtonStyle(
                    {
                      backgroundColor: "#ff4d4f",
                      color: "white",
                      border: "none",
                      padding: "6px 10px",
                      borderRadius: "6px",
                      cursor: "pointer",
                      fontWeight: "bold",
                      transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
                    },
                    "#ff4d4f"
                  )}
                >
                  {canTakeAlertActions ? "Block IP" : "🔒 Block IP"}
                </button>

                <button
                  onClick={() => executeAction(selectedAlert.id, "flag_high_priority")}
                  title={canTakeAlertActions ? "Escalate" : "Requires elevated privileges"}
                  style={getActionButtonStyle(
                    {
                      backgroundColor: "#faad14",
                      color: "black",
                      border: "none",
                      padding: "6px 10px",
                      borderRadius: "6px",
                      cursor: "pointer",
                      fontWeight: "bold",
                      transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
                    },
                    "#f59e0b"
                  )}
                >
                  {canTakeAlertActions ? "Escalate" : "🔒 Escalate"}
                </button>

                <button
                  onClick={() => executeAction(selectedAlert.id, "monitor")}
                  title={canTakeAlertActions ? "Monitor" : "Requires elevated privileges"}
                  style={getActionButtonStyle(
                    {
                      backgroundColor: "#52c41a",
                      color: "white",
                      border: "none",
                      padding: "6px 10px",
                      borderRadius: "6px",
                      cursor: "pointer",
                      fontWeight: "bold",
                      transition: "opacity 120ms ease, border-color 120ms ease, background-color 120ms ease",
                    },
                    "#22c55e"
                  )}
                >
                  {canTakeAlertActions ? "Monitor" : "🔒 Monitor"}
                </button>
              </div>
            </div>

            {canTakeAlertActions && (
              <div style={{ marginTop: "24px" }}>
                <strong>Analyst Notes:</strong>
                <div style={{ marginTop: "10px" }}>
                  <textarea
                    value={noteDrafts[selectedAlert.id] || ""}
                    onChange={(e) =>
                      setNoteDrafts((prev) => ({
                        ...prev,
                        [selectedAlert.id]: e.target.value,
                      }))
                    }
                    maxLength={MAX_ALERT_NOTE_LENGTH}
                    placeholder="Add investigation notes..."
                    style={{
                      width: "100%",
                      minHeight: "96px",
                      padding: "10px 12px",
                      borderRadius: "10px",
                      border: "1px solid #334155",
                      backgroundColor: "#111827",
                      color: "#e5e7eb",
                      resize: "vertical",
                      boxSizing: "border-box",
                      fontSize: "13px",
                    }}
                  />
                  <div
                    style={{
                      marginTop: "8px",
                      fontSize: "12px",
                      color: "#94a3b8",
                      textAlign: "right",
                    }}
                  >
                    {(noteDrafts[selectedAlert.id] || "").length} / {MAX_ALERT_NOTE_LENGTH}
                  </div>
                  <button
                    type="button"
                    onClick={() => addAlertNote(selectedAlert.id)}
                    disabled={addingNoteForAlertId === selectedAlert.id}
                    style={{
                      marginTop: "10px",
                      padding: "8px 12px",
                      borderRadius: "8px",
                      border: "1px solid rgba(59, 130, 246, 0.35)",
                      backgroundColor: "rgba(37, 99, 235, 0.18)",
                      color: "#bfdbfe",
                      fontWeight: "700",
                      cursor: addingNoteForAlertId === selectedAlert.id ? "not-allowed" : "pointer",
                      opacity: addingNoteForAlertId === selectedAlert.id ? 0.7 : 1,
                    }}
                  >
                    {addingNoteForAlertId === selectedAlert.id ? "Adding..." : "Add Note"}
                  </button>
                </div>

                <div style={{ marginTop: "14px" }}>
                  {loadingNotesForAlertId === selectedAlert.id ? (
                    <div style={{ fontSize: "12px", opacity: 0.7 }}>Loading notes...</div>
                  ) : alertNotes[selectedAlert.id] && alertNotes[selectedAlert.id].length > 0 ? (
                    alertNotes[selectedAlert.id].map((note) => (
                      <div
                        key={note.id}
                        style={{
                          marginTop: "8px",
                          padding: "10px 12px",
                          borderRadius: "10px",
                          backgroundColor: "#111827",
                          border: "1px solid #1f2937",
                        }}
                      >
                        <div
                          style={{
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            gap: "12px",
                            marginBottom: "6px",
                            fontSize: "12px",
                            color: "#94a3b8",
                          }}
                        >
                          <span>{note.author}</span>
                          <span>{formatNoteTimestamp(note.created_at)}</span>
                        </div>
                        <div style={{ fontSize: "13px", lineHeight: "1.55", color: "#e5e7eb" }}>
                          {note.note_text}
                        </div>
                      </div>
                    ))
                  ) : (
                    <div style={{ fontSize: "12px", opacity: 0.7 }}>
                      No notes yet. Add the first note.
                    </div>
                  )}
                </div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

export default AlertsTable;
