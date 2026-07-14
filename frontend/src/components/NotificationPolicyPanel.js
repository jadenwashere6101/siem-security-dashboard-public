import React, { useCallback, useEffect, useState } from "react";

import {
  loadNotificationPolicy,
  testNotificationPolicyRoute,
  updateNotificationPolicy,
} from "../services/notificationPolicyService";
import { formatTimestamp } from "../utils/displayFormatting";

const SEVERITY_OPTIONS = ["low", "medium", "high", "critical"];
const FORMAT_OPTIONS = ["compact", "detailed"];

function NotificationPolicyPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  displaySettings,
  onNavigate,
}) {
  const [policy, setPolicy] = useState(null);
  const [draft, setDraft] = useState(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [testingRoute, setTestingRoute] = useState("");
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const reload = useCallback(async () => {
    setLoading(true);
    setError("");
    try {
      const nextPolicy = await loadNotificationPolicy();
      setPolicy(nextPolicy);
      setDraft(nextPolicy);
    } catch (requestError) {
      setError(requestError.message || "Unable to load notification policy");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const updateDraft = (field, value) => {
    setDraft((current) => ({
      ...current,
      [field]: value,
    }));
  };

  const savePolicy = async () => {
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const updated = await updateNotificationPolicy({
        slack_enabled: !!draft.slack_enabled,
        minimum_severity: draft.minimum_severity,
        notify_on_alerts: !!draft.notify_on_alerts,
        notify_on_incidents: !!draft.notify_on_incidents,
        slack_format: draft.slack_format,
        pfsense_destination: draft.pfsense_destination,
        honeypot_destination: draft.honeypot_destination,
        critical_cross_source_destination: draft.critical_cross_source_destination,
      });
      setPolicy(updated);
      setDraft(updated);
      setNotice("Notification policy updated.");
    } catch (requestError) {
      setError(requestError.message || "Unable to update notification policy");
    } finally {
      setSaving(false);
    }
  };

  const runRouteTest = async (routeKey) => {
    setTestingRoute(routeKey);
    setError("");
    setNotice("");
    try {
      const result = await testNotificationPolicyRoute(routeKey);
      setNotice(result.message || "Notification policy route test completed.");
    } catch (requestError) {
      setError(requestError.message || "Unable to run notification policy route test");
    } finally {
      setTestingRoute("");
    }
  };

  return (
    <section style={cardStyle} aria-labelledby="notification-policy-title">
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Administration</p>
          <h2 id="notification-policy-title" style={cardTitleStyle}>Notification Policy</h2>
          <p style={cardSubtitleStyle}>
            Configure policy-driven Slack delivery for alerts and incidents. This panel stores
            routing labels only; Slack credentials remain in the existing runtime secret
            mechanism.
          </p>
        </div>
      </div>

      {loading ? <p style={mutedStyle}>Loading notification policy…</p> : null}
      {error ? <div role="alert" style={errorStyle}>{error}</div> : null}
      {notice ? <div role="status" style={successStyle}>{notice}</div> : null}

      {!loading && draft ? (
        <div style={contentStyle}>
          <div style={metadataStyle}>
            Effective policy
            {policy?.updated_by ? ` · ${policy.updated_by}` : ""}
            {policy?.updated_at ? ` · ${formatTimestamp(policy.updated_at, displaySettings)}` : " · defaults"}
          </div>

          <div style={gridStyle}>
            <label style={fieldStyle}>
              <span style={labelStyle}>Slack notifications enabled</span>
              <input
                type="checkbox"
                checked={!!draft.slack_enabled}
                onChange={(event) => updateDraft("slack_enabled", event.target.checked)}
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Minimum severity</span>
              <select
                value={draft.minimum_severity}
                onChange={(event) => updateDraft("minimum_severity", event.target.value)}
                style={selectStyle}
              >
                {SEVERITY_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Notify on alerts</span>
              <input
                type="checkbox"
                checked={!!draft.notify_on_alerts}
                onChange={(event) => updateDraft("notify_on_alerts", event.target.checked)}
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Notify on incidents</span>
              <input
                type="checkbox"
                checked={!!draft.notify_on_incidents}
                onChange={(event) => updateDraft("notify_on_incidents", event.target.checked)}
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Slack format</span>
              <select
                value={draft.slack_format}
                onChange={(event) => updateDraft("slack_format", event.target.value)}
                style={selectStyle}
              >
                {FORMAT_OPTIONS.map((option) => (
                  <option key={option} value={option}>{option}</option>
                ))}
              </select>
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>pfSense destination label</span>
              <input
                type="text"
                value={draft.pfsense_destination}
                onChange={(event) => updateDraft("pfsense_destination", event.target.value)}
                style={inputStyle}
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Honeypot destination label</span>
              <input
                type="text"
                value={draft.honeypot_destination}
                onChange={(event) => updateDraft("honeypot_destination", event.target.value)}
                style={inputStyle}
              />
            </label>

            <label style={fieldStyle}>
              <span style={labelStyle}>Critical cross-source destination label</span>
              <input
                type="text"
                value={draft.critical_cross_source_destination}
                onChange={(event) =>
                  updateDraft("critical_cross_source_destination", event.target.value)
                }
                style={inputStyle}
              />
            </label>
          </div>

          <div style={noteStyle}>
            Policy suppression affects Slack delivery only. Alerts, incidents, playbooks, audit
            evidence, and UI visibility remain unchanged.
          </div>

          <div style={linkRowStyle}>
            <button type="button" onClick={() => onNavigate?.("severity-response-matrix")} style={secondaryButtonStyle}>
              Open Severity &amp; Response Matrix
            </button>
            <button type="button" onClick={() => onNavigate?.("detection-rules")} style={secondaryButtonStyle}>
              Open Detection Rules
            </button>
          </div>

          <div style={testPanelStyle}>
            <div style={testTextStyle}>
              Route tests send a synthetic notification-policy message through the real pfSense or
              honeypot routing path without creating alerts, incidents, playbooks, approvals, or
              SOAR executions. These tests may bypass only the global Slack-disabled gate for
              controlled admin verification.
            </div>
            <div style={testActionsStyle}>
              <button
                type="button"
                onClick={() => runRouteTest("pfsense")}
                disabled={!!testingRoute || saving}
                style={{ ...secondaryButtonStyle, opacity: testingRoute || saving ? 0.6 : 1 }}
              >
                {testingRoute === "pfsense" ? "Testing pfSense…" : "Test pfSense route"}
              </button>
              <button
                type="button"
                onClick={() => runRouteTest("honeypot")}
                disabled={!!testingRoute || saving}
                style={{ ...secondaryButtonStyle, opacity: testingRoute || saving ? 0.6 : 1 }}
              >
                {testingRoute === "honeypot" ? "Testing Honeypot…" : "Test Honeypot route"}
              </button>
            </div>
          </div>

          <button
            type="button"
            onClick={savePolicy}
            disabled={saving}
            style={{ ...buttonStyle, opacity: saving ? 0.6 : 1 }}
          >
            {saving ? "Saving…" : "Save notification policy"}
          </button>
        </div>
      ) : null}
    </section>
  );
}

const sectionLabelStyle = { margin: "0 0 6px", color: "#67e8f9", fontSize: 12, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase" };
const mutedStyle = { color: "#94a3b8" };
const errorStyle = { marginTop: 14, padding: 12, borderRadius: 8, background: "#450a0a", color: "#fecaca" };
const successStyle = { marginTop: 14, padding: 12, borderRadius: 8, background: "#052e16", color: "#bbf7d0" };
const contentStyle = { display: "grid", gap: 18, paddingTop: 16 };
const metadataStyle = { color: "#94a3b8", fontSize: 12 };
const gridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 14 };
const fieldStyle = { display: "grid", gap: 8, color: "#e2e8f0" };
const labelStyle = { fontWeight: 700 };
const selectStyle = { padding: 10, borderRadius: 8, border: "1px solid #475569", background: "#020617", color: "#f8fafc" };
const inputStyle = { padding: 10, borderRadius: 8, border: "1px solid #475569", background: "#020617", color: "#f8fafc" };
const noteStyle = { padding: 14, borderRadius: 10, background: "#082f49", color: "#e0f2fe", lineHeight: 1.6 };
const buttonStyle = { padding: "10px 15px", border: 0, borderRadius: 8, background: "#0891b2", color: "#fff", fontWeight: 800, cursor: "pointer", justifySelf: "start" };
const testPanelStyle = { display: "grid", gap: 12, padding: 14, borderRadius: 10, background: "#172554", color: "#dbeafe" };
const testTextStyle = { lineHeight: 1.6 };
const testActionsStyle = { display: "flex", gap: 10, flexWrap: "wrap" };
const linkRowStyle = { display: "flex", gap: 10, flexWrap: "wrap" };
const secondaryButtonStyle = { padding: "10px 15px", border: "1px solid #38bdf8", borderRadius: 8, background: "#0f172a", color: "#e0f2fe", fontWeight: 700, cursor: "pointer" };

export default NotificationPolicyPanel;
