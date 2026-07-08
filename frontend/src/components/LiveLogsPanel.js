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
const VIEW_MODES = {
  eventFeed: "event-feed",
  rawStream: "raw-stream",
};

const stringifyRawValue = (value) => {
  if (value === null || value === undefined || value === "") {
    return "No raw_payload available; showing normalized event details.";
  }

  if (typeof value === "string") {
    return value;
  }

  try {
    return JSON.stringify(value, null, 2);
  } catch (_error) {
    return "Unable to display raw payload.";
  }
};

const buildNormalizedFallback = (event) => ({
  id: event.id,
  event_type: event.event_type,
  severity: event.severity,
  source: event.source,
  source_type: event.source_type,
  source_ip: event.source_ip,
  app_name: event.app_name,
  environment: event.environment,
  message: event.message,
  created_at: event.created_at,
});

// Some adapters (pfSense, NGINX) preserve the original pre-normalization log
// line verbatim under one of these keys alongside their parsed fields. When
// present, that literal text is a truer "raw log" than the surrounding JSON.
const RAW_LOG_TEXT_KEYS = ["raw_log", "line"];

const extractRawLogText = (rawPayload) => {
  if (!rawPayload || typeof rawPayload !== "object") {
    return null;
  }
  for (const key of RAW_LOG_TEXT_KEYS) {
    const value = rawPayload[key];
    if (typeof value === "string" && value.trim()) {
      return value;
    }
  }
  return null;
};

const formatRawStreamEntry = (event) => {
  const headerParts = [
    event.created_at || "unknown-time",
    `id=${event.id ?? "unknown"}`,
    `source=${event.source || "unknown"}`,
    `type=${event.event_type || "unknown"}`,
    `severity=${event.severity || "unknown"}`,
    event.source_ip ? `source_ip=${event.source_ip}` : null,
    event.app_name ? `app=${event.app_name}` : null,
  ].filter(Boolean);

  const hasRawPayload = event.raw_payload && Object.keys(event.raw_payload || {}).length > 0;
  const rawLogText = hasRawPayload ? extractRawLogText(event.raw_payload) : null;
  const body = rawLogText || stringifyRawValue(hasRawPayload ? event.raw_payload : buildNormalizedFallback(event));

  return `${headerParts.join(" ")}\n${body}`;
};

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
  const [viewMode, setViewMode] = useState(VIEW_MODES.eventFeed);
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
        <div style={viewToggleStyle} role="group" aria-label="Live log view mode">
          <button
            type="button"
            onClick={() => setViewMode(VIEW_MODES.eventFeed)}
            aria-pressed={viewMode === VIEW_MODES.eventFeed}
            style={{
              ...viewToggleButtonStyle,
              ...(viewMode === VIEW_MODES.eventFeed ? activeViewToggleButtonStyle : {}),
            }}
          >
            Event Feed
          </button>
          <button
            type="button"
            onClick={() => setViewMode(VIEW_MODES.rawStream)}
            aria-pressed={viewMode === VIEW_MODES.rawStream}
            style={{
              ...viewToggleButtonStyle,
              ...(viewMode === VIEW_MODES.rawStream ? activeViewToggleButtonStyle : {}),
            }}
          >
            Raw Stream
          </button>
        </div>

        {loading ? (
          <p style={emptyTextStyle}>Loading live logs...</p>
        ) : error ? (
          <div style={errorStateStyle}>{error}</div>
        ) : events.length === 0 ? (
          <p style={emptyTextStyle}>No live logs found for {displayLabel}.</p>
        ) : viewMode === VIEW_MODES.rawStream ? (
          <div style={rawStreamSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>Raw Stream</span>
              <span style={tableMetaCountStyle}>{events.length}</span>
            </div>
            <div style={rawStreamStyle} aria-label={`${displayLabel} raw stream`}>
              {events.map((event) => (
                <pre key={event.id} style={rawEntryStyle}>
                  {formatRawStreamEntry(event)}
                </pre>
              ))}
            </div>
          </div>
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

const viewToggleStyle = {
  display: "inline-flex",
  alignItems: "center",
  gap: "4px",
  marginBottom: "20px",
  padding: "4px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
};

const viewToggleButtonStyle = {
  appearance: "none",
  border: "0",
  borderRadius: "6px",
  backgroundColor: "transparent",
  color: "#8b949e",
  cursor: "pointer",
  fontSize: "12px",
  fontWeight: "700",
  padding: "8px 12px",
};

const activeViewToggleButtonStyle = {
  backgroundColor: "#1f6feb",
  color: "#ffffff",
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

const rawStreamSectionStyle = {
  marginTop: "4px",
  borderTop: "1px solid #21262d",
  paddingTop: "20px",
};

const rawStreamStyle = {
  maxHeight: "620px",
  overflow: "auto",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#010409",
  padding: "14px",
};

const rawEntryStyle = {
  margin: "0 0 14px 0",
  padding: "12px",
  borderRadius: "6px",
  border: "1px solid #21262d",
  backgroundColor: "#0d1117",
  color: "#d1d5db",
  fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
  fontSize: "12px",
  lineHeight: "1.55",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
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
