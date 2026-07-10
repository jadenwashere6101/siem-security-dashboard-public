import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  expireOverdueApprovals,
  getApproval,
  listApprovals,
  submitApprovalDecision,
} from "../services/approvalService";
import { listApprovalNotificationDeliveries } from "../services/notificationDeliveryService";
import { formatTimestamp } from "../utils/displayFormatting";
import { ResponseOutcomeBadge, ResponseOutcomeSummary } from "./ResponseOutcome";

const STATUS_FILTERS = ["all", "pending", "approved", "denied", "expired"];
const RISK_FILTERS = ["all", "medium", "high", "critical"];
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

function ApprovalsPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
  userRole,
  displaySettings,
  initialStatusFilter = "all",
  onOpenResponseRegistry = null,
}) {
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState(initialStatusFilter || "all");
  const [riskFilter, setRiskFilter] = useState("all");
  const [selectedApprovalId, setSelectedApprovalId] = useState(null);
  const [selectedApproval, setSelectedApproval] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionError, setDecisionError] = useState("");
  const [submittingDecision, setSubmittingDecision] = useState("");
  const [isExpiring, setIsExpiring] = useState(false);
  const [expireResult, setExpireResult] = useState(null);
  const [expireError, setExpireError] = useState("");
  const [deliveryAttempts, setDeliveryAttempts] = useState([]);
  const [deliveryLoading, setDeliveryLoading] = useState(false);
  const [deliveryError, setDeliveryError] = useState("");

  useEffect(() => {
    if (initialStatusFilter) {
      setStatusFilter(initialStatusFilter);
    }
  }, [initialStatusFilter]);

  const isSuperAdmin = userRole === "super_admin";

  const loadApprovalList = useCallback(async ({ quiet = false, clearExpireFeedback = true } = {}) => {
    try {
      if (quiet) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError("");
      if (clearExpireFeedback) {
        setExpireResult(null);
        setExpireError("");
      }

      const data = await listApprovals({ status: statusFilter });
      setApprovals(Array.isArray(data?.approvals) ? data.approvals : []);
    } catch (err) {
      setError(err.message || "Unable to load approvals.");
      if (!quiet) {
        setApprovals([]);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [statusFilter]);

  const loadDetail = useCallback(async (approvalId) => {
    if (!approvalId) return;
    try {
      setDetailLoading(true);
      setDetailError("");
      setDecisionError("");

      const data = await getApproval(approvalId);
      setSelectedApproval(data?.approval || null);
      setDecisionReason("");
    } catch (err) {
      setSelectedApproval(null);
      setDetailError(err.message || "Unable to load approval.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const loadApprovalNotificationDeliveries = useCallback(async (approvalId) => {
    if (!approvalId) return;
    try {
      setDeliveryLoading(true);
      setDeliveryError("");

      const data = await listApprovalNotificationDeliveries(approvalId, { limit: 50 });
      setDeliveryAttempts(Array.isArray(data?.items) ? data.items : []);
    } catch (err) {
      setDeliveryAttempts([]);
      setDeliveryError(err.message || "Unable to load notification deliveries.");
    } finally {
      setDeliveryLoading(false);
    }
  }, []);

  const handleDecision = useCallback(async (decision) => {
    if (!selectedApprovalId || !isSuperAdmin || selectedApproval?.status !== "pending") {
      return;
    }

    try {
      setSubmittingDecision(decision);
      setDecisionError("");
      await submitApprovalDecision(selectedApprovalId, {
        decision,
        reason: decisionReason,
      });
      await loadDetail(selectedApprovalId);
      await loadApprovalNotificationDeliveries(selectedApprovalId);
      await loadApprovalList({ quiet: true });
    } catch (err) {
      setDecisionError(err.message || "Unable to submit approval decision.");
    } finally {
      setSubmittingDecision("");
    }
  }, [
    decisionReason,
    isSuperAdmin,
    loadApprovalList,
    loadApprovalNotificationDeliveries,
    loadDetail,
    selectedApproval,
    selectedApprovalId,
  ]);

  const handleCloseDetail = useCallback(() => {
    setSelectedApprovalId(null);
    setSelectedApproval(null);
    setDetailError("");
    setDetailLoading(false);
    setDecisionError("");
    setDecisionReason("");
    setSubmittingDecision("");
    setDeliveryAttempts([]);
    setDeliveryError("");
    setDeliveryLoading(false);
  }, []);

  const handleExpireOverdue = useCallback(async () => {
    if (!isSuperAdmin || isExpiring) return;
    try {
      setIsExpiring(true);
      setExpireError("");
      setExpireResult(null);
      const result = await expireOverdueApprovals();
      await loadApprovalList({ quiet: true, clearExpireFeedback: false });
      if (selectedApprovalId) {
        await loadDetail(selectedApprovalId);
        await loadApprovalNotificationDeliveries(selectedApprovalId);
      }
      setExpireResult(result);
    } catch (err) {
      setExpireError(err.message || "Unable to expire overdue approvals.");
    } finally {
      setIsExpiring(false);
    }
  }, [
    isSuperAdmin,
    isExpiring,
    loadApprovalList,
    loadApprovalNotificationDeliveries,
    loadDetail,
    selectedApprovalId,
  ]);

  useEffect(() => {
    loadApprovalList();
  }, [loadApprovalList]);

  useEffect(() => {
    if (selectedApprovalId) {
      setDeliveryAttempts([]);
      setDeliveryError("");
      loadDetail(selectedApprovalId);
      loadApprovalNotificationDeliveries(selectedApprovalId);
    }
  }, [loadApprovalNotificationDeliveries, loadDetail, selectedApprovalId]);

  const filteredApprovals = useMemo(() => {
    if (riskFilter === "all") return approvals;
    return approvals.filter(
      (approval) => String(approval.risk_level || "").toLowerCase() === riskFilter
    );
  }, [approvals, riskFilter]);

  const canDecideSelected =
    isSuperAdmin && selectedApproval && selectedApproval.status === "pending";

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>SOAR</p>
          <h2 style={cardTitleStyle}>Approval Requests</h2>
          <p style={cardSubtitleStyle}>
            Human approval visibility for high-risk SOAR actions.
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
              {STATUS_FILTERS.map((status) => (
                <option key={status} value={status}>
                  {formatLabel(status)}
                </option>
              ))}
            </select>
          </label>
          <label style={filterWrapperStyle}>
            <span style={filterLabelStyle}>Risk</span>
            <select
              value={riskFilter}
              onChange={(event) => setRiskFilter(event.target.value)}
              style={selectStyle}
            >
              {RISK_FILTERS.map((risk) => (
                <option key={risk} value={risk}>
                  {formatLabel(risk)}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            onClick={() => loadApprovalList({ quiet: true })}
            disabled={loading || refreshing || isExpiring}
            style={{
              ...refreshButtonStyle,
              opacity: loading || refreshing || isExpiring ? 0.65 : 1,
              cursor: loading || refreshing || isExpiring ? "default" : "pointer",
            }}
          >
            {refreshing ? "Refreshing..." : "Refresh"}
          </button>
          {isSuperAdmin ? (
            <button
              type="button"
              onClick={handleExpireOverdue}
              disabled={isExpiring || loading || refreshing}
              style={{
                ...expireButtonStyle,
                opacity: isExpiring || loading || refreshing ? 0.65 : 1,
                cursor: isExpiring || loading || refreshing ? "default" : "pointer",
              }}
            >
              {isExpiring ? "Expiring..." : "Expire overdue"}
            </button>
          ) : null}
        </div>
        {isSuperAdmin && expireResult !== null ? (
          <div style={expireResultStyle}>
            Expired {expireResult.expired_approvals ?? 0} approval
            {expireResult.expired_approvals === 1 ? "" : "s"},{" "}
            {expireResult.skipped_queue_rows ?? 0} queue row
            {expireResult.skipped_queue_rows === 1 ? "" : "s"} skipped.
          </div>
        ) : null}
        {isSuperAdmin && expireError ? (
          <div style={expireErrorStyle}>{expireError}</div>
        ) : null}
      </div>

      <div style={panelContentStyle}>
        {error ? (
          <div style={errorStateStyle}>
            <span>{error}</span>
            <button
              type="button"
              onClick={() => loadApprovalList({ quiet: false })}
              style={retryButtonStyle}
            >
              Retry
            </button>
          </div>
        ) : null}

        {loading ? (
          <p style={emptyTextStyle}>Loading approvals...</p>
        ) : filteredApprovals.length === 0 ? (
          <p style={emptyTextStyle}>No approval requests found.</p>
        ) : (
          <div style={tableSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>Approvals</span>
              <span style={tableMetaCountStyle}>{filteredApprovals.length}</span>
            </div>
            <div style={tableWrapperStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={{ ...headerCellStyle, width: "8%" }}>ID</th>
                    <th style={{ ...headerCellStyle, width: "17%" }}>Action</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Risk</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Outcome</th>
                    <th style={{ ...headerCellStyle, width: "11%" }}>Status</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Incident</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Queue</th>
                    <th style={{ ...headerCellStyle, width: "13%" }}>Created</th>
                    <th style={{ ...headerCellStyle, width: "13%" }}>Expires</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredApprovals.map((approval) => (
                    <tr
                      key={approval.id}
                      onClick={() => setSelectedApprovalId(approval.id)}
                      style={{
                        ...rowStyle,
                        ...(selectedApprovalId === approval.id ? selectedRowStyle : null),
                      }}
                    >
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{approval.id}</td>
                      <td style={bodyCellStyle}>{formatLabel(approval.action)}</td>
                      <td style={bodyCellStyle}>
                        <span style={{ ...badgeStyle, ...getRiskBadgeStyle(approval.risk_level) }}>
                          {formatLabel(approval.risk_level)}
                        </span>
                      </td>
                      <td style={bodyCellStyle}>
                        <ResponseOutcomeBadge outcome={approval.response_outcome || null} />
                      </td>
                      <td style={bodyCellStyle}>
                        <span style={{ ...badgeStyle, ...getStatusBadgeStyle(approval.status) }}>
                          {formatLabel(approval.status)}
                        </span>
                      </td>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                        {approval.incident_id ?? <span style={mutedTextStyle}>N/A</span>}
                      </td>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                        {approval.queue_id ?? <span style={mutedTextStyle}>N/A</span>}
                      </td>
                      <td style={{ ...bodyCellStyle, ...timeCellStyle }}>
                        {formatTimestamp(approval.created_at, displaySettings, "N/A")}
                      </td>
                      <td style={{ ...bodyCellStyle, ...timeCellStyle }}>
                        {formatTimestamp(approval.expires_at, displaySettings, "N/A")}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}

        {selectedApprovalId ? (
          <div style={detailPanelStyle}>
            <div style={detailHeaderStyle}>
              <h3 style={detailTitleStyle}>
                {selectedApproval
                  ? `Approval #${selectedApproval.id} - ${formatLabel(selectedApproval.action)}`
                  : "Approval Detail"}
              </h3>
              <button type="button" style={detailCloseButtonStyle} onClick={handleCloseDetail}>
                Close
              </button>
            </div>

            {detailLoading ? (
              <p style={emptyTextStyle}>Loading approval...</p>
            ) : detailError ? (
              <div style={errorStateStyle}>Error loading approval: {detailError}</div>
            ) : selectedApproval ? (
              <>
                <div style={detailGridStyle}>
                  <DetailField label="Status" value={formatLabel(selectedApproval.status)} />
                  <DetailField label="Risk" value={formatLabel(selectedApproval.risk_level)} />
                  <DetailField label="Incident ID" value={selectedApproval.incident_id ?? "N/A"} mono />
                  <DetailField label="Linked Queue Item" value={selectedApproval.queue_id ?? "N/A"} mono />
                  {typeof onOpenResponseRegistry === "function" ? (
                    <button
                      type="button"
                      onClick={() =>
                        onOpenResponseRegistry({
                          relatedAlertId: selectedApproval.alert_id,
                          relatedIncidentId: selectedApproval.incident_id,
                          sourceIp: selectedApproval.source_ip,
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
                  <DetailField
                    label="Created"
                    value={formatTimestamp(selectedApproval.created_at, displaySettings, "N/A")}
                  />
                  <DetailField
                    label="Decided"
                    value={formatTimestamp(selectedApproval.decided_at, displaySettings, "N/A")}
                  />
                  <DetailField
                    label="Expires"
                    value={formatTimestamp(selectedApproval.expires_at, displaySettings, "N/A")}
                  />
                  <DetailField
                    label="Request Reason"
                    value={selectedApproval.request_reason || "N/A"}
                  />
                  <DetailField
                    label="Decision Comment"
                    value={selectedApproval.decision_comment || "N/A"}
                  />
                  {selectedApproval.queue_id !== null && selectedApproval.queue_id !== undefined ? (
                    <div style={queueLinkNoteStyle}>
                      This approval is linked to Queue Item #{selectedApproval.queue_id}. Open the SOAR
                      Queue panel to view its current execution status.
                    </div>
                  ) : null}
                </div>

                <div style={outcomeSectionStyle}>
                  <p style={tableMetaLabelStyle}>Canonical response outcome</p>
                  <ResponseOutcomeSummary outcome={selectedApproval.response_outcome || null} />
                </div>

                <div style={eventsSectionStyle}>
                  <div style={tableMetaStyle}>
                    <span style={tableMetaLabelStyle}>Event History</span>
                    <span style={tableMetaCountStyle}>
                      {Array.isArray(selectedApproval.events)
                        ? selectedApproval.events.length
                        : 0}
                    </span>
                  </div>
                  {Array.isArray(selectedApproval.events) && selectedApproval.events.length > 0 ? (
                    <div style={tableWrapperStyle}>
                      <table style={detailTableStyle}>
                        <thead>
                          <tr>
                            <th style={headerCellStyle}>Event</th>
                            <th style={headerCellStyle}>Previous</th>
                            <th style={headerCellStyle}>New</th>
                            <th style={headerCellStyle}>Comment</th>
                            <th style={headerCellStyle}>Created</th>
                          </tr>
                        </thead>
                        <tbody>
                          {selectedApproval.events.map((event) => (
                            <tr key={event.id} style={rowStyle}>
                              <td style={bodyCellStyle}>{formatLabel(event.event_type)}</td>
                              <td style={bodyCellStyle}>{formatLabel(event.previous_status || "none")}</td>
                              <td style={bodyCellStyle}>{formatLabel(event.new_status)}</td>
                              <td style={bodyCellStyle}>{event.comment || "N/A"}</td>
                              <td style={{ ...bodyCellStyle, ...timeCellStyle }}>
                                {formatTimestamp(event.created_at, displaySettings, "N/A")}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  ) : (
                    <p style={emptyTextStyle}>No approval events found.</p>
                  )}
                </div>

                <div style={deliverySectionStyle}>
                  <div style={tableMetaStyle}>
                    <span style={tableMetaLabelStyle}>Notification Delivery History</span>
                    <span style={tableMetaCountStyle}>{deliveryAttempts.length}</span>
                  </div>
                  <p style={deliveryNoticeStyle}>{DELIVERY_HISTORY_DISCLAIMER}</p>
                  {deliveryLoading ? (
                    <p style={emptyTextStyle}>Loading notification deliveries...</p>
                  ) : deliveryError ? (
                    <div style={deliveryErrorStyle}>
                      <span>Error loading notification deliveries: {deliveryError}</span>
                      <button
                        type="button"
                        onClick={() =>
                          loadApprovalNotificationDeliveries(selectedApprovalId)
                        }
                        style={retryButtonStyle}
                      >
                        Retry deliveries
                      </button>
                    </div>
                  ) : deliveryAttempts.length === 0 ? (
                    <p style={emptyTextStyle}>
                      No notification delivery attempts found for this approval.
                    </p>
                  ) : (
                    <div
                      style={deliveryListStyle}
                      aria-label="Notification delivery history"
                    >
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

                {canDecideSelected ? (
                  <div style={decisionControlStyle}>
                    <label style={{ ...filterWrapperStyle, minWidth: "260px", flex: "1 1 260px" }}>
                      <span style={filterLabelStyle}>Decision reason</span>
                      <input
                        type="text"
                        value={decisionReason}
                        onChange={(event) => setDecisionReason(event.target.value)}
                        placeholder="Optional"
                        style={inputStyle}
                      />
                    </label>
                    <button
                      type="button"
                      onClick={() => handleDecision("approved")}
                      disabled={!!submittingDecision}
                      style={{
                        ...approveButtonStyle,
                        opacity: submittingDecision ? 0.65 : 1,
                        cursor: submittingDecision ? "default" : "pointer",
                      }}
                    >
                      {submittingDecision === "approved" ? "Approving..." : "Approve"}
                    </button>
                    <button
                      type="button"
                      onClick={() => handleDecision("denied")}
                      disabled={!!submittingDecision}
                      style={{
                        ...denyButtonStyle,
                        opacity: submittingDecision ? 0.65 : 1,
                        cursor: submittingDecision ? "default" : "pointer",
                      }}
                    >
                      {submittingDecision === "denied" ? "Denying..." : "Deny"}
                    </button>
                    {decisionError ? (
                      <div style={inlineErrorStyle}>{decisionError}</div>
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
  String(value || "unknown").replaceAll("_", " ").replace(/\b\w/g, (char) => char.toUpperCase());

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

const getRiskBadgeStyle = (riskLevel) => {
  const normalized = String(riskLevel || "").toLowerCase();
  if (normalized === "critical") return criticalBadgeStyle;
  if (normalized === "high") return highBadgeStyle;
  if (normalized === "medium") return mediumBadgeStyle;
  return neutralBadgeStyle;
};

const getStatusBadgeStyle = (status) => {
  if (status === "pending") return pendingBadgeStyle;
  if (status === "approved") return approvedBadgeStyle;
  if (status === "denied") return deniedBadgeStyle;
  if (status === "expired") return expiredBadgeStyle;
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

const expireButtonStyle = {
  minHeight: "40px",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(251, 146, 60, 0.35)",
  backgroundColor: "rgba(251, 146, 60, 0.10)",
  color: "#fb923c",
  fontSize: "13px",
  fontWeight: "700",
};

const expireResultStyle = {
  marginTop: "8px",
  padding: "8px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(126, 231, 135, 0.28)",
  backgroundColor: "rgba(63, 185, 80, 0.08)",
  color: "#7ee787",
  fontSize: "13px",
  fontWeight: "600",
};

const expireErrorStyle = {
  marginTop: "8px",
  padding: "8px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(239, 68, 68, 0.28)",
  backgroundColor: "rgba(239, 68, 68, 0.08)",
  color: "#fca5a5",
  fontSize: "13px",
  fontWeight: "600",
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

const pendingBadgeStyle = {
  color: "#93c5fd",
  backgroundColor: "rgba(59, 130, 246, 0.12)",
  border: "1px solid rgba(59, 130, 246, 0.28)",
};

const approvedBadgeStyle = {
  color: "#7ee787",
  backgroundColor: "rgba(63, 185, 80, 0.12)",
  border: "1px solid rgba(63, 185, 80, 0.28)",
};

const deniedBadgeStyle = {
  color: "#fca5a5",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
};

const expiredBadgeStyle = {
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

const queueLinkNoteStyle = {
  gridColumn: "1 / -1",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(139, 148, 158, 0.2)",
  backgroundColor: "rgba(139, 148, 158, 0.06)",
  color: "#8b949e",
  fontSize: "13px",
  lineHeight: "1.5",
};

const eventsSectionStyle = {
  marginTop: "18px",
  paddingTop: "16px",
  borderTop: "1px solid #21262d",
};

const outcomeSectionStyle = {
  marginTop: "18px",
  paddingTop: "16px",
  borderTop: "1px solid #21262d",
};

const deliverySectionStyle = {
  marginTop: "18px",
  paddingTop: "16px",
  borderTop: "1px solid #21262d",
};

const deliveryNoticeStyle = {
  margin: "0 0 12px 0",
  color: "#8b949e",
  fontSize: "13px",
  lineHeight: 1.5,
};

const deliveryErrorStyle = {
  ...errorStateStyle,
  marginBottom: 0,
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

const decisionControlStyle = {
  display: "flex",
  alignItems: "flex-end",
  gap: "12px",
  flexWrap: "wrap",
  marginTop: "18px",
  paddingTop: "16px",
  borderTop: "1px solid #21262d",
};

const inputStyle = {
  minHeight: "40px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  boxSizing: "border-box",
};

const approveButtonStyle = {
  minHeight: "40px",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(63, 185, 80, 0.35)",
  backgroundColor: "rgba(63, 185, 80, 0.12)",
  color: "#7ee787",
  fontSize: "13px",
  fontWeight: "700",
};

const denyButtonStyle = {
  minHeight: "40px",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(239, 68, 68, 0.38)",
  backgroundColor: "rgba(239, 68, 68, 0.10)",
  color: "#fca5a5",
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

export default ApprovalsPanel;
