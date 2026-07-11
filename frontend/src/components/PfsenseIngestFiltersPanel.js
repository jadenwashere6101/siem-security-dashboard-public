import React, { useCallback, useEffect, useMemo, useState } from "react";
import {
  loadPfsenseIngestFilterMetrics,
  loadPfsenseIngestFilters,
  updatePfsenseIngestFilter,
} from "../services/pfsenseIngestFilterService";
import { formatTimestamp } from "../utils/displayFormatting";

const CATEGORY_LABELS = {
  block_events: "Blocked traffic",
  inbound_sensitive_port_allows: "Inbound sensitive-port allows",
  all_allow_events: "All allowed traffic",
  dns_traffic: "DNS port-53 traffic",
  icmp_traffic: "Allowed IPv4 ICMP traffic",
};

function PfsenseIngestFiltersPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  displaySettings,
}) {
  const [policy, setPolicy] = useState(null);
  const [metrics, setMetrics] = useState(null);
  const [ports, setPorts] = useState("");
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const [nextPolicy, nextMetrics] = await Promise.all([
        loadPfsenseIngestFilters(),
        loadPfsenseIngestFilterMetrics(),
      ]);
      setPolicy(nextPolicy);
      setMetrics(nextMetrics);
      const sensitive = nextPolicy.categories?.inbound_sensitive_port_allows;
      setPorts((sensitive?.parameters?.sensitive_ports || []).join(", "));
    } catch (requestError) {
      setError(requestError.message || "Unable to load pfSense ingest filters");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const parsedPorts = useMemo(() => {
    const parts = ports.split(",").map((value) => value.trim()).filter(Boolean);
    const values = parts.map(Number);
    const valid = parts.length > 0 && values.every(
      (value) => Number.isInteger(value) && value >= 1 && value <= 65535
    ) && new Set(values).size === values.length && values.length <= 64;
    return { valid, values };
  }, [ports]);

  const saveCategory = async (category, enabled, parameters) => {
    setSaving(category);
    setError("");
    setNotice("");
    try {
      await updatePfsenseIngestFilter(category, enabled, parameters);
      await reload();
      setNotice(`${CATEGORY_LABELS[category]} updated. The next pfSense request uses this policy.`);
    } catch (requestError) {
      setError(requestError.message || "Unable to update pfSense ingest filter");
    } finally {
      setSaving("");
    }
  };

  const categories = policy?.categories || {};
  const fallbackActive = ["invalid", "unavailable"].includes(policy?.status);

  return (
    <section style={cardStyle} aria-labelledby="pfsense-filter-title">
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Administration</p>
          <h2 id="pfsense-filter-title" style={cardTitleStyle}>pfSense Ingest Filters</h2>
          <p style={cardSubtitleStyle}>
            Control which normalized firewall events are retained before geolocation and storage.
            Saved changes apply to the next request without restarting either service.
          </p>
        </div>
      </div>

      {loading ? <p style={mutedStyle}>Loading effective policy…</p> : null}
      {error ? <div role="alert" style={errorStyle}>{error}</div> : null}
      {notice ? <div role="status" style={successStyle}>{notice}</div> : null}
      {fallbackActive ? (
        <div role="status" style={warningStyle}>
          Database overrides are {policy.status}. Restrictive source-controlled defaults are active.
        </div>
      ) : null}

      {!loading && policy ? (
        <div style={contentStyle}>
          <div style={policyGridStyle}>
            {Object.entries(categories).map(([category, config]) => (
              <article key={category} style={policyCardStyle}>
                <div style={policyHeadingStyle}>
                  <div>
                    <h3 style={policyTitleStyle}>{CATEGORY_LABELS[category] || category}</h3>
                    <p style={descriptionStyle}>{config.description}</p>
                  </div>
                  <label style={toggleLabelStyle}>
                    <input
                      type="checkbox"
                      checked={Boolean(config.enabled)}
                      disabled={Boolean(saving)}
                      onChange={(event) => saveCategory(category, event.target.checked, config.parameters)}
                    />
                    <span>{config.enabled ? "Enabled" : "Disabled"}</span>
                  </label>
                </div>
                <p style={metadataStyle}>
                  {config.override_status === "applied" ? "Database setting" : "Safe default"}
                  {config.updated_by ? ` · ${config.updated_by}` : ""}
                  {config.updated_at
                    ? ` · ${formatTimestamp(config.updated_at, displaySettings)}`
                    : ""}
                </p>
              </article>
            ))}
          </div>

          <section style={editorStyle} aria-labelledby="sensitive-port-editor-title">
            <h3 id="sensitive-port-editor-title" style={policyTitleStyle}>Canonical sensitive ports</h3>
            <p style={descriptionStyle}>
              Shared by inbound-allow retention and suspicious-allow detection. Enter unique ports
              from 1–65535, separated by commas (maximum 64).
            </p>
            <label htmlFor="pfsense-sensitive-ports" style={fieldLabelStyle}>Sensitive destination ports</label>
            <textarea
              id="pfsense-sensitive-ports"
              value={ports}
              onChange={(event) => setPorts(event.target.value)}
              rows={3}
              style={inputStyle}
              aria-describedby="pfsense-port-validation"
            />
            <div id="pfsense-port-validation" style={parsedPorts.valid ? validStyle : invalidStyle}>
              {parsedPorts.valid ? `${parsedPorts.values.length} valid unique ports` : "Enter 1–64 unique numeric ports."}
            </div>
            <button
              type="button"
              disabled={!parsedPorts.valid || Boolean(saving)}
              onClick={() => saveCategory(
                "inbound_sensitive_port_allows",
                categories.inbound_sensitive_port_allows.enabled,
                { sensitive_ports: parsedPorts.values }
              )}
              style={{ ...buttonStyle, opacity: !parsedPorts.valid || saving ? 0.55 : 1 }}
            >
              {saving === "inbound_sensitive_port_allows" ? "Saving…" : "Save sensitive ports"}
            </button>
          </section>

          <section style={explanationStyle} aria-label="Policy behavior">
            <strong>How retention works:</strong> any enabled matching category retains the event.
            Block retention includes blocked ICMP. DNS means allowed TCP/UDP destination port 53
            only—it does not inspect resolver queries or domains. This controls SIEM storage, not
            firewall enforcement.
          </section>

          <section style={metricsStyle} aria-labelledby="filter-metrics-title">
            <h3 id="filter-metrics-title" style={policyTitleStyle}>Backend decision counters</h3>
            <p style={descriptionStyle}>
              Process-local aggregates since {formatTimestamp(metrics?.started_at, displaySettings)}. Counters
              reset when the backend restarts and never store filtered payloads. Listener transport
              outcomes ({(metrics?.listener_outcome_contract || []).join(", ") || "forwarded, filtered, ingested, rejected, backend_failed"})
              remain separate in listener operational statistics.
            </p>
            <div style={counterGridStyle}>
              {Object.entries(metrics?.counts || {}).length ? Object.entries(metrics.counts).map(([reason, count]) => (
                <div key={reason} style={counterStyle}><span>{reason}</span><strong>{count}</strong></div>
              )) : <span style={mutedStyle}>No decisions recorded since process start.</span>}
            </div>
          </section>
        </div>
      ) : null}
    </section>
  );
}

const sectionLabelStyle = { margin: "0 0 6px", color: "#67e8f9", fontSize: 12, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase" };
const contentStyle = { display: "grid", gap: 20, paddingTop: 16 };
const policyGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(280px, 1fr))", gap: 14 };
const policyCardStyle = { padding: 16, border: "1px solid #334155", borderRadius: 12, background: "#0f172a" };
const policyHeadingStyle = { display: "flex", justifyContent: "space-between", gap: 16, alignItems: "flex-start" };
const policyTitleStyle = { margin: 0, color: "#f8fafc", fontSize: 16 };
const descriptionStyle = { margin: "6px 0 0", color: "#cbd5e1", lineHeight: 1.55, fontSize: 13 };
const toggleLabelStyle = { display: "flex", alignItems: "center", gap: 7, color: "#e2e8f0", fontWeight: 700, whiteSpace: "nowrap" };
const metadataStyle = { margin: "12px 0 0", color: "#94a3b8", fontSize: 12 };
const editorStyle = { padding: 18, border: "1px solid #334155", borderRadius: 12, background: "#111827" };
const fieldLabelStyle = { display: "block", margin: "14px 0 7px", color: "#e2e8f0", fontWeight: 700 };
const inputStyle = { width: "100%", boxSizing: "border-box", padding: 11, borderRadius: 8, border: "1px solid #475569", background: "#020617", color: "#f8fafc", resize: "vertical" };
const validStyle = { marginTop: 6, color: "#86efac", fontSize: 12 };
const invalidStyle = { marginTop: 6, color: "#fca5a5", fontSize: 12 };
const buttonStyle = { marginTop: 12, padding: "9px 14px", border: 0, borderRadius: 8, background: "#0891b2", color: "#fff", fontWeight: 800, cursor: "pointer" };
const explanationStyle = { padding: 16, borderRadius: 10, background: "#082f49", color: "#e0f2fe", lineHeight: 1.6 };
const metricsStyle = { padding: 18, border: "1px solid #334155", borderRadius: 12, background: "#0f172a" };
const counterGridStyle = { display: "grid", gap: 8, marginTop: 12 };
const counterStyle = { display: "flex", justifyContent: "space-between", gap: 12, color: "#cbd5e1", fontSize: 13 };
const mutedStyle = { color: "#94a3b8" };
const errorStyle = { marginTop: 14, padding: 12, borderRadius: 8, background: "#450a0a", color: "#fecaca" };
const successStyle = { marginTop: 14, padding: 12, borderRadius: 8, background: "#052e16", color: "#bbf7d0" };
const warningStyle = { marginTop: 14, padding: 12, borderRadius: 8, background: "#422006", color: "#fde68a" };

export default PfsenseIngestFiltersPanel;
