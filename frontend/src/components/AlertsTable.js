import React, { useState } from "react";
import AlertDetailsPanel from "./AlertDetailsPanel";
import AlertExpandedRow from "./AlertExpandedRow";
import AlertGroupHeader from "./AlertGroupHeader";
import AlertManualActions from "./AlertManualActions";
import AlertResponseLog from "./AlertResponseLog";
import AlertSidePanel from "./AlertSidePanel";
import AlertsEmptyState from "./AlertsEmptyState";
import AlertNotesPanel from "./AlertNotesPanel";
import AlertTableRow from "./AlertTableRow";
import AlertsTableHeader from "./AlertsTableHeader";
import AlertsToolbar from "./AlertsToolbar";
import AlertsToast from "./AlertsToast";
import ResolvedAlertsTable from "./ResolvedAlertsTable";
import { outcomeLabel } from "./ResponseOutcome";
import ResponseStateSummary from "./ResponseStateSummary";
import LifecycleIndependenceNotice from "./LifecycleIndependenceNotice";
import {
  correlationBadgeStyle,
  correlationListStyle,
  correlationPanelStyle,
  signalRowStyle,
  sourceTypeTextStyle,
  targetedAlertPanelStyle,
} from "./alertsTableStyles";
import {
  buildSelectedAlertTimeline,
  getCorrelationAlertTypes,
  getReputationBadgeStyle,
  getSourceBadgeMeta,
  isCorrelationAlert,
} from "../utils/alertDisplay";
import { loadAlertResponseLog } from "../services/alertResponseService";
import { getApiErrorMessage, parseJsonResponse } from "../utils/apiResponse";
import { buildSiemPath } from "../utils/siemPath";
import { formatTimestamp } from "../utils/displayFormatting";
import { formatCanonicalActionSuccess } from "../utils/responseStateLabels";
import { registryNavFromAlert } from "../utils/responseNavigation";
import { useResponseSync } from "../context/ResponseSyncContext";

// ============================================================================
// Imports / Utilities
// ============================================================================

function AlertsTable({
  alerts,
  canTakeAlertActions,
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
  displaySettings,
  onOpenResponseRegistry = null,
  onReviewIncident = null,
  totalAlerts = 0,
  pageOffset = 0,
  pageLimit = 50,
  pageEnd = 0,
  canGoToPreviousPage = false,
  canGoToNextPage = false,
  onPreviousPage = null,
  onNextPage = null,
  onRefreshAlerts = null,
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
  const { publishMutation } = useResponseSync();
  const [toastMessage, setToastMessage] = useState("");
  const [toastType, setToastType] = useState("info");
  const [selectedAlert, setSelectedAlert] = useState(null);
  const [hoveredAlertId, setHoveredAlertId] = useState(null);
  const [collapsedGroups, setCollapsedGroups] = useState({});
  const latestSelectedAlert =
    selectedAlertId !== null && selectedAlertId !== undefined
      ? alerts.find((alert) => alert.id === selectedAlertId) || selectedAlert
      : null;

  const groupHeaderCellStyle = {
    ...bodyCellStyle,
    padding: "10px 14px",
    backgroundColor: "#101722",
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
      const data = await loadAlertResponseLog(alertId);

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

      const data = await parseJsonResponse(res, []);

      if (!res.ok) {
        const errorMessage = getApiErrorMessage(data, "Unable to load notes", ["error"]);
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

  const formatNoteTimestamp = (value) => formatTimestamp(value, displaySettings, "N/A");

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

      const data = await parseJsonResponse(res, {});

      if (!res.ok) {
        const errorMessage = getApiErrorMessage(data, "Unable to add note", ["error"]);
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
    if (!canTakeAlertActions) {
      showToast("Requires analyst or super-admin privileges", "error");
      return;
    }
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
        const errorData = await parseJsonResponse(executeRes, {});
        throw new Error(
          getApiErrorMessage(errorData, "Action failed", ["message", "error"])
        );
      }
      const executeData = await parseJsonResponse(executeRes, {});

      // refresh response log for that alert
      await fetchResponseLog(alertId);

      if (typeof onRefreshAlerts === "function") {
        await onRefreshAlerts();
      }

      publishMutation(executeData?.affected_resource_keys || [], {
        action,
        alertId,
        result: executeData,
      });

      const responseOutcome = executeData?.response_outcome || null;
      if (action === "block_ip" && responseOutcome?.execution_mode === "tracking_only") {
        showToast(
          formatCanonicalActionSuccess(
            {
              ...executeData,
              message:
                `${outcomeLabel(responseOutcome)}: SIEM blocklist entry recorded. ` +
                "No firewall, provider, external, or local enforcement occurred.",
            },
            action
          )
        );
      } else {
        showToast(formatCanonicalActionSuccess(executeData, action));
      }
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
  const visibleColumns = displaySettings?.columnVisibility?.alertsTable || {
    id: true,
    type: true,
    source: true,
    sourceIp: true,
    behavior: true,
    severity: true,
    message: true,
    createdAt: true,
    action: true,
  };

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
  const selectedAlertTimeline = buildSelectedAlertTimeline(latestSelectedAlert, alerts);

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
      <AlertsToast toastMessage={toastMessage} toastType={toastType} />

      <section style={cardStyle}>
        <AlertsToolbar
          filteredAlertsCount={totalAlerts || filteredAlerts.length}
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
          <AlertsEmptyState
            emptyStateStyle={emptyStateStyle}
            emptyStateTextStyle={emptyStateTextStyle}
          />
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
              <AlertsTableHeader headerCellStyle={headerCellStyle} visibleColumns={visibleColumns} />

            <tbody>
              {groupedFilteredAlerts.map((group) => (
                <React.Fragment key={group.sourceIp}>
                  <AlertGroupHeader
                    group={group}
                    isCollapsed={collapsedGroups[group.sourceIp]}
                    onToggle={() => toggleGroup(group.sourceIp)}
                    getSeverityBadgeStyle={getSeverityBadgeStyle}
                    groupHeaderCellStyle={groupHeaderCellStyle}
                  />

                  {!collapsedGroups[group.sourceIp] &&
                    group.alerts.map((alert) => {
                      const sourceBadge = getSourceBadgeMeta(alert.source, alert.source_type);
                      const correlationAlert = isCorrelationAlert(alert);
                      const targetedAlertMeta = getTargetedAlertMeta(alert.alert_type);
                      const correlatedAlertTypes = getCorrelationAlertTypes(alert);

                      return (
                      <React.Fragment key={alert.id}>
                        <AlertTableRow
                          alert={alert}
                          sourceBadge={sourceBadge}
                          targetedAlertMeta={targetedAlertMeta}
                          isSelected={selectedAlertId === alert.id}
                          isHovered={hoveredAlertId === alert.id}
                          onHoverStart={() => setHoveredAlertId(alert.id)}
                          onHoverEnd={() => setHoveredAlertId(null)}
                          onRowClick={() => {
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
                          onResolve={(e) => handleResolve(e, alert.id)}
                          canTakeAlertActions={canTakeAlertActions}
                          getActionButtonStyle={getActionButtonStyle}
                          getSeverityBadgeStyle={getSeverityBadgeStyle}
                          formatTimestamp={(value) => formatTimestamp(value, displaySettings, "N/A")}
                          visibleColumns={visibleColumns}
                          tableRowStyle={tableRowStyle}
                          bodyCellStyle={bodyCellStyle}
                          monoCellStyle={monoCellStyle}
                        />

                        {selectedAlertId === alert.id && (
                          <AlertExpandedRow
                            alert={alert}
                            sourceBadge={sourceBadge}
                            correlationAlert={correlationAlert}
                            targetedAlertMeta={targetedAlertMeta}
                            correlatedAlertTypes={correlatedAlertTypes}
                            responseLog={responseLogs[alert.id]}
                            expandedCellStyle={expandedCellStyle}
                            expandedContentStyle={expandedContentStyle}
                            expandedLabelStyle={expandedLabelStyle}
                            expandedTextStyle={expandedTextStyle}
                            monoCellStyle={monoCellStyle}
                            canTakeAlertActions={canTakeAlertActions}
                            downloadPdfReport={downloadPdfReport}
                            executeAction={executeAction}
                            executingActionId={executingActionId}
                            getActionButtonStyle={getActionButtonStyle}
                            getReputationBadgeStyle={getReputationBadgeStyle}
                            onOpenResponseRegistry={onOpenResponseRegistry}
                            onReviewIncident={onReviewIncident}
                          />
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
        <ResolvedAlertsTable
          resolvedAlerts={resolvedAlerts}
          cardStyle={cardStyle}
          cardHeaderStyle={cardHeaderStyle}
          cardTitleStyle={cardTitleStyle}
          tableWrapperStyle={tableWrapperStyle}
          tableStyle={tableStyle}
          headerCellStyle={headerCellStyle}
          bodyCellStyle={bodyCellStyle}
        />
      )}

      {(canGoToPreviousPage || canGoToNextPage || totalAlerts > filteredAlerts.length) && (
        <div style={paginationBarStyle}>
          <span style={paginationMetaStyle}>
            Showing {filteredAlerts.length === 0 ? 0 : pageOffset + 1}-{pageEnd} of {totalAlerts}
            {" "}· Page size {pageLimit}
          </span>
          <div style={paginationControlsStyle}>
            <button
              type="button"
              onClick={onPreviousPage}
              disabled={!canGoToPreviousPage}
              style={{
                ...paginationButtonStyle,
                opacity: canGoToPreviousPage ? 1 : 0.55,
                cursor: canGoToPreviousPage ? "pointer" : "default",
              }}
            >
              Previous
            </button>
            <button
              type="button"
              onClick={onNextPage}
              disabled={!canGoToNextPage}
              style={{
                ...paginationButtonStyle,
                opacity: canGoToNextPage ? 1 : 0.55,
                cursor: canGoToNextPage ? "pointer" : "default",
              }}
            >
              Next
            </button>
          </div>
        </div>
      )}

      {latestSelectedAlert && (
        <AlertSidePanel
          onClose={() => {
            setSelectedAlert(null);
            setSelectedAlertId(null);
          }}
        >
            <AlertDetailsPanel
              selectedAlert={latestSelectedAlert}
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
              onOpenResponseRegistry={onOpenResponseRegistry}
            />
            <p><strong>Response Action:</strong> {latestSelectedAlert.response_action || "N/A"}</p>

            <ResponseStateSummary
              alert={latestSelectedAlert}
              onOpenRegistry={
                typeof onOpenResponseRegistry === "function"
                  ? () => onOpenResponseRegistry(registryNavFromAlert(latestSelectedAlert))
                  : null
              }
            />
            <LifecycleIndependenceNotice onReviewIncident={onReviewIncident} />

            <AlertResponseLog logs={responseLogs[latestSelectedAlert.id]} variant="panel" />

            <AlertManualActions
              alertId={latestSelectedAlert.id}
              sourceIp={latestSelectedAlert.source_ip}
              executeAction={executeAction}
              executingActionId={null}
              canTakeAlertActions={canTakeAlertActions}
              getActionButtonStyle={getActionButtonStyle}
              variant="panel"
            />

            {canTakeAlertActions && (
              <AlertNotesPanel
                alertId={latestSelectedAlert.id}
                noteDraft={noteDrafts[latestSelectedAlert.id] || ""}
                notes={alertNotes[latestSelectedAlert.id] || []}
                isLoadingNotes={loadingNotesForAlertId === latestSelectedAlert.id}
                isAddingNote={addingNoteForAlertId === latestSelectedAlert.id}
                onDraftChange={(value) =>
                  setNoteDrafts((prev) => ({
                    ...prev,
                    [latestSelectedAlert.id]: value,
                  }))
                }
                onAddNote={addAlertNote}
                formatNoteTimestamp={formatNoteTimestamp}
              />
            )}
        </AlertSidePanel>
      )}
    </>
  );
}

const paginationBarStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
  marginTop: "14px",
};

const paginationMetaStyle = {
  color: "#8b949e",
  fontSize: "13px",
};

const paginationControlsStyle = {
  display: "flex",
  gap: "8px",
};

const paginationButtonStyle = {
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#f0f6fc",
  borderRadius: "8px",
  padding: "8px 12px",
};

export default AlertsTable;
