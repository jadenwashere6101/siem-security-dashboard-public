import React, { useEffect, useRef, useState } from "react";
import ThreatHuntEventDetails from "./ThreatHuntEventDetails";
import { buildSiemPath } from "../utils/siemPath";
import {
  formatCreatedAt,
  formatRawPayload,
  getEventTypeBadgeStyle,
  getReputationBadgeStyle,
  getSeverityBadgeStyle,
  getSourceBadgeMeta,
  groupEventsByDate,
} from "../utils/threatHuntDisplay";

function ThreatHuntPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
  onViewRelatedAlerts,
}) {
  const [sourceIp, setSourceIp] = useState("");
  const [source, setSource] = useState("");
  const [eventType, setEventType] = useState("");
  const [startTime, setStartTime] = useState("");
  const [endTime, setEndTime] = useState("");
  const [events, setEvents] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [expandedEventId, setExpandedEventId] = useState(null);
  const [copyFeedback, setCopyFeedback] = useState("");
  const [pivotFeedback, setPivotFeedback] = useState("");
  const [pivotHighlightActive, setPivotHighlightActive] = useState(false);
  const sourceIpInputRef = useRef(null);

  useEffect(() => {
    sourceIpInputRef.current?.focus();
  }, []);

  const runSearch = async ({
    sourceIpValue = sourceIp,
    sourceValue = source,
    eventTypeValue = eventType,
    startTimeValue = startTime,
    endTimeValue = endTime,
  } = {}) => {
    setLoading(true);
    setError("");

    try {
      const params = new URLSearchParams();
      if (sourceIpValue.trim()) params.set("source_ip", sourceIpValue.trim());
      if (sourceValue) params.set("source", sourceValue);
      if (eventTypeValue) params.set("event_type", eventTypeValue);
      if (startTimeValue) params.set("start_time", new Date(startTimeValue).toISOString());
      if (endTimeValue) params.set("end_time", new Date(endTimeValue).toISOString());

      const searchPath = params.toString()
        ? `${buildSiemPath("/events/search")}?${params.toString()}`
        : buildSiemPath("/events/search");

      const res = await fetch(searchPath, {
        credentials: "include",
      });
      const data = await res.json().catch(() => []);

      if (!res.ok) {
        throw new Error(data.error || "Unable to search events");
      }

      setEvents(Array.isArray(data) ? data : []);
    } catch (err) {
      setError(err.message || "Unable to search events");
      setEvents([]);
    } finally {
      setLoading(false);
    }
  };

  const handleSearch = async (e) => {
    e.preventDefault();
    await runSearch();
  };

  const handleClearFilters = () => {
    setSourceIp("");
    setSource("");
    setEventType("");
    setStartTime("");
    setEndTime("");
    setEvents([]);
    setError("");
    setExpandedEventId(null);
  };

  const handleSearchThisIp = async (nextSourceIp) => {
    setSourceIp(nextSourceIp || "");
    setPivotHighlightActive(true);
    setPivotFeedback(`Searching events for ${nextSourceIp || "this IP"}...`);
    sourceIpInputRef.current?.focus();
    window.setTimeout(() => {
      setPivotHighlightActive(false);
      setPivotFeedback("");
    }, 1800);
    await runSearch({ sourceIpValue: nextSourceIp || "" });
  };

  const showCopyFeedback = (message) => {
    setCopyFeedback(message);
    window.setTimeout(() => {
      setCopyFeedback("");
    }, 1800);
  };

  const handleCopyValue = async (value, successMessage) => {
    try {
      await navigator.clipboard.writeText(value);
      showCopyFeedback(successMessage);
    } catch (_error) {
      showCopyFeedback("Copy failed");
    }
  };

  const groupedEvents = groupEventsByDate(events);

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Threat Hunting</p>
          <h2 style={cardTitleStyle}>Raw Event Search</h2>
          <p style={cardSubtitleStyle}>
            Search ingested events by source IP, event type, and time range.
          </p>
        </div>
      </div>

      <div style={panelContentStyle}>
        <form onSubmit={handleSearch} style={formStyle}>
          <div style={filtersGridStyle}>
            <div style={filterFieldStyle}>
              <label style={filterLabelStyle}>Source IP</label>
              <input
                ref={sourceIpInputRef}
                type="text"
                value={sourceIp}
                onChange={(e) => setSourceIp(e.target.value)}
                placeholder="e.g. 203.0.113.10"
                style={{
                  ...inputStyle,
                  ...(pivotHighlightActive ? highlightedInputStyle : null),
                }}
              />
            </div>

            <div style={filterFieldStyle}>
              <label style={filterLabelStyle}>Source</label>
              <select
                value={source}
                onChange={(e) => setSource(e.target.value)}
                style={selectStyle}
              >
                <option value="">All Sources</option>
                <option value="bank_app">bank_app</option>
                <option value="nginx">nginx</option>
                <option value="azure_insights">azure_insights</option>
                <option value="opentelemetry">opentelemetry</option>
              </select>
            </div>

            <div style={filterFieldStyle}>
              <label style={filterLabelStyle}>Event Type</label>
              <select
                value={eventType}
                onChange={(e) => setEventType(e.target.value)}
                style={selectStyle}
              >
                <option value="">All Event Types</option>
                <option value="failed_login">failed_login</option>
                <option value="login_failure">login_failure</option>
                <option value="successful_login">successful_login</option>
                <option value="port_scan">port_scan</option>
                <option value="unauthorized_access">unauthorized_access</option>
                <option value="http_error">http_error</option>
                <option value="application_exception">application_exception</option>
                <option value="availability_failure">availability_failure</option>
                <option value="normal_activity">normal_activity</option>
              </select>
            </div>

            <div style={filterFieldStyle}>
              <label style={filterLabelStyle}>Start Time (optional)</label>
              <input
                type="datetime-local"
                value={startTime}
                onChange={(e) => setStartTime(e.target.value)}
                style={dateTimeInputStyle}
              />
              <p style={helperTextStyle}>Filter events after this time</p>
            </div>

            <div style={filterFieldStyle}>
              <label style={filterLabelStyle}>End Time (optional)</label>
              <input
                type="datetime-local"
                value={endTime}
                onChange={(e) => setEndTime(e.target.value)}
                style={dateTimeInputStyle}
              />
              <p style={helperTextStyle}>Filter events before this time</p>
            </div>
          </div>

          <div style={actionsRowStyle}>
            <button type="submit" disabled={loading} style={searchButtonStyle}>
              {loading ? "Searching..." : "Run Search"}
            </button>
            <button
              type="button"
              onClick={handleClearFilters}
              disabled={loading}
              style={clearButtonStyle}
            >
              Clear Filters
            </button>
            {loading && <span style={searchStatusStyle}>Searching raw events...</span>}
          </div>
          {pivotFeedback && <p style={pivotFeedbackStyle}>{pivotFeedback}</p>}
        </form>

        {error ? (
          <div style={errorStateStyle}>{error}</div>
        ) : events.length === 0 ? (
          <p style={emptyTextStyle}>
            {loading ? "Searching raw events..." : "No events found for the selected filters."}
          </p>
        ) : (
          <div style={resultsSectionStyle}>
            <div style={resultsMetaStyle}>
              <span style={resultsLabelStyle}>Matching Events</span>
              <span style={resultsCountStyle}>Showing {events.length} results</span>
            </div>
            <div style={tableWrapperStyle}>
              <table style={tableStyle}>
                <thead>
                  <tr>
                        <th style={{ ...headerCellStyle, width: "16%" }}>Created</th>
                        <th style={{ ...headerCellStyle, width: "12%" }}>Event Type</th>
                        <th style={{ ...headerCellStyle, width: "10%" }}>Severity</th>
                        <th style={{ ...headerCellStyle, width: "12%" }}>Source</th>
                        <th style={{ ...headerCellStyle, width: "12%" }}>Source IP</th>
                    <th style={{ ...headerCellStyle, width: "12%" }}>Behavior</th>
                    <th style={{ ...headerCellStyle, width: "8%" }}>App</th>
                    <th style={{ ...headerCellStyle, width: "8%" }}>Environment</th>
                    <th style={{ ...headerCellStyle, width: "18%" }}>Message</th>
                  </tr>
                </thead>
                <tbody>
                  {groupedEvents.map((group) => (
                    <React.Fragment key={group.label}>
                      <tr>
                        <td colSpan={9} style={groupHeaderCellStyle}>
                          <div style={groupHeaderStyle}>{group.label}</div>
                        </td>
                      </tr>
                      {group.events.map((event) => {
                        const isExpanded = expandedEventId === event.id;
                        const sourceBadge = getSourceBadgeMeta(event.source, event.source_type);

                        return (
                          <React.Fragment key={event.id}>
                            <tr
                              style={{
                                ...rowStyle,
                                ...(isExpanded ? expandedRowStyle : null),
                              }}
                              onClick={() =>
                                setExpandedEventId((currentId) =>
                                  currentId === event.id ? null : event.id
                                )
                              }
                            >
                              <td style={bodyCellStyle}>{formatCreatedAt(event.created_at)}</td>
                              <td style={bodyCellStyle}>
                                <span style={{ ...eventTypeBadgeStyle, ...getEventTypeBadgeStyle(event.event_type) }}>
                                  {event.event_type}
                                </span>
                              </td>
                              <td style={bodyCellStyle}>
                                <span style={{ ...severityBadgeStyle, ...getSeverityBadgeStyle(event.severity) }}>
                                  {event.severity}
                                </span>
                              </td>
                              <td style={bodyCellStyle}>
                                <div style={sourceBadgeStackStyle}>
                                  <span style={{ ...sourceBadgeStyle, ...sourceBadge.style }}>
                                    {sourceBadge.label}
                                  </span>
                                  <span style={sourceTypeTextStyle}>{sourceBadge.subLabel}</span>
                                </div>
                              </td>
                              <td style={{ ...bodyCellStyle, ...monoCellStyle }}>{event.source_ip}</td>
                              <td style={bodyCellStyle}>
                                <div style={sourceBadgeStackStyle}>
                                  <span style={{ ...sourceBadgeStyle, ...getReputationBadgeStyle(event.reputation_label) }}>
                                    {event.reputation_label || "Normal"}
                                  </span>
                                  <span style={sourceTypeTextStyle}>Score {event.reputation_score ?? 0}</span>
                                </div>
                              </td>
                              <td style={bodyCellStyle}>{event.app_name}</td>
                              <td style={bodyCellStyle}>{event.environment}</td>
                              <td style={{ ...bodyCellStyle, ...messageCellStyle }} title={event.message}>
                                {event.message}
                              </td>
                            </tr>
                            {isExpanded && (
                              <tr>
                                <td colSpan={9} style={expandedCellStyle}>
                                  <div style={expandedContentStyle}>
                                    <div style={expandedActionsRowStyle}>
                                      <button
                                        type="button"
                                        style={copyActionButtonStyle}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          onViewRelatedAlerts?.(event.source_ip || "");
                                        }}
                                      >
                                        View Related Alerts
                                      </button>
                                      <button
                                        type="button"
                                        style={copyActionButtonStyle}
                                        onClick={async (e) => {
                                          e.stopPropagation();
                                          await handleSearchThisIp(event.source_ip || "");
                                        }}
                                      >
                                        Search this IP
                                      </button>
                                      <button
                                        type="button"
                                        style={copyActionButtonStyle}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleCopyValue(event.source_ip || "", "Copied IP");
                                        }}
                                      >
                                        Copy IP
                                      </button>
                                      <button
                                        type="button"
                                        style={copyActionButtonStyle}
                                        onClick={(e) => {
                                          e.stopPropagation();
                                          handleCopyValue(
                                            formatRawPayload(event.raw_payload),
                                            "Copied Payload"
                                          );
                                        }}
                                      >
                                        Copy Payload
                                      </button>
                                      {copyFeedback && <span style={copyFeedbackStyle}>{copyFeedback}</span>}
                                    </div>
                                    <ThreatHuntEventDetails
                                      event={event}
                                      sourceBadge={sourceBadge}
                                      getReputationBadgeStyle={getReputationBadgeStyle}
                                      formatRawPayload={formatRawPayload}
                                      expandedDetailTextStyle={expandedDetailTextStyle}
                                      expandedSupportTextStyle={expandedSupportTextStyle}
                                      expandedSignalsLabelStyle={expandedSignalsLabelStyle}
                                      expandedLabelStyle={expandedLabelStyle}
                                      sourceBadgeStyle={sourceBadgeStyle}
                                      sourceTypeTextStyle={sourceTypeTextStyle}
                                      signalRowStyle={signalRowStyle}
                                      noSignalTextStyle={noSignalTextStyle}
                                      rawPayloadStyle={rawPayloadStyle}
                                    />
                                  </div>
                                </td>
                              </tr>
                            )}
                          </React.Fragment>
                        );
                      })}
                    </React.Fragment>
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

const formStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "18px",
};

const filtersGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(220px, 1fr))",
  gap: "16px",
};

const filterFieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const inputStyle = {
  width: "100%",
  padding: "10px 12px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  fontSize: "13px",
  outline: "none",
  boxSizing: "border-box",
};

const highlightedInputStyle = {
  border: "1px solid rgba(59, 130, 246, 0.55)",
  boxShadow: "0 0 0 3px rgba(59, 130, 246, 0.16)",
};

const dateTimeInputStyle = {
  ...inputStyle,
  cursor: "pointer",
};

const helperTextStyle = {
  margin: 0,
  color: "#8b949e",
  fontSize: "12px",
  lineHeight: "1.4",
};

const actionsRowStyle = {
  display: "flex",
  alignItems: "center",
  gap: "12px",
  flexWrap: "wrap",
};

const searchButtonStyle = {
  padding: "10px 14px",
  borderRadius: "10px",
  border: "1px solid rgba(59, 130, 246, 0.35)",
  backgroundColor: "rgba(37, 99, 235, 0.15)",
  color: "#bfdbfe",
  fontSize: "13px",
  fontWeight: "700",
  cursor: "pointer",
};

const clearButtonStyle = {
  padding: "10px 14px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "13px",
  fontWeight: "700",
  cursor: "pointer",
};

const searchStatusStyle = {
  color: "#8b949e",
  fontSize: "13px",
  fontWeight: "600",
};

const pivotFeedbackStyle = {
  margin: "-4px 0 0 0",
  color: "#93c5fd",
  fontSize: "13px",
  fontWeight: "600",
};

const resultsSectionStyle = {
  marginTop: "22px",
  borderTop: "1px solid #21262d",
  paddingTop: "18px",
};

const resultsMetaStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  marginBottom: "12px",
};

const resultsLabelStyle = {
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const resultsCountStyle = {
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

const groupHeaderCellStyle = {
  padding: "18px 0 10px",
  backgroundColor: "#111827",
  borderBottom: "none",
};

const groupHeaderStyle = {
  color: "#c9d1d9",
  fontSize: "13px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  paddingTop: "8px",
  borderTop: "1px solid #21262d",
};

const bodyCellStyle = {
  padding: "14px",
  color: "#e6edf3",
  borderBottom: "1px solid #30363d",
  fontSize: "13px",
  verticalAlign: "middle",
};

const eventTypeBadgeStyle = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const severityBadgeStyle = {
  display: "inline-block",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};
const sourceBadgeStackStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};
const sourceBadgeStyle = {
  display: "inline-block",
  width: "fit-content",
  padding: "4px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};
const sourceTypeTextStyle = {
  color: "#8b949e",
  fontSize: "11px",
};

const rowStyle = {
  backgroundColor: "#161b22",
  cursor: "pointer",
};

const expandedRowStyle = {
  backgroundColor: "#18202b",
};

const monoCellStyle = {
  fontFamily: "'Courier New', monospace",
  fontSize: "12px",
  color: "#d29922",
};

const messageCellStyle = {
  maxWidth: "360px",
  whiteSpace: "nowrap",
  overflow: "hidden",
  textOverflow: "ellipsis",
};

const emptyTextStyle = {
  margin: "18px 0 0 0",
  color: "#8b949e",
  fontSize: "14px",
};

const errorStateStyle = {
  marginTop: "18px",
  padding: "10px 12px",
  borderRadius: "8px",
  fontSize: "13px",
  fontWeight: "600",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
  color: "#fca5a5",
};

const expandedCellStyle = {
  padding: 0,
  backgroundColor: "#111827",
  borderBottom: "1px solid #30363d",
};

const expandedContentStyle = {
  padding: "16px 18px 18px",
  borderTop: "1px solid #30363d",
};

const expandedActionsRowStyle = {
  display: "flex",
  alignItems: "center",
  gap: "10px",
  flexWrap: "wrap",
  marginBottom: "12px",
};

const expandedLabelStyle = {
  margin: "0 0 10px 0",
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};
const expandedDetailTextStyle = {
  margin: "0 0 10px 0",
  color: "#e6edf3",
  fontSize: "13px",
};
const expandedSupportTextStyle = {
  margin: "0 0 10px 0",
  color: "#8b949e",
  fontSize: "12px",
};
const expandedSignalsLabelStyle = {
  display: "block",
  marginBottom: "8px",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
};
const signalRowStyle = {
  marginTop: "6px",
  padding: "8px 10px",
  borderRadius: "8px",
  backgroundColor: "#111827",
  border: "1px solid #30363d",
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
  fontSize: "12px",
  color: "#e6edf3",
};
const noSignalTextStyle = {
  color: "#8b949e",
  fontSize: "12px",
};

const copyActionButtonStyle = {
  padding: "8px 12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const copyFeedbackStyle = {
  color: "#86efac",
  fontSize: "12px",
  fontWeight: "700",
};

const rawPayloadStyle = {
  margin: 0,
  padding: "14px 16px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#c9d1d9",
  fontSize: "12px",
  lineHeight: "1.5",
  fontFamily: "'Courier New', monospace",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

export default ThreatHuntPanel;
