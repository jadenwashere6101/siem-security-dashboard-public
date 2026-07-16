import React, { useCallback, useEffect, useState } from "react";
import {
  loadIncidentDetail,
  loadIncidentTimeline,
  loadIncidents,
  updateIncidentStatus,
} from "../services/incidentService";
import { listIncidentNotificationDeliveries } from "../services/notificationDeliveryService";
import { formatTimestamp } from "../utils/displayFormatting";
import { getOperationalHistoryBadge, getOperationalHistoryDescription } from "../utils/operationalHistory";
import { getSeverityBadgeStyle } from "../utils/severityDisplay";
import OperationalScopeToggle, {
  OPERATIONAL_SCOPE_SINCE_TUNING,
} from "./OperationalScopeToggle";
import {
  MasterDetailLayout,
  MasterDetailMaster,
  MasterDetailPane,
  useMasterDetailFocus,
} from "./MasterDetailLayout";

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
const UNSAFE_DELIVERY_METADATA_KEY_SNIPPETS = [
  "webhook",
  "token",
  "secret",
  "password",
  "authorization",
  "cookie",
  "bearer",
  "api_key",
  "apikey",
  "raw_payload",
  "raw_response",
  "header",
];
const DELIVERY_HISTORY_DISCLAIMER =
  // spec: SPEC-NOTIFY-001
  "Delivery history shows recorded notification attempts (simulation or real mode). " +
  "It is operational evidence only; it does not prove that a human saw the message.";

function IncidentsPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
  canTakeAlertActions,
  displaySettings,
  onOpenResponseRegistry = null,
  initialIncidentRequest = null,
  onViewRelatedAlerts = null,
}) {
  const [incidents, setIncidents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [severityFilter, setSeverityFilter] = useState("all");
  const [operationalScope, setOperationalScope] = useState(OPERATIONAL_SCOPE_SINCE_TUNING);
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
  const [deliveryAttempts, setDeliveryAttempts] = useState([]);
  const [deliveryLoading, setDeliveryLoading] = useState(false);
  const [deliveryError, setDeliveryError] = useState("");
  const { detailRef, rememberTrigger, restoreTriggerFocus } = useMasterDetailFocus(
    selectedIncidentId
  );

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
        operationalScope,
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
  }, [operationalScope, severityFilter, statusFilter]);

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

  const loadNotificationDeliveries = useCallback(async (incidentId) => {
    if (!incidentId) return;
    try {
      setDeliveryLoading(true);
      setDeliveryError("");

      const data = await listIncidentNotificationDeliveries(incidentId, { limit: 50 });
      setDeliveryAttempts(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      setDeliveryAttempts([]);
      setDeliveryError(err.message || "Unable to load notification deliveries.");
    } finally {
      setDeliveryLoading(false);
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
    restoreTriggerFocus();
    setSelectedIncidentId(null);
    setSelectedIncident(null);
    setDetailError("");
    setDetailLoading(false);
    setStatusUpdateError("");
    setPendingStatus("");
    setTimeline([]);
    setTimelineError("");
    setTimelineLoading(false);
    setDeliveryAttempts([]);
    setDeliveryError("");
    setDeliveryLoading(false);
  }, [restoreTriggerFocus]);

  const handleSelectIncident = useCallback((incidentId, trigger) => {
    rememberTrigger(trigger);
    setSelectedIncidentId(incidentId);
  }, [rememberTrigger]);

  useEffect(() => {
    loadIncidentList();
  }, [loadIncidentList]);

  useEffect(() => {
    if (selectedIncidentId) {
      setTimeline([]);
      setTimelineError("");
      setDeliveryAttempts([]);
      setDeliveryError("");
      loadDetail(selectedIncidentId);
      loadTimeline(selectedIncidentId);
      loadNotificationDeliveries(selectedIncidentId);
    }
  }, [loadDetail, loadNotificationDeliveries, loadTimeline, selectedIncidentId]);

  useEffect(() => {
    if (!initialIncidentRequest?.incidentId) return;
    setSelectedIncidentId(Number(initialIncidentRequest.incidentId));
  }, [initialIncidentRequest]);

  const rowsPerPage = displaySettings?.rowsPerPage ?? "all";
  const limitedIncidents =
    rowsPerPage === "all" ? incidents : incidents.slice(0, Number(rowsPerPage));
  const visibleColumns = displaySettings?.columnVisibility?.incidentsTable || {
    id: true,
    title: true,
    severity: true,
    priority: true,
    status: true,
    sourceIp: true,
    created: true,
  };

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
          <div style={filterWrapperStyle}>
            <OperationalScopeToggle
              value={operationalScope}
              onChange={setOperationalScope}
              label="Operational scope"
              compact
            />
          </div>
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

        <MasterDetailLayout
          detailOpen={selectedIncidentId !== null}
          ariaLabel="Incident list and selected incident detail"
        >
          <MasterDetailMaster ariaLabel="Incidents">
        {loading ? (
          <p style={emptyTextStyle}>Loading incidents...</p>
        ) : incidents.length === 0 ? (
          <p style={emptyTextStyle}>No incidents found.</p>
        ) : (
          <div style={tableSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>Incidents</span>
              <span style={tableMetaCountStyle}>{limitedIncidents.length}</span>
            </div>
            <div style={tableWrapperStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={{ ...headerCellStyle, width: "8%" }}>ID</th>
                    {visibleColumns.title && <th style={{ ...headerCellStyle, width: "28%" }}>Title</th>}
                    {visibleColumns.severity && (
                      <th style={{ ...headerCellStyle, width: "12%" }}>Severity</th>
                    )}
                    {visibleColumns.priority && (
                      <th style={{ ...headerCellStyle, width: "10%" }}>Priority</th>
                    )}
                    {visibleColumns.status && (
                      <th style={{ ...headerCellStyle, width: "14%" }}>Status</th>
                    )}
                    {visibleColumns.sourceIp && (
                      <th style={{ ...headerCellStyle, width: "14%" }}>Source IP</th>
                    )}
                    {visibleColumns.created && (
                      <th style={{ ...headerCellStyle, width: "14%" }}>Created</th>
                    )}
                  </tr>
                </thead>
                <tbody>
                  {limitedIncidents.map((incident) => (
                    <tr
                      key={incident.id}
                      tabIndex={0}
                      aria-selected={selectedIncidentId === incident.id}
                      onClick={(event) => handleSelectIncident(incident.id, event.currentTarget)}
                      onKeyDown={(event) => {
                        if (event.key === "Enter" || event.key === " ") {
                          event.preventDefault();
                          handleSelectIncident(incident.id, event.currentTarget);
                        }
                      }}
                      style={{
                        ...rowStyle,
                        ...(selectedIncidentId === incident.id ? selectedRowStyle : null),
                      }}
                    >
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{incident.id}</td>
                      {visibleColumns.title && <td style={bodyCellStyle} title={incident.title || ""}>
                        <div>{truncateText(incident.title || "Untitled incident", 44)}</div>
                        {getOperationalHistoryBadge(incident) ? (
                          <div style={legacyBadgeRowStyle}>
                            <span style={legacyBadgeStyle}>{getOperationalHistoryBadge(incident)}</span>
                          </div>
                        ) : null}
                      </td>}
                      {visibleColumns.severity && <td style={bodyCellStyle}>
                        <span
                          style={{
                            ...badgeStyle,
                            ...getSeverityBadgeStyle(
                              incident.severity,
                              displaySettings?.severityColorPreset
                            ),
                          }}
                        >
                          {formatSeverity(incident.severity)}
                        </span>
                      </td>}
                      {visibleColumns.priority && <td style={bodyCellStyle}>{incident.priority || "N/A"}</td>}
                      {visibleColumns.status && <td style={bodyCellStyle}>
                        <span style={{ ...badgeStyle, ...getStatusBadgeStyle(incident.status) }}>
                          {formatLabel(incident.status)}
                        </span>
                      </td>}
                      {visibleColumns.sourceIp && <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                        {incident.source_ip || <span style={mutedTextStyle}>N/A</span>}
                      </td>}
                      {visibleColumns.created && <td style={{ ...bodyCellStyle, ...timeCellStyle }} title={incident.created_at || ""}>
                        {formatTimestamp(incident.created_at, displaySettings, "N/A")}
                      </td>}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
          </MasterDetailMaster>

        {selectedIncidentId ? (
          <MasterDetailPane
            ref={detailRef}
            ariaLabel="Selected incident detail"
          >
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
                  {typeof onOpenResponseRegistry === "function" && selectedIncident.source_ip ? (
                    <button
                      type="button"
                      onClick={() =>
                        onOpenResponseRegistry({
                          sourceIp: selectedIncident.source_ip,
                          relatedIncidentId: selectedIncident.id,
                        })
                      }
                      style={{
                        marginTop: "8px",
                        background: "transparent",
                        border: "1px solid #388bfd",
                        color: "#58a6ff",
                        borderRadius: "6px",
                        padding: "4px 8px",
                        cursor: "pointer",
                        fontSize: "12px",
                      }}
                    >
                      Open in Response Registry
                    </button>
                  ) : null}
                  {typeof onViewRelatedAlerts === "function" && selectedIncident.source_ip ? (
                    <button
                      type="button"
                      onClick={() => onViewRelatedAlerts(selectedIncident.source_ip)}
                      style={{
                        marginTop: "8px",
                        marginLeft: "8px",
                        background: "transparent",
                        border: "1px solid #30363d",
                        color: "#c9d1d9",
                        borderRadius: "6px",
                        padding: "4px 8px",
                        cursor: "pointer",
                        fontSize: "12px",
                      }}
                    >
                      View related alerts
                    </button>
                  ) : null}
                  <DetailField
                    label="Created"
                    value={formatTimestamp(selectedIncident.created_at, displaySettings, "N/A")}
                  />
                  {getOperationalHistoryBadge(selectedIncident) ? (
                    <DetailField
                      label="Operational History"
                      value={`${getOperationalHistoryBadge(selectedIncident)} · ${getOperationalHistoryDescription(selectedIncident)}`}
                    />
                  ) : null}
                  <DetailField
                    label="Resolved"
                    value={
                      selectedIncident.resolved_at
                        ? formatTimestamp(selectedIncident.resolved_at, displaySettings, "N/A")
                        : "—"
                    }
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
                                {formatTimestamp(alert.linked_at, displaySettings, "N/A")}
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
                    Timeline is read-only. Each event's mode (internal, tracking-only,
                    simulated, or real) is determined by the backend and shown per event.
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
                          displaySettings={displaySettings}
                        />
                      ))}
                    </ol>
                  )}
                </div>

                <div style={deliverySectionStyle}>
                  <div style={tableMetaStyle}>
                    <span style={tableMetaLabelStyle}>Notification Delivery History</span>
                    <span style={tableMetaCountStyle}>{deliveryAttempts.length}</span>
                  </div>
                  <p style={timelineNoticeStyle}>{DELIVERY_HISTORY_DISCLAIMER}</p>
                  {deliveryLoading ? (
                    <p style={emptyTextStyle}>Loading notification deliveries...</p>
                  ) : deliveryError ? (
                    <div style={timelineErrorStyle}>
                      <span>Error loading notification deliveries: {deliveryError}</span>
                      <button
                        type="button"
                        onClick={() => loadNotificationDeliveries(selectedIncidentId)}
                        style={retryButtonStyle}
                      >
                        Retry deliveries
                      </button>
                    </div>
                  ) : deliveryAttempts.length === 0 ? (
                    <p style={emptyTextStyle}>No notification delivery attempts found for this incident.</p>
                  ) : (
                    <div style={deliveryListStyle} aria-label="Notification delivery history">
                      {deliveryAttempts.map((attempt) => (
                        <DeliveryAttempt
                          key={attempt.id || attempt.correlation_id}
                          attempt={attempt}
                          displaySettings={displaySettings}
                        />
                      ))}
                    </div>
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
          </MasterDetailPane>
        ) : null}
        </MasterDetailLayout>
      </div>
    </section>
  );
}

const formatLabel = (value) =>
  String(value || "unknown").replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());

const formatSeverity = (value) => String(value || "N/A").toUpperCase();

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
    playbook_adapter_real: "Real adapter step",
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

const deliveryMetadataKeyIsSafe = (key) => {
  if (!key || typeof key !== "string") return false;
  const normalized = key.toLowerCase();
  if (normalized.includes("://")) return false;
  return !UNSAFE_DELIVERY_METADATA_KEY_SNIPPETS.some((snippet) =>
    normalized.includes(snippet)
  );
};

const formatDeliveryValue = (value, emptyValue = "N/A") => {
  if (value === true) return "Yes";
  if (value === false) return "No";
  if (value === null || value === undefined || value === "") return emptyValue;
  if (typeof value === "string" && /https?:\/\//i.test(value)) return "[REDACTED_URL]";
  if (typeof value === "object") return JSON.stringify(value);
  return String(value);
};

const getSafeDeliveryMetadataEntries = (metadata) => {
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) return [];
  return Object.entries(metadata).filter(([key]) => deliveryMetadataKeyIsSafe(key));
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

const deliverySectionStyle = {
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

const deliveryListStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const deliveryCardStyle = {
  padding: "12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
};

const deliveryCardHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "10px",
  flexWrap: "wrap",
  marginBottom: "12px",
};

const deliveryTitleStyle = {
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "700",
};

const deliveryModeStyle = {
  color: "#93c5fd",
  fontSize: "12px",
  fontWeight: "700",
};

const deliveryGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))",
  gap: "12px",
};

const deliveryMetadataStyle = {
  marginTop: "12px",
  paddingTop: "12px",
  borderTop: "1px solid #21262d",
};

const deliveryMetadataTitleStyle = {
  marginBottom: "10px",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
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

const legacyBadgeRowStyle = {
  marginTop: "6px",
};

const legacyBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  borderRadius: "999px",
  padding: "3px 8px",
  border: "1px solid rgba(244, 114, 182, 0.28)",
  backgroundColor: "rgba(244, 114, 182, 0.12)",
  color: "#fbcfe8",
  fontSize: "10px",
  fontWeight: "800",
  textTransform: "uppercase",
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

function TimelineEvent({ event, displaySettings }) {
  const metadataEntries = getSafeMetadataEntries(event?.metadata);
  return (
    <li style={timelineItemStyle}>
      <div style={timelineItemHeaderStyle}>
        <span style={timelineEventTypeStyle}>{formatEventType(event?.event_type)}</span>
        <time style={timelineTimestampStyle} dateTime={event?.timestamp || undefined}>
          {formatTimestamp(event?.timestamp, displaySettings, "N/A")}
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

function DeliveryAttempt({ attempt, displaySettings }) {
  const metadataEntries = getSafeDeliveryMetadataEntries(attempt?.metadata);
  return (
    <div style={deliveryCardStyle}>
      <div style={deliveryCardHeaderStyle}>
        <span style={deliveryTitleStyle}>
          Delivery #{formatDeliveryValue(attempt?.id)}
        </span>
        <span style={deliveryModeStyle}>
          {formatDeliveryValue(attempt?.provider)} / {formatDeliveryValue(attempt?.mode)}
        </span>
        <span style={{ ...badgeStyle, ...neutralBadgeStyle }}>
          {formatDeliveryValue(attempt?.status)}
        </span>
      </div>
      <div style={deliveryGridStyle}>
        <DetailField label="Correlation ID" value={formatDeliveryValue(attempt?.correlation_id)} mono />
        <DetailField label="Adapter" value={formatDeliveryValue(attempt?.adapter_name)} />
        <DetailField label="Action" value={formatDeliveryValue(attempt?.action)} />
        <DetailField
          label="Circuit breaker"
          value={formatDeliveryValue(attempt?.circuit_breaker_state)}
        />
        <DetailField
          label="Timeout seconds"
          value={formatDeliveryValue(attempt?.timeout_seconds)}
        />
        <DetailField
          label="Requested"
          value={formatTimestamp(attempt?.requested_at, displaySettings, "N/A")}
        />
        <DetailField
          label="Started"
          value={formatTimestamp(attempt?.started_at, displaySettings, "N/A")}
        />
        <DetailField
          label="Completed"
          value={formatTimestamp(attempt?.completed_at, displaySettings, "N/A")}
        />
        <DetailField
          label="Created"
          value={formatTimestamp(attempt?.created_at, displaySettings, "N/A")}
        />
        {attempt?.failure_code ? (
          <DetailField label="Failure code" value={formatDeliveryValue(attempt.failure_code)} />
        ) : null}
        {attempt?.failure_message ? (
          <DetailField
            label="Failure message"
            value={formatDeliveryValue(attempt.failure_message)}
          />
        ) : null}
      </div>
      {metadataEntries.length > 0 ? (
        <div style={deliveryMetadataStyle}>
          <div style={deliveryMetadataTitleStyle}>Safe metadata</div>
          <div style={deliveryGridStyle}>
            {metadataEntries.map(([key, value]) => (
              <DetailField key={key} label={key} value={formatDeliveryValue(value)} />
            ))}
          </div>
        </div>
      ) : null}
    </div>
  );
}

export default IncidentsPanel;
