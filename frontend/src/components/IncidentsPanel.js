import React, { useCallback, useEffect, useState } from "react";
import {
  loadIncidentDetail,
  loadIncidentTimeline,
  loadIncidents,
  updateIncidentStatus,
} from "../services/incidentService";
import { formatAdminTimestamp } from "../utils/adminPanelDisplay";

const INCIDENT_STATUS_FILTERS = ["all", "open", "investigating", "resolved", "closed"];
const INCIDENT_SEVERITY_FILTERS = ["all", "LOW", "MEDIUM", "HIGH", "CRITICAL"];
const INCIDENT_STATUSES = ["open", "investigating", "resolved", "closed"];
const SAFE_TIMELINE_METADATA_KEYS = [
  "incident_id",
  "alert_id",
  "playbook_id",
  "execution_id",
  "step_index",
  "action",
  "status",
  "simulated",
  "executed",
  "adapter",
  "circuit_state",
  "approval_request_id",
  "required_role",
  "source_ip",
  "severity",
];

function IncidentsPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
  canTakeAlertActions,
}) {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [selectedIncidentId, setSelectedIncidentId] = useState(null);
  const [selectedIncident, setSelectedIncident] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [pendingStatus, setPendingStatus] = useState("");
  const [updatingStatus, setUpdatingStatus] = useState(false);
  const [statusUpdateError, setStatusUpdateError] = useState("");
  const [timeline, setTimeline] = useState([]);
  const [timelineLoading, setTimelineLoading] = useState(false);
  const [timelineError, setTimelineError] = useState("");

  const loadIncidentList = useCallback(async ({ quiet = false } = {}) => {
    try {
      if (quiet) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError("");

      const data = await loadIncidents({
        status: statusFilter,
        severity: severityFilter,
      });
      setIncidents(Array.isArray(data?.incidents) ? data.incidents : []);
    } catch (err) {
      setError(err.message || "Unable to load incidents.");
      if (!quiet) {
        setIncidents([]);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [statusFilter, severityFilter]);

  const loadDetail = useCallback(async (incidentId) => {
    if (!incidentId) return;
    try {
      setDetailLoading(true);
      setDetailError("");
      setStatusUpdateError("");

      const data = await loadIncidentDetail(incidentId);
      const incident = data?.incident || null;
      setSelectedIncident(incident);
      setPendingStatus(incident?.status || "");
    } catch (err) {
      setSelectedIncident(null);
      setDetailError(err.message || "Unable to load incident.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadTimeline = useCallback(async (incidentId) => {
    if (!incidentId) return;
    try {
      setTimelineLoading(true);
      setTimelineError("");

      const data = await loadIncidentTimeline(incidentId);
      setTimeline(Array.isArray(data?.timeline) ? data.timeline : []);
    } catch (err) {
      setTimeline([]);
      setTimelineError(err.message || "Unable to load incident timeline.");
    } finally {
      setTimelineLoading(false);
    }
  }, []);

  const handleStatusUpdate = useCallback(async () => {
    if (!selectedIncidentId || !selectedIncident || !pendingStatus) return;
    if (pendingStatus === selectedIncident.status) return;

    try {
      setUpdatingStatus(true);
      setStatusUpdateError("");
      await updateIncidentStatus(selectedIncidentId, pendingStatus);
      await loadDetail(selectedIncidentId);
      await loadTimeline(selectedIncidentId);
      await loadIncidentList({ quiet: true });
    } catch (err) {
      setStatusUpdateError(err.message || "Unable to update incident status.");
    } finally {
      setUpdatingStatus(false);
    }
  }, [
    loadDetail,
    loadTimeline,
    loadIncidentList,
    pendingStatus,
    selectedIncident,
    selectedIncidentId,
  ]);

  const handleCloseDetail = useCallback(() => {
    setSelectedIncidentId(null);
    setSelectedIncident(null);
    setDetailError("");
    setDetailLoading(false);
    setStatusUpdateError("");
    setPendingStatus("");
    setTimeline([]);
    setTimelineError("");
    setTimelineLoading(false);
  }, []);

  useEffect(() => {
    loadIncidentList();
  }, [loadIncidentList]);

  useEffect(() => {
    if (selectedIncidentId) {
      setTimeline([]);
      setTimelineError("");
      loadDetail(selectedIncidentId);
      loadTimeline(selectedIncidentId);
    }
  }, [loadDetail, loadTimeline, selectedIncidentId]);

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>SOAR</p>
          <h2 style={cardTitleStyle}>Incident Visibility</h2>
          <p style={cardSubtitleStyle}>
            Case-level view of detection alerts grouped into incidents.
          </p>
        </div>
        <div style={controlsStyle}>
          <label style={filterWrapperStyle}>
            <span style={filterLabelStyle}>Status</span>
            <select
              value={statusFilter}
              onChange={(event) => setStatusFilter(event.target.value)}
              style={selectStyle}
            >
              {INCIDENT_STATUS_FILTERS.map((status) => (
                <option key={status} value={status}>
                  {formatLabel(status)}
                </option>
              ))}
            </select>
          </label>
          <label style={filterWrapperStyle}>
            <span style={filterLabelStyle}>Severity</span>
            <select
              value={severityFilter}
              onChange={(event) => setSeverityFilter(event.target.value)}
              style={selectStyle}
            >
              {INCIDENT_SEVERITY_FILTERS.map((severity) => (
                <option key={severity} value={severity}>
                  {formatLabel(severity)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => loadIncidentList({ quiet: true })}
            disabled={loading || refreshing}
            style={{
              ...refreshButtonStyle,
              opacity: loading || refreshing ? 0.65 : 1,
              cursor: loading || refreshing ? "default" : "pointer",
            }}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
        </div>
      </div>

      <div style={panelContentStyle}>
        {error ? (
          <div style={errorStateStyle}>
            <span>Error: {error}</span>
            <button
              type="button"
              onClick={() => loadIncidentList({ quiet: false })}
              style={retryButtonStyle}
            >
              Retry
            </button>
          </div>
        ) : null}

        {loading ? (
          <p style={emptyTextStyle}>Loading incidents...</p>
        ) : incidents.length === 0 ? (
          <p style={emptyTextStyle}>No incidents found.</p>
        ) : (
          <div style={tableSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>Incidents</span>
              <span style={tableMetaCountStyle}>{incidents.length}</span>
            </div>
            <div style={tableWrapperStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={{ ...headerCellStyle, width: "8%" }}>ID</th>
                    <th style={{ ...headerCellStyle, width: "28%" }}>Title</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Severity</th>
                    <th style={{ ...headerCellStyle, width: "10%" }}>Priority</th>
                    <th style={{ ...headerCellStyle, width: "14%" }}>Status</th>
                    <th style={{ ...headerCellStyle, width: "14%" }}>Source IP</th>
                    <th style={{ ...headerCellStyle, width: "14%" }}>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {incidents.map((incident) => (
                    <tr
                      key={incident.id}
                      onClick={() => setSelectedIncidentId(incident.id)}
                      style={{
                        ...rowStyle,
                        ...(selectedIncidentId === incident.id ? selectedRowStyle : null),
                      }}
                    >
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{incident.id}</td>
                      <td style={bodyCellStyle} title={incident.title || ""}>
                        {truncateText(incident.title || "Untitled incident", 44)}
                      </td>
                      <td style={bodyCellStyle}>
                        <span style={{ ...badgeStyle, ...getSeverityBadgeStyle(incident.severity) }}>
                          {formatSeverity(incident.severity)}
                        </span>
                      </td>
                      <td style={bodyCellStyle}>{incident.priority || "N/A"}</td>
                      <td style={bodyCellStyle}>
                        <span style={{ ...badgeStyle, ...getStatusBadgeStyle(incident.status) }}>
                          {formatLabel(incident.status)}
                        </span>
                      </td>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                        {incident.source_ip || <span style={mutedTextStyle}>N/A</span>}
                      </td>
                      <td style={{ ...bodyCellStyle, ...timeCellStyle }} title={incident.created_at || ""}>
                        {formatTimestamp(incident.created_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {selectedIncidentId ? (
          <div style={detailPanelStyle}>
            <div style={detailHeaderStyle}>
              <h3 style={detailTitleStyle}>
                {selectedIncident
                  ? `Incident #${selectedIncident.id} - ${selectedIncident.title}`
                  : "Incident Detail"}
              </h3>
              <button type="button" style={detailCloseButtonStyle} onClick={handleCloseDetail}>
                Close
              </button>
            </div>

            {detailLoading ? (
              <p style={emptyTextStyle}>Loading incident...</p>
            ) : detailError ? (
              <div style={errorStateStyle}>Error loading incident: {detailError}</div>
            ) : selectedIncident ? (
              <>
                <div style={detailGridStyle}>
                  <DetailField label="Severity" value={formatSeverity(selectedIncident.severity)} />
                  <DetailField label="Priority" value={selectedIncident.priority || "N/A"} />
                  <DetailField label="Status" value={formatLabel(selectedIncident.status)} />
                  <DetailField label="Source IP" value={selectedIncident.source_ip || "N/A"} mono />
                  <DetailField label="Created" value={formatTimestamp(selectedIncident.created_at)} />
                  <DetailField
                    label="Resolved"
                    value={selectedIncident.resolved_at ? formatTimestamp(selectedIncident.resolved_at) : "—"}
                  />
                </div>

                <div style={linkedAlertsSectionStyle}>
                  <div style={tableMetaStyle}>
                    <span style={tableMetaLabelStyle}>Linked Alerts</span>
                    <span style={tableMetaCountStyle}>
                      {Array.isArray(selectedIncident.alerts) ? selectedIncident.alerts.length : 0}
                    </span>
                  </div>
                  {Array.isArray(selectedIncident.alerts) && selectedIncident.alerts.length > 0 ? (
                    <div style={tableWrapperStyle}>
                      <table style={detailTableStyle}>
                        <thead>
                          <tr>
                            <th style={headerCellStyle}>Alert ID</th>
                            <th style={headerCellStyle}>Type</th>
                            <th style={headerCellStyle}>Severity</th>
                            <th style={headerCellStyle}>Status</th>
                            <th style={headerCellStyle}>Linked At</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedIncident.alerts.map((alert) => (
                            <tr key={alert.alert_id} style={rowStyle}>
                              <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{alert.alert_id}</td>
                              <td style={bodyCellStyle}>{alert.alert_type || "N/A"}</td>
                              <td style={bodyCellStyle}>{formatSeverity(alert.severity)}</td>
                              <td style={bodyCellStyle}>{formatLabel(alert.status)}</td>
                              <td style={{ ...bodyCellStyle, ...timeCellStyle }}>
                                {formatTimestamp(alert.linked_at)}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p style={emptyTextStyle}>No linked alerts.</p>
                  )}
                </div>

                <div style={timelineSectionStyle}>
                  <div style={tableMetaStyle}>
                    <span style={tableMetaLabelStyle}>SOAR Timeline</span>
                    <span style={tableMetaCountStyle}>{timeline.length}</span>
                  </div>
                  <p style={timelineNoticeStyle}>
                    Timeline is read-only. SOAR playbook and adapter events are
                    simulation-only unless explicitly marked otherwise by the backend.
                  </p>
                  {timelineLoading ? (
                    <p style={emptyTextStyle}>Loading timeline...</p>
                  ) : timelineError ? (
                    <div style={timelineErrorStyle}>
                      <span>Error loading timeline: {timelineError}</span>
                      <button
                        type="button"
                        onClick={() => loadTimeline(selectedIncidentId)}
                        style={retryButtonStyle}
                      >
                        Retry timeline
                      </button>
                    </div>
                  ) : timeline.length === 0 ? (
                    <p style={emptyTextStyle}>No SOAR timeline events found for this incident.</p>
                  ) : (
                    <ol style={timelineListStyle} aria-label="SOAR timeline events">
                      {timeline.map((event, index) => (
                        <TimelineEvent
                          key={getTimelineEventKey(event, index)}
                          event={event}
                        />
                      ))}
                    </ol>
                  )}
                </div>

                {canTakeAlertActions ? (
                  <div style={statusControlStyle}>
                    <label style={filterWrapperStyle}>
                      <span style={filterLabelStyle}>Update status:</span>
                      <select
                        value={pendingStatus}
                        onChange={(event) => setPendingStatus(event.target.value)}
                        style={selectStyle}
                      >
                        {INCIDENT_STATUSES.map((status) => (
                          <option key={status} value={status}>
                            {formatLabel(status)}
                          </option>
                        ))}
                      </select>
                    </label>
                    <button
                      type="button"
                      onClick={handleStatusUpdate}
                      disabled={updatingStatus || pendingStatus === selectedIncident.status}
                      style={{
                        ...updateButtonStyle,
                        opacity:
                          updatingStatus || pendingStatus === selectedIncident.status ? 0.65 : 1,
                        cursor:
                          updatingStatus || pendingStatus === selectedIncident.status
                            ? "default"
                            : "pointer",
                      }}
                    >
                      {updatingStatus ? "Updating..." : "Update Status"}
                    </button>
                    {statusUpdateError ? (
                      <div style={inlineErrorStyle}>{statusUpdateError}</div>
                    ) : null}
                  </div>
                ) : null}
              </>
            ) : null}
          </div>
        ) : null}
      </div>
    </section>
  );
}

const formatLabel = (value) =>
  String(value || "unknown").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());

const formatSeverity = (value) => String(value || "N/A").toUpperCase();

const formatTimestamp = (value) => formatAdminTimestamp(value, "N/A");

const formatEventType = (value) => {
  const labels = {
    incident_created: "Incident created",
    alert_linked: "Alert linked",
    alert_created: "Alert created",
    playbook_execution_created: "Playbook execution created",
    playbook_execution_started: "Playbook execution started",
    playbook_execution_status_changed: "Playbook status changed",
    playbook_step_started: "Playbook step started",
    playbook_step_completed: "Playbook step completed",
    playbook_step_failed: "Playbook step failed",
    playbook_step_skipped: "Playbook step skipped",
    playbook_adapter_simulated: "Simulated adapter step",
    approval_requested: "Approval requested",
    approval_approved: "Approval approved",
    approval_denied: "Approval denied",
    approval_expired: "Approval expired",
    approval_resumed: "Approval resumed",
    audit_event: "Audit event",
  };
  const normalized = String(value || "timeline_event");
  return labels[normalized] || formatLabel(normalized);
};

const formatMetadataValue = (value) => {
  if (value === true) return "true";
  if (value === false) return "false";
  if (value === null || value === undefined || value === "") return "N/A";
  return String(value);
};

const getSafeMetadataEntries = (metadata) => {
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return [];
  return SAFE_TIMELINE_METADATA_KEYS
    .filter((key) => Object.prototype.hasOwnProperty.call(metadata, key))
    .map((key) => [key, formatMetadataValue(metadata[key])]);
};

const getTimelineEventKey = (event, index) => {
  const timestamp = event?.timestamp || "no-time";
  const type = event?.event_type || "event";
  const source = event?.source || "source";
  const sourceId = event?.source_id || index;
  return `${timestamp}-${type}-${source}-${sourceId}-${index}`;
};

const truncateText = (value, maxLength) => {
  const text = String(value || "");
  if (text.length <= maxLength) return text;
  return `${text.slice(0, maxLength)}...`;
};

const getSeverityBadgeStyle = (severity) => {
  const normalized = String(severity || "").toUpperCase();
  if (normalized === "CRITICAL") return criticalBadgeStyle;
  if (normalized === "HIGH") return highBadgeStyle;
  if (normalized === "MEDIUM") return mediumBadgeStyle;
  if (normalized === "LOW") return lowBadgeStyle;
  return neutralBadgeStyle;
};

const getStatusBadgeStyle = (status) => {
  if (status === "open") return openBadgeStyle;
  if (status === "investigating") return investigatingBadgeStyle;
  if (status === "resolved") return resolvedBadgeStyle;
  if (status === "closed") return closedBadgeStyle;
  return neutralBadgeStyle;
};

const panelContentStyle = {
  padding: "24px 20px 22px",
};

const sectionLabelStyle = {
  margin: "0 0 8px 0",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.14em",
  textTransform: "uppercase",
};

const controlsStyle = {
  display: "flex",
  alignItems: "flex-end",
  gap: "12px",
  flexWrap: "wrap",
};

const filterWrapperStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
};

const refreshButtonStyle = {
  minHeight: "40px",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.14)",
  color: "#93c5fd",
  fontSize: "13px",
  fontWeight: "700",
};

const retryButtonStyle = {
  marginLeft: "12px",
  minHeight: "30px",
  padding: "6px 10px",
  borderRadius: "8px",
  border: "1px solid rgba(239, 68, 68, 0.38)",
  backgroundColor: "rgba(239, 68, 68, 0.10)",
  color: "#fca5a5",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const tableSectionStyle = {
  marginTop: "4px",
};

const tableMetaStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  marginBottom: "12px",
};

const tableMetaLabelStyle = {
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const tableMetaCountStyle = {
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
};

const tableWrapperStyle = {
  overflowX: "auto",
};

const tableStyle = {
  width: "100%",
  minWidth: "980px",
  borderCollapse: "collapse",
};

const detailTableStyle = {
  width: "100%",
  minWidth: "760px",
  borderCollapse: "collapse",
};

const headerCellStyle = {
  textAlign: "left",
  padding: "12px 14px",
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  borderBottom: "1px solid #30363d",
};

const bodyCellStyle = {
  padding: "14px",
  color: "#e6edf3",
  borderBottom: "1px solid #30363d",
  fontSize: "13px",
  verticalAlign: "middle",
};

const rowStyle = {
  backgroundColor: "#161b22",
  cursor: "pointer",
};

const selectedRowStyle = {
  backgroundColor: "rgba(31, 111, 235, 0.14)",
};

const monoCellStyle = {
  fontFamily: "'Courier New', monospace",
  fontSize: "12px",
  color: "#d29922",
};

const timeCellStyle = {
  color: "#8b949e",
  whiteSpace: "nowrap",
};

const mutedTextStyle = {
  color: "#8b949e",
};

const emptyTextStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "14px",
};

const errorStateStyle = {
  marginBottom: "16px",
  padding: "10px 12px",
  borderRadius: "8px",
  fontSize: "13px",
  fontWeight: "600",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
  color: "#fca5a5",
};

const inlineErrorStyle = {
  color: "#fca5a5",
  fontSize: "13px",
  fontWeight: "600",
};

const badgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  width: "fit-content",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const criticalBadgeStyle = {
  color: "#fca5a5",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
};

const highBadgeStyle = {
  color: "#fb923c",
  backgroundColor: "rgba(251, 146, 60, 0.12)",
  border: "1px solid rgba(251, 146, 60, 0.28)",
};

const mediumBadgeStyle = {
  color: "#f5d487",
  backgroundColor: "rgba(217, 164, 65, 0.14)",
  border: "1px solid rgba(217, 164, 65, 0.32)",
};

const lowBadgeStyle = {
  color: "#7ee787",
  backgroundColor: "rgba(63, 185, 80, 0.12)",
  border: "1px solid rgba(63, 185, 80, 0.28)",
};

const openBadgeStyle = {
  color: "#93c5fd",
  backgroundColor: "rgba(59, 130, 246, 0.12)",
  border: "1px solid rgba(59, 130, 246, 0.28)",
};

const investigatingBadgeStyle = {
  color: "#f5d487",
  backgroundColor: "rgba(217, 164, 65, 0.14)",
  border: "1px solid rgba(217, 164, 65, 0.32)",
};

const resolvedBadgeStyle = {
  color: "#7ee787",
  backgroundColor: "rgba(63, 185, 80, 0.12)",
  border: "1px solid rgba(63, 185, 80, 0.28)",
};

const closedBadgeStyle = {
  color: "#c9d1d9",
  backgroundColor: "rgba(139, 148, 158, 0.12)",
  border: "1px solid rgba(139, 148, 158, 0.26)",
};

const neutralBadgeStyle = {
  color: "#c9d1d9",
  backgroundColor: "#161b22",
  border: "1px solid #30363d",
};

const detailPanelStyle = {
  marginTop: "18px",
  border: "1px solid #30363d",
  borderRadius: "10px",
  backgroundColor: "#0d1117",
  padding: "14px",
};

const detailHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  marginBottom: "12px",
};

const detailTitleStyle = {
  margin: 0,
  color: "#e6edf3",
  fontSize: "15px",
  fontWeight: "700",
};

const detailCloseButtonStyle = {
  minHeight: "30px",
  padding: "6px 10px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const detailGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "12px",
};

const detailFieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
};

const detailLabelStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const detailValueStyle = {
  color: "#e6edf3",
  fontSize: "13px",
};

const detailMonoValueStyle = {
  fontFamily: "'Courier New', monospace",
  color: "#d29922",
  fontSize: "12px",
};

const linkedAlertsSectionStyle = {
  marginTop: "18px",
  paddingTop: "16px",
  borderTop: "1px solid #21262d",
};

const timelineSectionStyle = {
  marginTop: "18px",
  paddingTop: "16px",
  borderTop: "1px solid #21262d",
};

const timelineNoticeStyle = {
  margin: "0 0 12px 0",
  color: "#8b949e",
  fontSize: "13px",
  lineHeight: 1.5,
};

const timelineErrorStyle = {
  ...errorStateStyle,
  marginBottom: 0,
};

const timelineListStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "10px",
  maxHeight: "420px",
  overflowY: "auto",
  margin: 0,
  padding: 0,
  listStyle: "none",
};

const timelineItemStyle = {
  padding: "12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
};

const timelineItemHeaderStyle = {
  display: "flex",
  alignItems: "baseline",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
  marginBottom: "6px",
};

const timelineEventTypeStyle = {
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "700",
};

const timelineTimestampStyle = {
  color: "#8b949e",
  fontSize: "12px",
  fontFamily: "'Courier New', monospace",
};

const timelineSourceStyle = {
  margin: "0 0 4px 0",
  color: "#93c5fd",
  fontSize: "12px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
};

const timelineTitleStyle = {
  margin: "0 0 4px 0",
  color: "#c9d1d9",
  fontSize: "13px",
  fontWeight: "700",
};

const timelineSummaryStyle = {
  margin: 0,
  color: "#c9d1d9",
  fontSize: "13px",
  lineHeight: 1.5,
};

const timelineMetadataStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "6px",
  marginTop: "10px",
};

const timelineMetadataChipStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "4px",
  maxWidth: "100%",
  padding: "4px 7px",
  borderRadius: "999px",
  border: "1px solid #30363d",
  color: "#c9d1d9",
  backgroundColor: "#0d1117",
  fontSize: "11px",
  fontFamily: "'Courier New', monospace",
  overflowWrap: "anywhere",
};

const timelineMetadataKeyStyle = {
  color: "#8b949e",
};

const statusControlStyle = {
  display: "flex",
  alignItems: "flex-end",
  gap: "12px",
  flexWrap: "wrap",
  marginTop: "18px",
  paddingTop: "16px",
  borderTop: "1px solid #21262d",
};

const updateButtonStyle = {
  minHeight: "40px",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.14)",
  color: "#93c5fd",
  fontSize: "13px",
  fontWeight: "700",
};

function DetailField({ label, value, mono = false }) {
  return (
    <div style={detailFieldStyle}>
      <span style={detailLabelStyle}>{label}</span>
      <span style={{ ...detailValueStyle, ...(mono ? detailMonoValueStyle : null) }}>
        {value}
      </span>
    </div>
  );
}

function TimelineEvent({ event }) {
  const metadataEntries = getSafeMetadataEntries(event?.metadata);
  return (
    <li style={timelineItemStyle}>
      <div style={timelineItemHeaderStyle}>
        <span style={timelineEventTypeStyle}>{formatEventType(event?.event_type)}</span>
        <time style={timelineTimestampStyle} dateTime={event?.timestamp || undefined}>
          {formatTimestamp(event?.timestamp)}
        </time>
      </div>
      <p style={timelineSourceStyle}>{formatLabel(event?.source || "timeline")}</p>
      {event?.title ? <p style={timelineTitleStyle}>{event.title}</p> : null}
      <p style={timelineSummaryStyle}>{event?.summary || "No summary provided."}</p>
      {metadataEntries.length > 0 ? (
        <div style={timelineMetadataStyle} aria-label="Timeline metadata">
          {metadataEntries.map(([key, value]) => (
            <span key={key} style={timelineMetadataChipStyle}>
              <span style={timelineMetadataKeyStyle}>{key}:</span>
              <span>{value}</span>
            </span>
          ))}
        </div>
      ) : null}
    </li>
  );
}

export default IncidentsPanel;
