import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { loadSourceHealth } from "../services/sourceHealthService";
import { formatTimestamp } from "../utils/displayFormatting";
import { getSourceBadgeMeta } from "../utils/alertDisplay";
import { SOURCE_METADATA_BY_ID } from "../utils/sourceMetadata";

function SourceHealthPanel({ pollIntervalMs = 0, displaySettings, onOpenLiveLogs }) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [error, setError] = useState("");
  const mountedRef = useRef(false);

  const refresh = useCallback(async ({ initial = false } = {}) => {
    if (initial) setLoading(true);
    else setRefreshing(true);
    try {
      const response = await loadSourceHealth();
      if (!mountedRef.current) return;
      setData(response);
      setError("");
    } catch (err) {
      if (!mountedRef.current) return;
      setError(err.message || "Unable to load source activity");
    } finally {
      if (!mountedRef.current) return;
      if (initial) setLoading(false);
      else setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    mountedRef.current = true;
    const start = async () => {
      await refresh({ initial: true });
    };
    start();
    if (pollIntervalMs <= 0) return () => { mountedRef.current = false; };
    const intervalId = window.setInterval(() => {
      refresh();
    }, pollIntervalMs);
    return () => {
      mountedRef.current = false;
      window.clearInterval(intervalId);
    };
  }, [pollIntervalMs, refresh]);

  const allNeverSeen = useMemo(
    () => !!data?.sources?.length && data.sources.every((item) => !item.ever_seen),
    [data]
  );

  return (
    <section aria-labelledby="source-health-heading" style={panelStyle}>
      <header style={headerStyle}>
        <div>
          <p style={eyebrowStyle}>Overview</p>
          <h2 id="source-health-heading" data-workspace-heading style={headingStyle}>Source Health</h2>
          <p style={subtitleStyle}>Authoritative stored-event activity. Hour and day windows use UTC.</p>
        </div>
        <button type="button" onClick={() => refresh()} disabled={loading || refreshing} style={refreshButtonStyle}>
          {refreshing ? "Refreshing…" : "Refresh"}
        </button>
      </header>

      {loading && <p role="status" style={stateStyle}>Loading source activity…</p>}
      {!loading && error && !data && <div role="alert" style={errorStyle}>{error}</div>}
      {!loading && error && data && <div role="alert" style={warningStyle}>Refresh failed: {error}. Showing the last successful response.</div>}
      {!loading && allNeverSeen && <p style={emptyStyle}>No recognized source has stored an event yet. All six sources remain visible below.</p>}

      {!loading && data && (
        <>
          <div style={gridStyle} data-testid="source-health-grid">
            {data.sources.map((item) => {
              const metadata = SOURCE_METADATA_BY_ID[item.source];
              const badge = getSourceBadgeMeta(item.source, item.source_type);
              return (
                <article key={item.source} data-source={item.source} style={cardStyle}>
                  <div style={cardTopStyle}>
                    <div>
                      <h3 style={sourceHeadingStyle}>{item.display_label}</h3>
                      <code style={identityStyle}>{item.source} / {item.source_type}</code>
                    </div>
                    <span style={{ ...badgeStyle, ...badge.style }}>{badge.label}</span>
                  </div>
                  <dl style={metricsStyle}>
                    <Metric label="Last event" value={item.ever_seen ? formatTimestamp(item.last_event_at, displaySettings, "Unavailable") : "Never seen"} />
                    <Metric label="Last hour" value={item.events_last_hour.toLocaleString()} />
                    <Metric label="Today (UTC)" value={item.events_today.toLocaleString()} />
                    <Metric label="Total events" value={item.total_events.toLocaleString()} />
                  </dl>
                  {!item.ever_seen && <p style={neverSeenStyle}>No stored events for this source.</p>}
                  <button
                    type="button"
                    onClick={() => onOpenLiveLogs(metadata.liveLogsDestination)}
                    aria-label={`Open ${item.display_label} Live Logs`}
                    style={liveLogsButtonStyle}
                  >
                    Open Live Logs
                  </button>
                </article>
              );
            })}
          </div>
          <p style={observedStyle}>Observed {formatTimestamp(data.generated_at, { ...displaySettings, timezoneMode: "utc" }, data.generated_at)} · UTC boundaries supplied by the API</p>
        </>
      )}
    </section>
  );
}

function Metric({ label, value }) {
  return <div style={metricStyle}><dt style={metricLabelStyle}>{label}</dt><dd style={metricValueStyle}>{value}</dd></div>;
}

const panelStyle = { color: "#f0f6fc" };
const headerStyle = { display: "flex", justifyContent: "space-between", gap: "16px", alignItems: "flex-start", marginBottom: "18px" };
const eyebrowStyle = { margin: "0 0 6px", color: "#58a6ff", fontSize: "12px", fontWeight: 700, textTransform: "uppercase", letterSpacing: "0.08em" };
const headingStyle = { margin: 0, fontSize: "28px" };
const subtitleStyle = { margin: "8px 0 0", color: "#9da7b3" };
const refreshButtonStyle = { border: "1px solid #388bfd", background: "#1f6feb", color: "#fff", borderRadius: "8px", padding: "8px 14px", cursor: "pointer" };
const stateStyle = { color: "#9da7b3", padding: "24px 0" };
const errorStyle = { border: "1px solid #f85149", background: "rgba(248,81,73,.12)", color: "#ffa198", padding: "12px", borderRadius: "8px" };
const warningStyle = { ...errorStyle, borderColor: "#d29922", background: "rgba(210,153,34,.12)", color: "#e3b341", marginBottom: "14px" };
const emptyStyle = { color: "#c9d1d9", background: "#161b22", border: "1px solid #30363d", padding: "12px", borderRadius: "8px" };
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: "16px" };
const cardStyle = { minWidth: 0, background: "#161b22", border: "1px solid #30363d", borderRadius: "12px", padding: "18px", boxShadow: "0 8px 22px rgba(0,0,0,.18)" };
const cardTopStyle = { display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "flex-start" };
const sourceHeadingStyle = { margin: "0 0 5px", fontSize: "18px" };
const identityStyle = { color: "#8c96a1", fontSize: "12px", overflowWrap: "anywhere" };
const badgeStyle = { borderRadius: "999px", padding: "4px 8px", fontSize: "11px", whiteSpace: "nowrap" };
const metricsStyle = { display: "grid", gridTemplateColumns: "1fr 1fr", gap: "12px", margin: "18px 0" };
const metricStyle = { minWidth: 0 };
const metricLabelStyle = { color: "#8c96a1", fontSize: "11px", textTransform: "uppercase", letterSpacing: ".05em" };
const metricValueStyle = { margin: "4px 0 0", color: "#f0f6fc", fontWeight: 700, overflowWrap: "anywhere" };
const neverSeenStyle = { color: "#9da7b3", fontSize: "13px" };
const liveLogsButtonStyle = { border: "1px solid #30363d", background: "#0d1117", color: "#79c0ff", borderRadius: "8px", padding: "7px 10px", cursor: "pointer" };
const observedStyle = { color: "#8c96a1", fontSize: "12px", marginTop: "16px" };

export default SourceHealthPanel;
