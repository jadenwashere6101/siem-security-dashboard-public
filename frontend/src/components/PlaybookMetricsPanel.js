import React, { useCallback, useEffect, useMemo, useState } from "react";
import { getPlaybookMetrics, getNotificationDeliveryMetrics } from "../services/metricsService";

const KNOWN_STATUSES = [
  "pending",
  "running",
  "awaiting_approval",
  "success",
  "failed",
  "abandoned",
];

const NOTIFICATION_MODES = ["simulation", "real"];
const NOTIFICATION_DELIVERY_STATUSES = ["pending", "success", "failed", "timeout", "blocked"];
const NOTIFICATION_RECENT_BUCKETS = ["success", "failed", "timeout", "blocked"];
const CIRCUIT_BREAKER_STATES = ["closed", "open", "half_open", "unknown", "invalid"];

const SIMULATION_NOTICE =
  "Simulation only: these playbook metrics reflect simulated executions and visibility data. No real remediation or live integration execution is active.";

const NOTIFICATION_METRICS_NOTICE =
  "Operational evidence only: delivery metrics count recorded attempts (simulation and real mode). They do not prove a human received a message at Slack, Teams, or any other provider.";

function toCount(value) {
  const n = Number(value);
  return Number.isFinite(n) ? n : 0;
}

function normalizeByStatus(raw) {
  const out = {};
  for (const status of KNOWN_STATUSES) {
    out[status] = toCount(raw?.[status]);
  }
  return out;
}

function unknownStatusTotal(rawUnknown) {
  if (!rawUnknown || typeof rawUnknown !== "object" || Array.isArray(rawUnknown)) {
    return 0;
  }
  return Object.values(rawUnknown).reduce((sum, value) => sum + toCount(value), 0);
}

function normalizePlaybookRows(rawRows) {
  if (!Array.isArray(rawRows)) {
    return [];
  }
  return rawRows.map((row, index) => {
    const playbookId =
      row && row.playbook_id !== null && row.playbook_id !== undefined && row.playbook_id !== ""
        ? String(row.playbook_id)
        : `unknown-${index + 1}`;
    return {
      playbook_id: playbookId,
      total: toCount(row?.total),
      by_status: normalizeByStatus(row?.by_status),
      other_status_count: toCount(row?.other_status_count),
    };
  });
}

function normalizeFixedKeys(raw, keys) {
  const out = {};
  for (const key of keys) {
    out[key] = toCount(raw?.[key]);
  }
  return out;
}

function sortedCountEntries(rawMap) {
  if (!rawMap || typeof rawMap !== "object" || Array.isArray(rawMap)) {
    return [];
  }
  return Object.entries(rawMap).sort(([a], [b]) => a.localeCompare(b));
}

function PlaybookMetricsPanel({ cardStyle, cardHeaderStyle, cardTitleStyle, cardSubtitleStyle }) {
  const [metrics, setMetrics] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const [notificationMetrics, setNotificationMetrics] = useState(null);
  const [notificationLoading, setNotificationLoading] = useState(true);
  const [notificationError, setNotificationError] = useState("");

  const loadMetrics = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const data = await getPlaybookMetrics();
      setMetrics(data && typeof data === "object" ? data : null);
    } catch (err) {
      setError(err.message || "Unable to load playbook metrics.");
      setMetrics(null);
    } finally {
      setLoading(false);
    }
  }, []);

  const loadNotificationMetrics = useCallback(async () => {
    try {
      setNotificationLoading(true);
      setNotificationError("");
      const data = await getNotificationDeliveryMetrics();
      setNotificationMetrics(data && typeof data === "object" ? data : null);
    } catch (err) {
      setNotificationError(err.message || "Unable to load notification delivery metrics.");
      setNotificationMetrics(null);
    } finally {
      setNotificationLoading(false);
    }
  }, []);

  useEffect(() => {
    loadMetrics();
  }, [loadMetrics]);

  useEffect(() => {
    loadNotificationMetrics();
  }, [loadNotificationMetrics]);

  const byStatus = useMemo(() => normalizeByStatus(metrics?.by_status), [metrics?.by_status]);
  const statusTotal = useMemo(
    () => KNOWN_STATUSES.reduce((sum, status) => sum + toCount(byStatus[status]), 0),
    [byStatus]
  );
  const totalExecutions = toCount(metrics?.total_executions);
  const isEmpty = !loading && !error && totalExecutions === 0 && statusTotal === 0;

  const recentWindowHours = toCount(metrics?.recent?.window_hours) || 24;
  const recentSuccess = toCount(metrics?.recent?.success);
  const recentFailed = toCount(metrics?.recent?.failed);
  const recentTimeBasis = String(metrics?.recent?.time_basis || "");

  const approvalAwaiting = toCount(metrics?.approval_gated?.awaiting_approval);
  const approvalLinked = toCount(metrics?.approval_gated?.with_linked_approval);

  const rows = useMemo(() => normalizePlaybookRows(metrics?.by_playbook_id), [metrics?.by_playbook_id]);
  const unknownTotal = useMemo(() => unknownStatusTotal(metrics?.unknown_statuses), [metrics?.unknown_statuses]);

  const byNotificationMode = useMemo(
    () => normalizeFixedKeys(notificationMetrics?.by_mode, NOTIFICATION_MODES),
    [notificationMetrics?.by_mode]
  );
  const byNotificationStatus = useMemo(
    () => normalizeFixedKeys(notificationMetrics?.by_status, NOTIFICATION_DELIVERY_STATUSES),
    [notificationMetrics?.by_status]
  );
  const recentNotificationBuckets = useMemo(
    () => normalizeFixedKeys(notificationMetrics?.recent, NOTIFICATION_RECENT_BUCKETS),
    [notificationMetrics?.recent]
  );
  const circuitBreakerCounts = useMemo(
    () => normalizeFixedKeys(notificationMetrics?.circuit_breaker_state_counts, CIRCUIT_BREAKER_STATES),
    [notificationMetrics?.circuit_breaker_state_counts]
  );
  const totalDeliveryAttempts = toCount(notificationMetrics?.total_delivery_attempts);
  const providerEntries = useMemo(
    () => sortedCountEntries(notificationMetrics?.by_provider),
    [notificationMetrics?.by_provider]
  );
  const adapterNameEntries = useMemo(
    () => sortedCountEntries(notificationMetrics?.by_adapter_name),
    [notificationMetrics?.by_adapter_name]
  );
  const notificationRecentWindowHours = toCount(notificationMetrics?.recent?.window_hours) || 24;
  const notificationRecentTimeBasis = String(notificationMetrics?.recent?.time_basis || "");
  const notificationEmpty =
    !notificationLoading &&
    !notificationError &&
    totalDeliveryAttempts === 0 &&
    providerEntries.length === 0 &&
    adapterNameEntries.length === 0;

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>SOAR</p>
          <h2 style={cardTitleStyle}>Playbook Execution Metrics</h2>
          <p style={cardSubtitleStyle}>
            Read-only aggregate metrics for simulation-only playbook execution health.
          </p>
        </div>
      </div>

      <div style={panelContentStyle}>
        <div style={simulationNoticeStyle} role="note">
          {SIMULATION_NOTICE}
        </div>

        {error ? (
          <div style={errorStateStyle}>
            <span>Error: {error}</span>
          </div>
        ) : null}

        {loading ? <p style={emptyTextStyle}>Loading playbook metrics...</p> : null}

        {!loading && !error ? (
          <>
            <div style={summaryGridStyle}>
              <div style={summaryCardStyle}>
                <span style={summaryLabelStyle}>Total Executions</span>
                <span style={summaryValueStyle}>{totalExecutions}</span>
              </div>
              <div style={summaryCardStyle}>
                <span style={summaryLabelStyle}>Recent Window</span>
                <span style={summaryValueStyle}>Last {recentWindowHours} hours</span>
              </div>
            </div>

            {isEmpty ? <p style={emptyTextStyle}>No playbook execution data yet.</p> : null}

            <div style={sectionBlockStyle}>
              <h3 style={subsectionTitleStyle}>Status Breakdown</h3>
              <div style={statusGridStyle}>
                {KNOWN_STATUSES.map((status) => (
                  <div key={status} style={statusCellStyle}>
                    <span style={statusNameStyle}>{status}</span>
                    <span style={statusValueStyle}>{toCount(byStatus[status])}</span>
                  </div>
                ))}
                {unknownTotal > 0 ? (
                  <div style={statusCellStyle}>
                    <span style={statusNameStyle}>Other / Unknown</span>
                    <span style={statusValueStyle}>{unknownTotal}</span>
                  </div>
                ) : null}
              </div>
            </div>

            <div style={sectionBlockStyle}>
              <h3 style={subsectionTitleStyle}>Recent Activity</h3>
              <p style={infoTextStyle}>
                Last {recentWindowHours} hours - Success: {recentSuccess} | Failed: {recentFailed}
              </p>
              {recentTimeBasis ? <p style={mutedTextStyle}>{recentTimeBasis}</p> : null}
            </div>

            <div style={sectionBlockStyle}>
              <h3 style={subsectionTitleStyle}>Approval-Gated</h3>
              <p style={infoTextStyle}>Currently awaiting approval: {approvalAwaiting}</p>
              <p style={infoTextStyle}>Ever had a linked approval: {approvalLinked}</p>
            </div>

            <div style={sectionBlockStyle}>
              <h3 style={subsectionTitleStyle}>Per-Playbook Breakdown</h3>
              {rows.length === 0 ? (
                <p style={emptyTextStyle}>No playbook-level data available.</p>
              ) : (
                <ul style={rowListStyle}>
                  {rows.map((row) => (
                    <li key={row.playbook_id} style={rowCardStyle}>
                      <div style={rowHeaderStyle}>
                        <span style={playbookIdStyle}>{row.playbook_id}</span>
                        <span style={totalPillStyle}>Total: {row.total}</span>
                      </div>
                      <div style={rowStatusGridStyle}>
                        {KNOWN_STATUSES.map((status) => (
                          <span key={`${row.playbook_id}-${status}`} style={inlineStatusStyle}>
                            {status}: {row.by_status[status]}
                          </span>
                        ))}
                        {row.other_status_count > 0 ? (
                          <span style={inlineStatusStyle}>Other: {row.other_status_count}</span>
                        ) : null}
                      </div>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          </>
        ) : null}

        <div style={notificationSectionWrapStyle}>
          <h3 style={notificationSectionTitleStyle}>Notification Delivery Metrics</h3>
          <div style={notificationNoticeStyle} role="note">
            {NOTIFICATION_METRICS_NOTICE}
          </div>
          <p style={notificationModeHintStyle}>
            Compare <strong>simulation</strong> vs <strong>real</strong> counts under &quot;By mode&quot; (real
            attempts are rare and staging-controlled).
          </p>

          {notificationError ? (
            <div style={errorStateStyle}>
              <span>Notification metrics error: {notificationError}</span>
            </div>
          ) : null}

          {notificationLoading ? (
            <p style={emptyTextStyle}>Loading notification delivery metrics…</p>
          ) : null}

          {!notificationLoading && !notificationError ? (
            <>
              <div style={summaryGridStyle}>
                <div style={summaryCardStyle}>
                  <span style={summaryLabelStyle}>Total delivery attempts</span>
                  <span style={summaryValueStyle}>{totalDeliveryAttempts}</span>
                </div>
                <div style={summaryCardStyle}>
                  <span style={summaryLabelStyle}>Recent window</span>
                  <span style={summaryValueStyle}>Last {notificationRecentWindowHours} hours</span>
                </div>
              </div>

              {notificationEmpty ? (
                <p style={emptyTextStyle}>No notification delivery data yet.</p>
              ) : null}

              <div style={sectionBlockStyle}>
                <h4 style={notificationSubsectionTitleStyle}>By provider</h4>
                {providerEntries.length === 0 ? (
                  <p style={emptyTextStyle}>No provider breakdown.</p>
                ) : (
                  <div style={statusGridStyle}>
                    {providerEntries.map(([name, count]) => (
                      <div key={name} style={statusCellStyle}>
                        <span style={statusNameStyle}>{name}</span>
                        <span style={statusValueStyle}>{count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div style={sectionBlockStyle}>
                <h4 style={notificationSubsectionTitleStyle}>By mode</h4>
                <div style={statusGridStyle}>
                  {NOTIFICATION_MODES.map((mode) => (
                    <div key={mode} style={statusCellStyle}>
                      <span style={statusNameStyle}>{mode}</span>
                      <span style={statusValueStyle}>{toCount(byNotificationMode[mode])}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={sectionBlockStyle}>
                <h4 style={notificationSubsectionTitleStyle}>By status</h4>
                <div style={statusGridStyle}>
                  {NOTIFICATION_DELIVERY_STATUSES.map((status) => (
                    <div key={status} style={statusCellStyle}>
                      <span style={statusNameStyle}>{status}</span>
                      <span style={statusValueStyle}>{toCount(byNotificationStatus[status])}</span>
                    </div>
                  ))}
                </div>
              </div>

              <div style={sectionBlockStyle}>
                <h4 style={notificationSubsectionTitleStyle}>By adapter name</h4>
                {adapterNameEntries.length === 0 ? (
                  <p style={emptyTextStyle}>No adapter breakdown.</p>
                ) : (
                  <div style={statusGridStyle}>
                    {adapterNameEntries.map(([name, count]) => (
                      <div key={name} style={statusCellStyle}>
                        <span style={statusNameStyle}>{name}</span>
                        <span style={statusValueStyle}>{count}</span>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <div style={sectionBlockStyle}>
                <h4 style={notificationSubsectionTitleStyle}>Recent delivery outcomes</h4>
                <p style={infoTextStyle}>
                  Last {notificationRecentWindowHours} hours — success: {toCount(recentNotificationBuckets.success)}{" "}
                  | failed: {toCount(recentNotificationBuckets.failed)} | timeout:{" "}
                  {toCount(recentNotificationBuckets.timeout)} | blocked:{" "}
                  {toCount(recentNotificationBuckets.blocked)}
                </p>
                {notificationRecentTimeBasis ? <p style={mutedTextStyle}>{notificationRecentTimeBasis}</p> : null}
              </div>

              <div style={sectionBlockStyle}>
                <h4 style={notificationSubsectionTitleStyle}>Circuit breaker state (recorded)</h4>
                <div style={statusGridStyle}>
                  {CIRCUIT_BREAKER_STATES.map((state) => (
                    <div key={state} style={statusCellStyle}>
                      <span style={statusNameStyle}>{state}</span>
                      <span style={statusValueStyle}>{toCount(circuitBreakerCounts[state])}</span>
                    </div>
                  ))}
                </div>
              </div>

              {notificationMetrics?.unknown_modes &&
              Object.keys(notificationMetrics.unknown_modes).length > 0 ? (
                <p style={mutedTextStyle}>
                  Other modes (not in standard list):{" "}
                  {JSON.stringify(notificationMetrics.unknown_modes)}
                </p>
              ) : null}
              {notificationMetrics?.unknown_statuses &&
              Object.keys(notificationMetrics.unknown_statuses).length > 0 ? (
                <p style={mutedTextStyle}>
                  Other delivery statuses: {JSON.stringify(notificationMetrics.unknown_statuses)}
                </p>
              ) : null}
            </>
          ) : null}
        </div>
      </div>
    </section>
  );
}

const sectionLabelStyle = {
  margin: "0 0 8px 0",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.14em",
  textTransform: "uppercase",
};

const panelContentStyle = {
  padding: "24px 20px 22px",
};

const simulationNoticeStyle = {
  marginBottom: "18px",
  padding: "12px 14px",
  borderRadius: "10px",
  border: "1px solid rgba(210, 153, 34, 0.35)",
  backgroundColor: "rgba(210, 153, 34, 0.10)",
  color: "#e6c35c",
  fontSize: "13px",
  fontWeight: "600",
  lineHeight: 1.45,
};

const notificationSectionWrapStyle = {
  marginTop: "28px",
  paddingTop: "22px",
  borderTop: "1px solid #30363d",
};

const notificationSectionTitleStyle = {
  margin: "0 0 10px 0",
  fontSize: "16px",
  fontWeight: "700",
  color: "#e6edf3",
};

const notificationNoticeStyle = {
  marginBottom: "10px",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid rgba(56, 139, 253, 0.35)",
  backgroundColor: "rgba(56, 139, 253, 0.08)",
  color: "#c9e1ff",
  fontSize: "12px",
  fontWeight: "600",
  lineHeight: 1.45,
};

const notificationModeHintStyle = {
  margin: "0 0 14px 0",
  color: "#8b949e",
  fontSize: "12px",
  lineHeight: 1.45,
};

const notificationSubsectionTitleStyle = {
  margin: "0 0 10px 0",
  fontSize: "14px",
  fontWeight: "700",
  color: "#c9d1d9",
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

const emptyTextStyle = {
  margin: "0 0 12px 0",
  color: "#8b949e",
  fontSize: "14px",
};

const summaryGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: "12px",
  marginBottom: "18px",
};

const summaryCardStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
  padding: "12px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
};

const summaryLabelStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const summaryValueStyle = {
  color: "#e6edf3",
  fontSize: "18px",
  fontWeight: "700",
};

const sectionBlockStyle = {
  marginTop: "18px",
};

const subsectionTitleStyle = {
  margin: "0 0 12px 0",
  fontSize: "15px",
  fontWeight: "700",
  color: "#e6edf3",
};

const statusGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "10px",
};

const statusCellStyle = {
  border: "1px solid #30363d",
  borderRadius: "10px",
  padding: "10px 12px",
  backgroundColor: "#0d1117",
  display: "flex",
  justifyContent: "space-between",
  gap: "8px",
};

const statusNameStyle = {
  color: "#8b949e",
  fontSize: "12px",
  textTransform: "lowercase",
};

const statusValueStyle = {
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "700",
};

const infoTextStyle = {
  margin: "0 0 6px 0",
  color: "#e6edf3",
  fontSize: "13px",
};

const mutedTextStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
};

const rowListStyle = {
  listStyle: "none",
  margin: 0,
  padding: 0,
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const rowCardStyle = {
  border: "1px solid #30363d",
  borderRadius: "10px",
  padding: "12px",
  backgroundColor: "#0d1117",
};

const rowHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "10px",
  marginBottom: "8px",
  flexWrap: "wrap",
};

const playbookIdStyle = {
  color: "#e6edf3",
  fontWeight: "700",
  fontSize: "14px",
};

const totalPillStyle = {
  color: "#c9d1d9",
  fontSize: "12px",
  border: "1px solid #30363d",
  borderRadius: "999px",
  padding: "3px 10px",
  backgroundColor: "#161b22",
};

const rowStatusGridStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "8px",
};

const inlineStatusStyle = {
  color: "#8b949e",
  fontSize: "12px",
  border: "1px solid #30363d",
  borderRadius: "8px",
  padding: "3px 8px",
};

export default PlaybookMetricsPanel;
