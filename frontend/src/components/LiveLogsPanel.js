import React, { useEffect, useMemo, useRef, useState } from "react";

import { loadLiveLogs } from "../services/liveLogsService";

export const LIVE_LOG_SOURCE_LABELS = {
  honeypot: "Honeypot",
  bank_app: "Bank App",
  pfsense: "pfSense",
  nginx: "NGINX",
  azure_insights: "Azure",
  opentelemetry: "OTEL",
};

const POLL_INTERVAL_MS = 5000;

function LiveLogsPanel({
  source,
  label,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
}) {
  const displayLabel = label || LIVE_LOG_SOURCE_LABELS[source] || source;
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const maxSeenIdRef = useRef(null);

  const mergeEvents = (incoming) => {
    const rows = Array.isArray(incoming) ? incoming : [];
    if (rows.length === 0) {
      return;
    }

    setEvents((current) => {
      const byId = new Map(current.map((event) => [event.id, event]));
      rows.forEach((event) => {
        byId.set(event.id, event);
      });
      return Array.from(byId.values()).sort((a, b) => Number(b.id) - Number(a.id));
    });

    const newest = rows.reduce((max, event) => Math.max(max, Number(event.id) || 0), 0);
    if (newest > (maxSeenIdRef.current || 0)) {
      maxSeenIdRef.current = newest;
    }
  };

  const pollForNewEvents = async () => {
    try {
      const rows = await loadLiveLogs({ source, afterId: maxSeenIdRef.current });
      setError("");
      mergeEvents(rows);
    } catch (err) {
      setError(err.message || "Unable to load live logs");
    }
  };

  useEffect(() => {
    let isMounted = true;
    let intervalId;

    const start = async () => {
      setLoading(true);
      setError("");
      setEvents([]);
      maxSeenIdRef.current = null;

      try {
        const rows = await loadLiveLogs({ source });
        if (!isMounted) return;
        mergeEvents(rows);
      } catch (err) {
        if (!isMounted) return;
        setError(err.message || "Unable to load live logs");
      } finally {
        if (isMounted) {
          setLoading(false);
        }
      }

      intervalId = setInterval(() => {
        pollForNewEvents();
      }, POLL_INTERVAL_MS);
    };

    start();

    return () => {
      isMounted = false;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [source]);

  const subtitle = useMemo(
    () => `Newest normalized events for source=${source}. Auto-refreshes every few seconds.`,
    [source]
  );

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Live Logs</p>
          <h2 style={cardTitleStyle}>{displayLabel}</h2>
          <p style={cardSubtitleStyle}>{subtitle}</p>
        </div>
        <span style={sourceBadgeStyle}>{source}</span>
      </div>

      <div style={panelContentStyle}>
        {loading ? (
          <p style={emptyTextStyle}>Loading live logs...</p>
        ) : error ? (
          <div style={errorStateStyle}>{error}</div>
        ) : events.length === 0 ? (
          <p style={emptyTextStyle}>No live logs found for {displayLabel}.</p>
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
                    <th style={{ ...headerCellStyle, width: "8%" }}>ID</th>
                    <th style={{ ...headerCellStyle, width: "14%" }}>Type</th>
                    <th style={{ ...headerCellStyle, width: "10%" }}>Severity</th>
                    <th style={{ ...headerCellStyle, width: "13%" }}>Source IP</th>
                    <th style={{ ...headerCellStyle, width: "13%" }}>App</th>
                    <th style={{ ...headerCellStyle, width: "24%" }}>Message</th>
                    <th style={{ ...headerCellStyle, width: "18%" }}>Created</th>
                  </tr>
                </thead>
                <tbody>
                  {events.map((event) => (
                    <tr key={event.id} style={rowStyle}>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{event.id}</td>
                      <td style={bodyCellStyle}>
                        <span style={eventTypeBadgeStyle}>{event.event_type || "unknown"}</span>
                      </td>
                      <td style={bodyCellStyle}>{event.severity || "unknown"}</td>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{event.source_ip || "N/A"}</td>
                      <td style={bodyCellStyle}>{event.app_name || "N/A"}</td>
                      <td style={bodyCellStyle}>{event.message || "N/A"}</td>
                      <td style={{ ...bodyCellStyle, ...createdCellStyle }} title={event.created_at || ""}>
                        {event.created_at || "N/A"}
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

const sourceBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  justifyContent: "center",
  minHeight: "28px",
  padding: "4px 10px",
  borderRadius: "999px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.14)",
  color: "#93c5fd",
  fontSize: "11px",
  fontWeight: "700",
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

const monoCellStyle = {
  fontFamily: "'Courier New', monospace",
  fontSize: "12px",
  color: "#d29922",
};

const createdCellStyle = {
  color: "#8b949e",
  fontSize: "12px",
};

const emptyTextStyle = {
  color: "#8b949e",
  margin: 0,
};

const errorStateStyle = {
  padding: "12px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(248, 81, 73, 0.35)",
  color: "#fca5a5",
  backgroundColor: "rgba(248, 81, 73, 0.10)",
};

export default LiveLogsPanel;
