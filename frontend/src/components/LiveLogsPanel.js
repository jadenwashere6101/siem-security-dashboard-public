import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { loadLiveLogs } from "../services/liveLogsService";
import { formatTimestamp } from "../utils/displayFormatting";
import { getSeverityBadgeStyle } from "../utils/severityDisplay";
import { LIVE_LOG_SOURCE_LABELS } from "../utils/sourceMetadata";
export { LIVE_LOG_SOURCE_LABELS } from "../utils/sourceMetadata";

const DEFAULT_POLL_INTERVAL_MS = 5000;
const MAX_RETAINED_EVENTS = 500;
const VIEW_MODES = {
  eventFeed: "event-feed",
  rawLog: "raw-log",
  json: "json",
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

const formatJsonEntry = (event) => {
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

// --- Raw Log tab: one compact, source-specific text line per event -------
// This is deliberately NOT a JSON renderer. Sources that preserve a literal
// pre-normalization log line (pfSense, NGINX) show it verbatim; sources that
// only ever had structured data (Honeypot, Azure, OTel, Bank App) get the
// most realistic single-line log reconstructed from whatever fields their
// raw_payload happens to contain, falling back to normalized event columns.

const getRawPayloadObject = (event) =>
  event.raw_payload && typeof event.raw_payload === "object" ? event.raw_payload : {};

const firstNonEmptyString = (...values) => {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) {
      return value.trim();
    }
    if (typeof value === "number" && Number.isFinite(value)) {
      return String(value);
    }
  }
  return null;
};

const formatGenericLogLine = (event) => {
  const timestamp = event.created_at || "unknown-time";
  const sourceIpSuffix = event.source_ip ? ` source_ip=${event.source_ip}` : "";
  return `${timestamp} [${event.source || "unknown"}] ${event.message || "event"}${sourceIpSuffix}`;
};

const formatHoneypotLogLine = (event, rawPayload) => {
  const timestamp = firstNonEmptyString(rawPayload.timestamp, event.created_at) || "unknown-time";
  const sourceIp = firstNonEmptyString(rawPayload.source_ip, event.source_ip) || "unknown-ip";
  const method = firstNonEmptyString(rawPayload.method);
  const path = firstNonEmptyString(rawPayload.path);
  const username = firstNonEmptyString(rawPayload.username);
  const userAgent = firstNonEmptyString(rawPayload.user_agent, rawPayload.scanner_signature);

  const segments = [timestamp, sourceIp];
  if (method || path) {
    segments.push(`${method || "-"} ${path || "-"}`);
  }
  if (username) {
    segments.push(`username="${username}"`);
  }
  if (userAgent) {
    segments.push(`User-Agent="${userAgent}"`);
  }
  if (segments.length === 2) {
    segments.push(event.message || "honeypot event");
  }
  return segments.join(" ");
};

const formatAzureLogLine = (event, rawPayload) => {
  const timestamp =
    firstNonEmptyString(rawPayload.timestamp, rawPayload.time, event.created_at) || "unknown-time";
  const baseData = rawPayload?.data?.baseData;
  const operation =
    firstNonEmptyString(baseData?.name, rawPayload.operationName, rawPayload.name, event.event_type) ||
    "azure_event";
  const resultCode = firstNonEmptyString(
    baseData?.resultCode,
    baseData?.responseCode,
    rawPayload.resultCode,
    rawPayload.responseCode,
    rawPayload.statusCode
  );
  const username = firstNonEmptyString(rawPayload.userPrincipalName, rawPayload.username, rawPayload.upn);
  const sourceIp = firstNonEmptyString(
    rawPayload.source_ip,
    rawPayload.sourceIp,
    rawPayload.clientIp,
    rawPayload.client_IP,
    event.source_ip
  );

  const segments = [timestamp, `[${operation}]`];
  if (resultCode) segments.push(`result=${resultCode}`);
  if (username) segments.push(`user=${username}`);
  if (sourceIp) segments.push(`source_ip=${sourceIp}`);
  segments.push(event.message || "Azure telemetry event");
  return segments.join(" ");
};

const extractOtelAttribute = (rawPayload, ...keys) => {
  const attributes = rawPayload.attributes;
  if (Array.isArray(attributes)) {
    for (const item of attributes) {
      if (item && keys.includes(item.key)) {
        const value = firstNonEmptyString(item.value?.stringValue, item.value);
        if (value) return value;
      }
    }
  } else if (attributes && typeof attributes === "object") {
    for (const key of keys) {
      const value = firstNonEmptyString(attributes[key]);
      if (value) return value;
    }
  }
  return null;
};

const formatOtelLogLine = (event, rawPayload) => {
  const timestamp =
    firstNonEmptyString(rawPayload.timestamp, rawPayload.time, event.created_at) || "unknown-time";
  const serviceName = extractOtelAttribute(rawPayload, "service.name") || event.app_name;
  const operation =
    firstNonEmptyString(rawPayload.name) ||
    extractOtelAttribute(rawPayload, "http.target", "url.path", "http.route") ||
    event.event_type ||
    "otel_event";
  const statusCode =
    firstNonEmptyString(rawPayload.status_code, rawPayload.statusCode) ||
    extractOtelAttribute(rawPayload, "http.status_code", "status_code", "statusCode");

  const segments = [timestamp];
  if (serviceName) segments.push(`[${serviceName}]`);
  segments.push(operation);
  if (statusCode) segments.push(`status=${statusCode}`);
  segments.push(event.message || "OpenTelemetry event");
  return segments.join(" ");
};

const formatBankAppLogLine = (event, rawPayload) => {
  const timestamp = firstNonEmptyString(event.created_at) || "unknown-time";
  const appName = firstNonEmptyString(rawPayload.app_name, event.app_name) || "bank_app";
  const level = (firstNonEmptyString(rawPayload.severity, event.severity) || "info").toUpperCase();
  const message = firstNonEmptyString(rawPayload.message, event.message) || "no message";
  const sourceIp = firstNonEmptyString(rawPayload.source_ip, event.source_ip);

  const segments = [timestamp, `[${appName}]`, `${level}:`, message];
  if (sourceIp) segments.push(`source_ip=${sourceIp}`);
  return segments.join(" ");
};

const formatRawLogLine = (event) => {
  const rawPayload = getRawPayloadObject(event);

  switch (event.source) {
    case "honeypot":
      return formatHoneypotLogLine(event, rawPayload);
    case "nginx":
      return firstNonEmptyString(rawPayload.line) || formatGenericLogLine(event);
    case "pfsense":
      return firstNonEmptyString(rawPayload.raw_log, rawPayload.sanitized_summary) || formatGenericLogLine(event);
    case "azure_insights":
      return formatAzureLogLine(event, rawPayload);
    case "opentelemetry":
      return formatOtelLogLine(event, rawPayload);
    case "bank_app":
      return formatBankAppLogLine(event, rawPayload);
    default:
      return formatGenericLogLine(event);
  }
};

function LiveLogsPanel({
  source,
  label,
  pollIntervalMs = DEFAULT_POLL_INTERVAL_MS,
  displaySettings,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
}) {
  const displayLabel = label || LIVE_LOG_SOURCE_LABELS[source] || source;
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [viewMode, setViewMode] = useState(
    displaySettings?.defaultLiveLogsTab || VIEW_MODES.eventFeed
  );
  const maxSeenIdRef = useRef(null);
  const defaultViewModeRef = useRef(displaySettings?.defaultLiveLogsTab || VIEW_MODES.eventFeed);

  useEffect(() => {
    const nextDefault = displaySettings?.defaultLiveLogsTab || VIEW_MODES.eventFeed;
    if (defaultViewModeRef.current !== nextDefault) {
      defaultViewModeRef.current = nextDefault;
      setViewMode(nextDefault);
    }
  }, [displaySettings?.defaultLiveLogsTab]);

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
      return Array.from(byId.values())
        .sort((a, b) => Number(b.id) - Number(a.id))
        .slice(0, MAX_RETAINED_EVENTS);
    });

    const newest = rows.reduce((max, event) => Math.max(max, Number(event.id) || 0), 0);
    if (newest > (maxSeenIdRef.current || 0)) {
      maxSeenIdRef.current = newest;
    }
  };

  const pollForNewEvents = useCallback(async () => {
    try {
      const rows = await loadLiveLogs({ source, afterId: maxSeenIdRef.current });
      setError("");
      mergeEvents(rows);
    } catch (err) {
      setError(err.message || "Unable to load live logs");
    }
  }, [source]);

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

      if (pollIntervalMs > 0) {
        intervalId = setInterval(() => {
          pollForNewEvents();
        }, pollIntervalMs);
      }
    };

    start();

    return () => {
      isMounted = false;
      if (intervalId) {
        clearInterval(intervalId);
      }
    };
  }, [pollForNewEvents, source, pollIntervalMs]);

  const subtitle = useMemo(
    () =>
      pollIntervalMs > 0
        ? `Newest normalized events for source=${source}. Auto-refreshes every few seconds.`
        : `Newest normalized events for source=${source}. Auto-refresh is currently disabled.`,
    [source, pollIntervalMs]
  );

  const limitedEvents = useMemo(() => {
    const rowsPerPage = displaySettings?.rowsPerPage ?? "all";
    return rowsPerPage === "all" ? events : events.slice(0, Number(rowsPerPage));
  }, [events, displaySettings?.rowsPerPage]);

  const fontSizeScale = useMemo(() => {
    const size = displaySettings?.liveLogsFontSize || "medium";
    if (size === "small") return { table: "12px", raw: "11px", json: "11px" };
    if (size === "large") return { table: "15px", raw: "13px", json: "13px" };
    return { table: "13px", raw: "12px", json: "12px" };
  }, [displaySettings?.liveLogsFontSize]);

  const visibleColumns = displaySettings?.columnVisibility?.liveLogsTable || {
    id: true,
    type: true,
    severity: true,
    sourceIp: true,
    app: true,
    message: true,
    created: true,
  };

  const getHighlightStyle = (event) => {
    const rules = displaySettings?.liveLogHighlightRules || [];
    const severity = String(event.severity || "").toLowerCase();
    const type = String(event.event_type || "").toLowerCase();
    for (const rule of rules) {
      const targetValue = rule.target === "severity" ? severity : type;
      if (targetValue !== String(rule.value || "").toLowerCase()) {
        continue;
      }
      if (rule.treatment === "border") {
        return { boxShadow: "inset 3px 0 0 #58a6ff" };
      }
      if (rule.treatment === "background") {
        return { backgroundColor: "rgba(31, 111, 235, 0.14)" };
      }
      if (rule.treatment === "glow") {
        return { boxShadow: "0 0 0 1px rgba(88, 166, 255, 0.45)" };
      }
    }
    return null;
  };

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
            onClick={() => setViewMode(VIEW_MODES.rawLog)}
            aria-pressed={viewMode === VIEW_MODES.rawLog}
            style={{
              ...viewToggleButtonStyle,
              ...(viewMode === VIEW_MODES.rawLog ? activeViewToggleButtonStyle : {}),
            }}
          >
            Raw Log
          </button>
          <button
            type="button"
            onClick={() => setViewMode(VIEW_MODES.json)}
            aria-pressed={viewMode === VIEW_MODES.json}
            style={{
              ...viewToggleButtonStyle,
              ...(viewMode === VIEW_MODES.json ? activeViewToggleButtonStyle : {}),
            }}
          >
            JSON
          </button>
        </div>

        {loading ? (
          <p style={emptyTextStyle}>Loading live logs...</p>
        ) : error ? (
          <div style={errorStateStyle}>{error}</div>
        ) : limitedEvents.length === 0 ? (
          <p style={emptyTextStyle}>No live logs found for {displayLabel}.</p>
        ) : viewMode === VIEW_MODES.rawLog ? (
          <div style={rawStreamSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>Raw Log</span>
              <span style={tableMetaCountStyle}>{limitedEvents.length}</span>
            </div>
            <div style={rawStreamStyle} aria-label={`${displayLabel} raw log`}>
              {limitedEvents.map((event) => (
                <div key={event.id} style={{ ...rawLogLineStyle, fontSize: fontSizeScale.raw }}>
                  {formatRawLogLine(event)}
                </div>
              ))}
            </div>
          </div>
        ) : viewMode === VIEW_MODES.json ? (
          <div style={rawStreamSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>JSON</span>
              <span style={tableMetaCountStyle}>{limitedEvents.length}</span>
            </div>
            <div style={rawStreamStyle} aria-label={`${displayLabel} json view`}>
              {limitedEvents.map((event) => (
                <pre key={event.id} style={{ ...rawEntryStyle, fontSize: fontSizeScale.json }}>
                  {formatJsonEntry(event)}
                </pre>
              ))}
            </div>
          </div>
        ) : (
          <div style={tableSectionStyle}>
            <div style={tableMetaStyle}>
              <span style={tableMetaLabelStyle}>Recent Events</span>
              <span style={tableMetaCountStyle}>{limitedEvents.length}</span>
            </div>
            <div style={tableWrapperStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                    <th style={{ ...headerCellStyle, width: "8%" }}>ID</th>
                    {visibleColumns.type && <th style={{ ...headerCellStyle, width: "14%" }}>Type</th>}
                    {visibleColumns.severity && (
                      <th style={{ ...headerCellStyle, width: "10%" }}>Severity</th>
                    )}
                    {visibleColumns.sourceIp && (
                      <th style={{ ...headerCellStyle, width: "13%" }}>Source IP</th>
                    )}
                    {visibleColumns.app && <th style={{ ...headerCellStyle, width: "13%" }}>App</th>}
                    {visibleColumns.message && (
                      <th style={{ ...headerCellStyle, width: "24%" }}>Message</th>
                    )}
                    {visibleColumns.created && <th style={{ ...headerCellStyle, width: "18%" }}>Created</th>}
                  </tr>
                </thead>
                <tbody>
                  {limitedEvents.map((event) => (
                    <tr key={event.id} style={{ ...rowStyle, ...getHighlightStyle(event) }}>
                      <td style={{ ...bodyCellStyle, ...monoCellStyle, fontSize: fontSizeScale.table }}>
                        {event.id}
                      </td>
                      {visibleColumns.type && (
                        <td style={{ ...bodyCellStyle, fontSize: fontSizeScale.table }}>
                          <span style={eventTypeBadgeStyle}>{event.event_type || "unknown"}</span>
                        </td>
                      )}
                      {visibleColumns.severity && (
                        <td style={{ ...bodyCellStyle, fontSize: fontSizeScale.table }}>
                          <span
                            style={{
                              ...eventTypeBadgeStyle,
                              ...getSeverityBadgeStyle(
                                event.severity,
                                displaySettings?.severityColorPreset
                              ),
                            }}
                          >
                            {event.severity || "unknown"}
                          </span>
                        </td>
                      )}
                      {visibleColumns.sourceIp && (
                        <td style={{ ...bodyCellStyle, ...monoCellStyle, fontSize: fontSizeScale.table }}>
                          {event.source_ip || "N/A"}
                        </td>
                      )}
                      {visibleColumns.app && (
                        <td style={{ ...bodyCellStyle, fontSize: fontSizeScale.table }}>
                          {event.app_name || "N/A"}
                        </td>
                      )}
                      {visibleColumns.message && (
                        <td style={{ ...bodyCellStyle, fontSize: fontSizeScale.table }}>
                          {event.message || "N/A"}
                        </td>
                      )}
                      {visibleColumns.created && (
                        <td style={{ ...bodyCellStyle, ...createdCellStyle }} title={event.created_at || ""}>
                          {formatTimestamp(event.created_at, displaySettings, "N/A")}
                        </td>
                      )}
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

const rawLogLineStyle = {
  padding: "5px 4px",
  borderBottom: "1px solid #161b22",
  color: "#d1d5db",
  fontFamily: "'SFMono-Regular', Consolas, 'Liberation Mono', Menlo, monospace",
  fontSize: "12px",
  lineHeight: "1.6",
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
