import React, { useEffect, useState } from "react";

const SIEM_BASE_PATH =
  typeof window !== "undefined" &&
  (window.location.pathname === "/siem" || window.location.pathname.startsWith("/siem/"))
    ? "/siem"
    : "";

const buildSiemPath = (path) => `${SIEM_BASE_PATH}${path}`;

function AuditLogPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
}) {
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const formatCreatedAt = (value) => {
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

  const loadAuditLog = async () => {
    try {
      setLoading(true);
      setError("");

      const res = await fetch(buildSiemPath("/admin/audit-log"), {
        credentials: "include",
      });
      const data = await res.json().catch(() => []);

      if (!res.ok) {
        throw new Error(data.error || "Unable to load audit log");
      }

      setEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "Unable to load audit log");
      setEvents([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadAuditLog();
  }, []);

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Administration</p>
          <h2 style={cardTitleStyle}>Audit Log</h2>
          <p style={cardSubtitleStyle}>
            Recent security-relevant authentication and RBAC events.
          </p>
        </div>
      </div>

      <div style={panelContentStyle}>
        {loading ? (
          <p style={emptyTextStyle}>Loading audit events...</p>
        ) : error ? (
          <div style={errorStateStyle}>{error}</div>
        ) : events.length === 0 ? (
          <p style={emptyTextStyle}>No audit events found.</p>
        ) : (
          <div style={tableSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>Recent Events</span>
              <span style={tableMetaCountStyle}>{events.length}</span>
            </div>
            <div style={tableWrapperStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={{ ...headerCellStyle, width: "16%" }}>Event</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Actor</th>
                    <th style={{ ...headerCellStyle, width: "10%" }}>Role</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Target User</th>
                    <th style={{ ...headerCellStyle, width: "10%" }}>Alert ID</th>
                    <th style={{ ...headerCellStyle, width: "18%" }}>Path</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Source IP</th>
                    <th style={{ ...headerCellStyle, width: "10%" }}>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event, index) => (
                    <tr
                      key={`${event.event_type}-${event.created_at}-${index}`}
                      style={rowStyle}
                    >
                      <td style={bodyCellStyle}>
                        <span style={eventTypeBadgeStyle}>{event.event_type}</span>
                      </td>
                      <td style={bodyCellStyle}>{event.actor_username || "N/A"}</td>
                      <td style={bodyCellStyle}>
                        {event.actor_role ? (
                          <span style={roleBadgeStyle}>{event.actor_role}</span>
                        ) : (
                          <span style={mutedTextStyle}>N/A</span>
                        )}
                      </td>
                      <td style={bodyCellStyle}>{event.target_username || "N/A"}</td>
                      <td style={bodyCellStyle}>
                        {event.target_alert_id ?? <span style={mutedTextStyle}>N/A</span>}
                      </td>
                      <td style={{ ...bodyCellStyle, ...pathCellStyle }} title={event.request_path || ""}>
                        {event.request_path || "N/A"}
                      </td>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>
                        {event.source_ip || "N/A"}
                      </td>
                      <td style={{ ...bodyCellStyle, ...createdCellStyle }} title={event.created_at}>
                        {formatCreatedAt(event.created_at)}
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
  minWidth: "980px",
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

const eventTypeBadgeStyle = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  textTransform: "uppercase",
  letterSpacing: "0.04em",
  color: "#d2a8ff",
  backgroundColor: "rgba(210, 168, 255, 0.10)",
  border: "1px solid rgba(210, 168, 255, 0.25)",
};

const roleBadgeStyle = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  textTransform: "uppercase",
  color: "#93c5fd",
  backgroundColor: "rgba(59, 130, 246, 0.12)",
  border: "1px solid rgba(59, 130, 246, 0.28)",
};

const monoCellStyle = {
  fontFamily: "'Courier New', monospace",
  fontSize: "12px",
  color: "#d29922",
};

const pathCellStyle = {
  maxWidth: "220px",
  color: "#c9d1d9",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const createdCellStyle = {
  maxWidth: "160px",
  fontSize: "12px",
  color: "#8b949e",
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
  padding: "10px 12px",
  borderRadius: "8px",
  fontSize: "13px",
  fontWeight: "600",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
  color: "#fca5a5",
};

export default AuditLogPanel;
