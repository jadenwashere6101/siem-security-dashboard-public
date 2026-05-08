import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  getApproval,
  listApprovals,
  submitApprovalDecision,
} from "../services/approvalService";
import { formatAdminTimestamp } from "../utils/adminPanelDisplay";

const STATUS_FILTERS = ["all", "pending", "approved", "denied", "expired"];
const RISK_FILTERS = ["all", "medium", "high", "critical"];

function ApprovalsPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
  userRole,
}) {
  const [approvals, setApprovals] = useState([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [statusFilter, setStatusFilter] = useState("all");
  const [riskFilter, setRiskFilter] = useState("all");
  const [selectedApprovalId, setSelectedApprovalId] = useState(null);
  const [selectedApproval, setSelectedApproval] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");
  const [decisionReason, setDecisionReason] = useState("");
  const [decisionError, setDecisionError] = useState("");
  const [submittingDecision, setSubmittingDecision] = useState("");

  const isSuperAdmin = userRole === "super_admin";

  const loadApprovalList = useCallback(async ({ quiet = false } = {}) => {
    try {
      if (quiet) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError("");

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
  }, []);

  useEffect(() => {
    loadApprovalList();
  }, [loadApprovalList]);

  useEffect(() => {
    if (selectedApprovalId) {
      loadDetail(selectedApprovalId);
    }
  }, [loadDetail, selectedApprovalId]);

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
                    <th style={{ ...headerCellStyle, width: "13%" }}>Status</th>
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
                        {formatTimestamp(approval.created_at)}
                      </td>
                      <td style={{ ...bodyCellStyle, ...timeCellStyle }}>
                        {formatTimestamp(approval.expires_at)}
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
                  <DetailField label="Queue ID" value={selectedApproval.queue_id ?? "N/A"} mono />
                  <DetailField label="Created" value={formatTimestamp(selectedApproval.created_at)} />
                  <DetailField label="Decided" value={formatTimestamp(selectedApproval.decided_at)} />
                  <DetailField label="Expires" value={formatTimestamp(selectedApproval.expires_at)} />
                  <DetailField
                    label="Request Reason"
                    value={selectedApproval.request_reason || "N/A"}
                  />
                  <DetailField
                    label="Decision Comment"
                    value={selectedApproval.decision_comment || "N/A"}
                  />
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
                                {formatTimestamp(event.created_at)}
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
  String(value || "unknown").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());

const formatTimestamp = (value) => formatAdminTimestamp(value, "N/A");

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

const eventsSectionStyle = {
  marginTop: "18px",
  paddingTop: "16px",
  borderTop: "1px solid #21262d",
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

export default ApprovalsPanel;
