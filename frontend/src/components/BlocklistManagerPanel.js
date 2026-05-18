import React, { useEffect, useState } from "react";
import {
  addBlocklistEntry,
  loadBlocklistEntries,
  unblockBlocklistEntry,
} from "../services/blocklistService";
import { formatAdminTimestamp } from "../utils/adminPanelDisplay";

function BlocklistManagerPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
}) {
  const [entries, setEntries] = useState([]);
  const [loading, setLoading] = useState(true);
  const [submitting, setSubmitting] = useState(false);
  const [unblockingId, setUnblockingId] = useState("");
  const [ipAddress, setIpAddress] = useState("");
  const [reason, setReason] = useState("");
  const [expiresAt, setExpiresAt] = useState("");
  const [feedback, setFeedback] = useState({ type: "", message: "" });

  const loadEntries = async () => {
    try {
      setLoading(true);
      const data = await loadBlocklistEntries();

      setEntries(Array.isArray(data) ? data : []);
    } catch (err) {
      setFeedback({
        type: "error",
        message: err.message || "Unable to load blocked IPs",
      });
      setEntries([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadEntries();
  }, []);

  const handleAddBlockedIp = async (e) => {
    e.preventDefault();
    setFeedback({ type: "", message: "" });

    try {
      setSubmitting(true);
      const data = await addBlocklistEntry({ ipAddress, reason, expiresAt });

      setIpAddress("");
      setReason("");
      setExpiresAt("");
      setFeedback({
        type: "success",
        message: data.message || "Blocked IP added successfully",
      });
      await loadEntries();
    } catch (err) {
      setFeedback({
        type: "error",
        message: err.message || "Unable to add blocked IP",
      });
    } finally {
      setSubmitting(false);
    }
  };

  const handleUnblock = async (blockId) => {
    setFeedback({ type: "", message: "" });

    try {
      setUnblockingId(String(blockId));
      const data = await unblockBlocklistEntry(blockId);

      setFeedback({
        type: "success",
        message: data.message || "Blocked IP removed successfully",
      });
      await loadEntries();
    } catch (err) {
      setFeedback({
        type: "error",
        message: err.message || "Unable to unblock IP",
      });
    } finally {
      setUnblockingId("");
    }
  };

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Response Controls</p>
          <h2 style={cardTitleStyle}>Blocklist Manager</h2>
          <p style={cardSubtitleStyle}>
            SIEM-managed blocklist tracking only. No firewall or host-level enforcement is applied in this phase.
          </p>
        </div>
      </div>

      <div style={panelContentStyle}>
        {feedback.message ? (
          <div style={feedback.type === "error" ? errorStateStyle : successStateStyle}>
            {feedback.message}
          </div>
        ) : null}

        <form onSubmit={handleAddBlockedIp} style={formStyle}>
          <div style={formGridStyle}>
            <div style={fieldStyle}>
              <label htmlFor="blocklist-ip-address" style={filterLabelStyle}>
                IP Address
              </label>
              <input
                id="blocklist-ip-address"
                type="text"
                value={ipAddress}
                onChange={(e) => setIpAddress(e.target.value)}
                placeholder="e.g. 198.51.100.14"
                style={inputStyle}
              />
            </div>

            <div style={fieldStyle}>
              <label htmlFor="blocklist-expires-at" style={filterLabelStyle}>
                Expires At (optional)
              </label>
              <input
                id="blocklist-expires-at"
                type="datetime-local"
                value={expiresAt}
                onChange={(e) => setExpiresAt(e.target.value)}
                style={{
                  ...inputStyle,
                  cursor: "pointer",
                }}
              />
            </div>
          </div>

          <div style={fieldStyle}>
            <label htmlFor="blocklist-reason" style={filterLabelStyle}>
              Reason (optional)
            </label>
            <input
              id="blocklist-reason"
              type="text"
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              placeholder="Why this IP is being tracked"
              style={inputStyle}
            />
          </div>

          <button type="submit" disabled={submitting} style={submitButtonStyle}>
            {submitting ? "Adding..." : "Add Blocked IP"}
          </button>
        </form>

        {loading ? (
          <p style={emptyTextStyle}>Loading blocked IPs...</p>
        ) : entries.length === 0 ? (
          <p style={emptyTextStyle}>No blocked IP entries recorded yet.</p>
        ) : (
          <div style={tableWrapperStyle}>
            <table style={tableStyle}>
              <thead>
                <tr>
                  <th style={headerCellStyle}>IP</th>
                  <th style={headerCellStyle}>Status</th>
                  <th style={headerCellStyle}>Reason</th>
                  <th style={headerCellStyle}>Created By</th>
                  <th style={headerCellStyle}>Created At</th>
                  <th style={headerCellStyle}>Expires At</th>
                  <th style={headerCellStyle}>Action</th>
                </tr>
              </thead>
              <tbody>
                {entries.map((entry) => (
                  <tr key={entry.id} style={rowStyle}>
                    <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{entry.ip_address}</td>
                    <td style={bodyCellStyle}>
                      <span style={entry.status === "active" ? activeBadgeStyle : inactiveBadgeStyle}>
                        {entry.status}
                      </span>
                    </td>
                    <td style={bodyCellStyle}>{entry.reason || "No reason provided"}</td>
                    <td style={bodyCellStyle}>{entry.created_by || "Unknown"}</td>
                    <td style={bodyCellStyle}>{formatAdminTimestamp(entry.created_at, "None")}</td>
                    <td style={bodyCellStyle}>{formatAdminTimestamp(entry.expires_at, "None")}</td>
                    <td style={bodyCellStyle}>
                      {entry.status === "active" ? (
                        <button
                          type="button"
                          onClick={() => handleUnblock(entry.id)}
                          disabled={unblockingId === String(entry.id)}
                          style={unblockButtonStyle}
                        >
                          {unblockingId === String(entry.id) ? "Unblocking..." : "Unblock"}
                        </button>
                      ) : (
                        <span style={inactiveTextStyle}>Inactive</span>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
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
  padding: "20px",
};

const formStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "14px",
  marginBottom: "20px",
};

const formGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "14px",
};

const fieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
};

const inputStyle = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  fontSize: "13px",
  boxSizing: "border-box",
};

const submitButtonStyle = {
  width: "fit-content",
  padding: "10px 14px",
  borderRadius: "10px",
  border: "1px solid rgba(239, 68, 68, 0.35)",
  backgroundColor: "rgba(239, 68, 68, 0.14)",
  color: "#fecaca",
  fontSize: "13px",
  fontWeight: "700",
  cursor: "pointer",
};

const tableWrapperStyle = {
  overflowX: "auto",
};

const tableStyle = {
  width: "100%",
  borderCollapse: "collapse",
  minWidth: "900px",
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

const monoCellStyle = {
  fontFamily: "'Courier New', monospace",
  fontSize: "12px",
  color: "#d29922",
};

const rowStyle = {
  backgroundColor: "#161b22",
};

const activeBadgeStyle = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  color: "#fca5a5",
  backgroundColor: "rgba(239, 68, 68, 0.10)",
  border: "1px solid rgba(239, 68, 68, 0.30)",
};

const inactiveBadgeStyle = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  color: "#c9d1d9",
  backgroundColor: "rgba(148, 163, 184, 0.10)",
  border: "1px solid rgba(148, 163, 184, 0.24)",
};

const unblockButtonStyle = {
  padding: "8px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(59, 130, 246, 0.35)",
  backgroundColor: "rgba(59, 130, 246, 0.12)",
  color: "#bfdbfe",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const inactiveTextStyle = {
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "600",
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

const successStateStyle = {
  marginBottom: "16px",
  padding: "10px 12px",
  borderRadius: "8px",
  fontSize: "13px",
  fontWeight: "600",
  backgroundColor: "rgba(34, 197, 94, 0.12)",
  border: "1px solid rgba(34, 197, 94, 0.28)",
  color: "#86efac",
};

export default BlocklistManagerPanel;
