import React, { useCallback, useEffect, useState } from "react";
import {
  loadRecentSoarQueueItems,
  loadSoarQueueStatus,
  runSoarWorkerOnce,
} from "../services/soarQueueService";
import { formatAdminTimestamp } from "../utils/adminPanelDisplay";

const QUEUE_STATUSES = ["pending", "running", "success", "failed", "skipped"];

function SoarQueuePanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
}) {
  const [statusSummary, setStatusSummary] = useState(null);
  const [queueItems, setQueueItems] = useState([]);
  const [statusFilter, setStatusFilter] = useState("all");
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const [runBatchSize, setRunBatchSize] = useState(10);
  const [isRunningBatch, setIsRunningBatch] = useState(false);
  const [runError, setRunError] = useState("");
  const [lastRunResult, setLastRunResult] = useState(null);

  const loadQueueVisibility = useCallback(async ({ quiet = false } = {}) => {
    try {
      if (quiet) {
        setRefreshing(true);
      } else {
        setLoading(true);
      }
      setError("");

      const [statusData, recentData] = await Promise.all([
        loadSoarQueueStatus(),
        loadRecentSoarQueueItems({
          limit: 50,
          status: statusFilter,
        }),
      ]);

      setStatusSummary(statusData || null);
      setQueueItems(Array.isArray(recentData?.items) ? recentData.items : []);
    } catch (err) {
      setError(err.message || "Unable to load SOAR queue");
      if (!quiet) {
        setStatusSummary(null);
        setQueueItems([]);
      }
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [statusFilter]);

  const handleRunBatch = useCallback(async () => {
    try {
      setRunError("");
      setIsRunningBatch(true);
      setLastRunResult(null);

      let batchSize = parseInt(runBatchSize, 10);
      if (Number.isNaN(batchSize) || batchSize < 1) {
        batchSize = 10;
      }
      batchSize = Math.min(batchSize, 25);

      const result = await runSoarWorkerOnce({ batchSize });
      setLastRunResult(result);

      await loadQueueVisibility({ quiet: true });
    } catch (err) {
      setRunError(err.message || "Unable to run SOAR simulation batch.");
    } finally {
      setIsRunningBatch(false);
    }
  }, [loadQueueVisibility, runBatchSize]);

  useEffect(() => {
    loadQueueVisibility();
  }, [loadQueueVisibility]);

  const counts = statusSummary?.counts || {};
  const total = statusSummary?.total ?? QUEUE_STATUSES.reduce(
    (sum, status) => sum + Number(counts[status] || 0),
    0
  );

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>SOAR</p>
          <h2 style={cardTitleStyle}>Queue Visibility</h2>
          <p style={cardSubtitleStyle}>
            Read-only status for queued automated response actions.
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
              <option value="all">All</option>
              {QUEUE_STATUSES.map((status) => (
                <option key={status} value={status}>
                  {formatQueueLabel(status)}
                </option>
              ))}
            </select>
          </label>
          <div style={batchControlWrapperStyle}>
            <label style={filterWrapperStyle}>
              <span style={filterLabelStyle}>Batch Size</span>
              <input
                type="number"
                min="1"
                max="25"
                value={runBatchSize}
                onChange={(event) => setRunBatchSize(event.target.value)}
                disabled={isRunningBatch}
                style={{ ...batchInputStyle, opacity: isRunningBatch ? 0.65 : 1 }}
              />
            </label>
            <button
              type="button"
              onClick={handleRunBatch}
              disabled={loading || isRunningBatch}
              title="Run one manual simulation batch. This processes pending queue items in simulation mode only."
              style={{
                ...runBatchButtonStyle,
                opacity: loading || isRunningBatch ? 0.65 : 1,
                cursor: loading || isRunningBatch ? "default" : "pointer",
              }}
            >
              {isRunningBatch ? "Running..." : "Run simulation batch"}
            </button>
          </div>
          <button
            type="button"
            onClick={() => loadQueueVisibility({ quiet: true })}
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
        {runError ? <div style={errorStateStyle}>{runError}</div> : null}

        {lastRunResult && lastRunResult.summary ? (
          <div style={resultSummaryStyle}>
            <div style={resultHeaderStyle}>
              <p style={resultLabelStyle}>Last manual simulation batch</p>
              <span style={resultMetaStyle}>
                Batch size used: {lastRunResult.batch_size ?? "N/A"}
              </span>
            </div>
            <div style={resultGridStyle}>
              <div style={resultItemStyle}>
                <span style={resultCountLabelStyle}>Processed</span>
                <strong style={resultCountValueStyle}>{lastRunResult.summary.processed || 0}</strong>
              </div>
              <div style={resultItemStyle}>
                <span style={resultCountLabelStyle}>Success</span>
                <strong style={{ ...resultCountValueStyle, color: "#7ee787" }}>
                  {lastRunResult.summary.success || 0}
                </strong>
              </div>
              <div style={resultItemStyle}>
                <span style={resultCountLabelStyle}>Failed</span>
                <strong style={{ ...resultCountValueStyle, color: "#fca5a5" }}>
                  {lastRunResult.summary.failed || 0}
                </strong>
              </div>
              <div style={resultItemStyle}>
                <span style={resultCountLabelStyle}>Skipped</span>
                <strong style={{ ...resultCountValueStyle, color: "#c9d1d9" }}>
                  {lastRunResult.summary.skipped || 0}
                </strong>
              </div>
              <div style={resultItemStyle}>
                <span style={resultCountLabelStyle}>Requeued</span>
                <strong style={{ ...resultCountValueStyle, color: "#f5d487" }}>
                  {lastRunResult.summary.requeued || 0}
                </strong>
              </div>
            </div>
            {lastRunResult.requested_batch_size !== undefined &&
            lastRunResult.batch_size !== undefined &&
            lastRunResult.requested_batch_size !== lastRunResult.batch_size ? (
              <p style={resultNoteStyle}>
                Requested batch size was capped by the backend.
              </p>
            ) : null}
          </div>
        ) : null}

        <div style={countsGridStyle}>
          {QUEUE_STATUSES.map((status) => (
            <div key={status} style={countCardStyle}>
              <span style={{ ...statusBadgeStyle, ...getStatusBadgeStyle(status) }}>
                {formatQueueLabel(status)}
              </span>
              <strong style={countValueStyle}>{counts[status] || 0}</strong>
            </div>
          ))}
          <div style={countCardStyle}>
            <span style={totalLabelStyle}>Total</span>
            <strong style={countValueStyle}>{total}</strong>
          </div>
        </div>

        {error ? <div style={errorStateStyle}>{error}</div> : null}

        {loading ? (
          <p style={emptyTextStyle}>Loading SOAR queue...</p>
        ) : queueItems.length === 0 ? (
          <p style={emptyTextStyle}>No queued SOAR actions found.</p>
        ) : (
          <div style={tableSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>Recent Queue Items</span>
              <span style={tableMetaCountStyle}>{queueItems.length}</span>
            </div>
            <div style={tableWrapperStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={{ ...headerCellStyle, width: "7%" }}>Queue ID</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Action</th>
                    <th style={{ ...headerCellStyle, width: "10%" }}>Status</th>
                    <th style={{ ...headerCellStyle, width: "13%" }}>Source IP</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Alert</th>
                    <th style={{ ...headerCellStyle, width: "8%" }}>Retries</th>
                    <th style={{ ...headerCellStyle, width: "16%" }}>Last Error</th>
                    <th style={{ ...headerCellStyle, width: "11%" }}>Created</th>
                    <th style={{ ...headerCellStyle, width: "11%" }}>Updated</th>
                  </tr>
                </thead>
                <tbody>
                  {queueItems.map((item) => (
                    <tr key={item.id} style={rowStyle}>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{item.id}</td>
                      <td style={bodyCellStyle}>{formatQueueLabel(item.action)}</td>
                      <td style={bodyCellStyle}>
                        <span style={{ ...statusBadgeStyle, ...getStatusBadgeStyle(item.status) }}>
                          {formatQueueLabel(item.status)}
                        </span>
                      </td>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                        {item.source_ip || <span style={mutedTextStyle}>N/A</span>}
                      </td>
                      <td style={bodyCellStyle}>{formatAlertReference(item)}</td>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                        {formatRetryCount(item)}
                      </td>
                      <td style={{ ...bodyCellStyle, ...errorCellStyle }} title={item.last_error || ""}>
                        {item.last_error || <span style={mutedTextStyle}>N/A</span>}
                      </td>
                      <td style={{ ...bodyCellStyle, ...timeCellStyle }} title={item.created_at || ""}>
                        {formatQueueTimestamp(item.created_at)}
                      </td>
                      <td style={{ ...bodyCellStyle, ...timeCellStyle }} title={item.updated_at || ""}>
                        {formatQueueTimestamp(item.updated_at)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )}
      </div>
    </section>
  );
}

const formatQueueLabel = (value) =>
  String(value || "unknown").replace(/_/g, " ").replace(/\b\w/g, (char) => char.toUpperCase());

const formatAlertReference = (item) => {
  if (item?.alert_reference?.label) return item.alert_reference.label;
  if (item?.alert_id !== null && item?.alert_id !== undefined) return `Alert ${item.alert_id}`;
  return <span style={mutedTextStyle}>Deleted alert</span>;
};

const formatRetryCount = (item) => `${item?.retry_count ?? 0} / ${item?.max_retries ?? 0}`;

const formatQueueTimestamp = (value) => formatAdminTimestamp(value, "N/A");

const getStatusBadgeStyle = (status) => {
  if (status === "pending") return pendingBadgeStyle;
  if (status === "running") return runningBadgeStyle;
  if (status === "success") return successBadgeStyle;
  if (status === "failed") return failedBadgeStyle;
  if (status === "skipped") return skippedBadgeStyle;
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
  borderRadius: "10px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.14)",
  color: "#93c5fd",
  fontSize: "13px",
  fontWeight: "700",
};

const batchControlWrapperStyle = {
  display: "flex",
  alignItems: "flex-end",
  gap: "8px",
  flexWrap: "wrap",
};

const batchInputStyle = {
  width: "96px",
  minHeight: "40px",
  padding: "9px 10px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "700",
};

const runBatchButtonStyle = {
  minHeight: "40px",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(245, 212, 135, 0.38)",
  backgroundColor: "rgba(217, 164, 65, 0.14)",
  color: "#f5d487",
  fontSize: "13px",
  fontWeight: "700",
};

const resultSummaryStyle = {
  marginBottom: "18px",
  padding: "14px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.24)",
  backgroundColor: "rgba(88, 166, 255, 0.08)",
};

const resultHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
  marginBottom: "12px",
};

const resultLabelStyle = {
  margin: 0,
  color: "#93c5fd",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const resultMetaStyle = {
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
};

const resultGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(96px, 1fr))",
  gap: "10px",
};

const resultItemStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
  minHeight: "52px",
  justifyContent: "center",
};

const resultCountLabelStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  textTransform: "uppercase",
};

const resultCountValueStyle = {
  color: "#e6edf3",
  fontSize: "20px",
  lineHeight: 1,
};

const resultNoteStyle = {
  margin: "10px 0 0",
  color: "#8b949e",
  fontSize: "12px",
};

const countsGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(130px, 1fr))",
  gap: "12px",
  marginBottom: "20px",
};

const countCardStyle = {
  border: "1px solid #30363d",
  borderRadius: "8px",
  backgroundColor: "#0d1117",
  padding: "12px",
  minHeight: "76px",
  display: "flex",
  flexDirection: "column",
  justifyContent: "space-between",
  gap: "10px",
};

const countValueStyle = {
  color: "#e6edf3",
  fontSize: "24px",
  lineHeight: 1,
};

const totalLabelStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const tableSectionStyle = {
  marginTop: "4px",
  borderTop: "1px solid #21262d",
  paddingTop: "20px",
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
  minWidth: "1120px",
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
};

const monoCellStyle = {
  fontFamily: "'Courier New', monospace",
  fontSize: "12px",
  color: "#d29922",
};

const timeCellStyle = {
  maxWidth: "150px",
  color: "#8b949e",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const errorCellStyle = {
  maxWidth: "220px",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
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

const statusBadgeStyle = {
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

const pendingBadgeStyle = {
  color: "#f5d487",
  backgroundColor: "rgba(217, 164, 65, 0.14)",
  border: "1px solid rgba(217, 164, 65, 0.32)",
};

const runningBadgeStyle = {
  color: "#93c5fd",
  backgroundColor: "rgba(59, 130, 246, 0.12)",
  border: "1px solid rgba(59, 130, 246, 0.28)",
};

const successBadgeStyle = {
  color: "#7ee787",
  backgroundColor: "rgba(63, 185, 80, 0.12)",
  border: "1px solid rgba(63, 185, 80, 0.28)",
};

const failedBadgeStyle = {
  color: "#fca5a5",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
};

const skippedBadgeStyle = {
  color: "#c9d1d9",
  backgroundColor: "rgba(139, 148, 158, 0.12)",
  border: "1px solid rgba(139, 148, 158, 0.26)",
};

const neutralBadgeStyle = {
  color: "#c9d1d9",
  backgroundColor: "#161b22",
  border: "1px solid #30363d",
};

export default SoarQueuePanel;
