import React, { useCallback, useEffect, useMemo, useState } from "react";

import {
  loadAiGatewayConfig,
  updateAiGatewayConfig,
} from "../services/aiGatewayConfigService";
import { formatTimestamp } from "../utils/displayFormatting";

const GATEWAY_MODES = [
  { value: "disabled", label: "Disabled" },
  { value: "local_only", label: "Local only" },
  { value: "ask_before_paid_fallback", label: "Ask before paid fallback" },
  { value: "automatic_fallback", label: "Automatic fallback" },
];

const STATUS_LABELS = {
  applied: "Runtime policy applied",
  default: "Source-controlled default",
  invalid: "Invalid runtime policy — fail closed",
  unavailable: "Configuration store unavailable — fail closed",
};

const toDraft = (configuration = {}) => ({
  gateway_mode: configuration.gateway_mode || "disabled",
  anthropic_routing_enabled: Boolean(configuration.anthropic_routing_enabled),
  preferred_anthropic_model: configuration.preferred_anthropic_model || "",
  daily_paid_budget_usd: String(configuration.daily_paid_budget_usd ?? ""),
});

function AiGatewayConfigPanel({
  userRole,
  displaySettings,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
}) {
  const isSuperAdmin = userRole === "super_admin";
  const [policy, setPolicy] = useState(null);
  const [draft, setDraft] = useState(toDraft());
  const [loading, setLoading] = useState(isSuperAdmin);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  const applyResponse = useCallback((nextPolicy) => {
    setPolicy(nextPolicy);
    setDraft(toDraft(nextPolicy.configuration));
  }, []);

  const reload = useCallback(async () => {
    if (!isSuperAdmin) return;
    setLoading(true);
    setError("");
    try {
      applyResponse(await loadAiGatewayConfig());
    } catch (requestError) {
      setError(requestError.message || "Unable to load AI gateway configuration");
    } finally {
      setLoading(false);
    }
  }, [applyResponse, isSuperAdmin]);

  useEffect(() => {
    reload();
  }, [reload]);

  const validationError = useMemo(() => {
    const budget = Number(draft.daily_paid_budget_usd);
    if (!draft.preferred_anthropic_model.trim() && draft.anthropic_routing_enabled) {
      return "A preferred Anthropic model is required when routing is enabled.";
    }
    if (draft.daily_paid_budget_usd === "" || !Number.isFinite(budget) || budget < 0) {
      return "Daily paid budget must be a non-negative number.";
    }
    if (draft.anthropic_routing_enabled && budget <= 0) {
      return "Daily paid budget must be greater than zero when routing is enabled.";
    }
    return "";
  }, [draft]);

  const failClosed = ["invalid", "unavailable"].includes(policy?.status);
  const effective = policy?.effective || {};

  const save = async (event) => {
    event.preventDefault();
    if (validationError || failClosed) return;
    setSaving(true);
    setError("");
    setNotice("");
    try {
      const nextPolicy = await updateAiGatewayConfig({
        gateway_mode: draft.gateway_mode,
        anthropic_routing_enabled: draft.anthropic_routing_enabled,
        preferred_anthropic_model: draft.preferred_anthropic_model.trim(),
        daily_paid_budget_usd: Number(draft.daily_paid_budget_usd),
      });
      applyResponse(nextPolicy);
      setNotice("AI gateway policy updated. The next request uses this configuration.");
    } catch (requestError) {
      setError(requestError.message || "Unable to update AI gateway configuration");
    } finally {
      setSaving(false);
    }
  };

  if (!isSuperAdmin) {
    return (
      <section style={cardStyle} aria-labelledby="ai-gateway-config-title">
        <h2 id="ai-gateway-config-title" style={cardTitleStyle}>AI Gateway Policy</h2>
        <div role="alert" style={errorStyle}>Super-admin access is required.</div>
      </section>
    );
  }

  return (
    <section style={cardStyle} aria-labelledby="ai-gateway-config-title">
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>Administration</p>
          <h2 id="ai-gateway-config-title" style={cardTitleStyle}>AI Gateway Policy</h2>
          <p style={cardSubtitleStyle}>
            Manage the non-secret hybrid gateway policy. Saved changes apply to the next AI
            request without restarting services.
          </p>
        </div>
      </div>

      {loading ? <p style={mutedStyle}>Loading effective gateway policy…</p> : null}
      {error ? <div role="alert" style={errorStyle}>{error}</div> : null}
      {notice ? <div role="status" style={successStyle}>{notice}</div> : null}
      {failClosed ? (
        <div role="status" style={warningStyle}>
          {STATUS_LABELS[policy.status]}. Paid routing is disabled and the effective policy is
          {` ${effective.gateway_mode || "disabled"}`}.
        </div>
      ) : null}

      {!loading && policy ? (
        <div style={contentStyle}>
          <section style={statusCardStyle} aria-labelledby="effective-policy-heading">
            <div style={statusHeadingStyle}>
              <div>
                <p style={sectionLabelStyle}>Effective policy status</p>
                <h3 id="effective-policy-heading" style={subheadingStyle}>
                  {STATUS_LABELS[policy.status] || "Unknown policy state"}
                </h3>
              </div>
              <span style={failClosed ? dangerBadgeStyle : healthyBadgeStyle}>
                {failClosed ? "Fail closed" : "Active"}
              </span>
            </div>
            <dl style={metadataGridStyle}>
              <Metadata label="Gateway mode" value={effective.gateway_mode} />
              <Metadata
                label="Anthropic routing"
                value={effective.anthropic_routing_enabled ? "Enabled" : "Disabled"}
              />
              <Metadata label="Preferred Anthropic model" value={effective.preferred_anthropic_model || "Not configured"} />
              <Metadata label="Daily paid budget" value={formatBudget(effective.daily_paid_budget_usd)} />
              <Metadata label="Updated by" value={policy.updated_by || "Source-controlled default"} />
              <Metadata
                label="Updated at"
                value={formatTimestamp(policy.updated_at, displaySettings, "Not yet updated")}
              />
            </dl>
          </section>

          <form onSubmit={save} style={formStyle} aria-labelledby="gateway-policy-editor-heading">
            <h3 id="gateway-policy-editor-heading" style={subheadingStyle}>Runtime configuration</h3>
            <p style={descriptionStyle}>
              Provider credentials and endpoints are intentionally managed outside this page.
            </p>

            <div style={fieldGridStyle}>
              <label style={fieldLabelStyle}>
                <span>Gateway mode</span>
                <select
                  value={draft.gateway_mode}
                  onChange={(event) => setDraft((current) => ({ ...current, gateway_mode: event.target.value }))}
                  disabled={saving || failClosed}
                  style={inputStyle}
                >
                  {GATEWAY_MODES.map((mode) => (
                    <option key={mode.value} value={mode.value}>{mode.label}</option>
                  ))}
                </select>
              </label>

              <label style={fieldLabelStyle}>
                <span>Preferred Anthropic model</span>
                <input
                  type="text"
                  value={draft.preferred_anthropic_model}
                  onChange={(event) => setDraft((current) => ({ ...current, preferred_anthropic_model: event.target.value }))}
                  disabled={saving || failClosed}
                  autoComplete="off"
                  style={inputStyle}
                />
              </label>

              <label style={fieldLabelStyle}>
                <span>Daily paid budget (USD)</span>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={draft.daily_paid_budget_usd}
                  onChange={(event) => setDraft((current) => ({ ...current, daily_paid_budget_usd: event.target.value }))}
                  disabled={saving || failClosed}
                  style={inputStyle}
                />
              </label>

              <label style={toggleLabelStyle}>
                <input
                  type="checkbox"
                  checked={draft.anthropic_routing_enabled}
                  onChange={(event) => setDraft((current) => ({ ...current, anthropic_routing_enabled: event.target.checked }))}
                  disabled={saving || failClosed}
                />
                <span>Anthropic routing enabled</span>
              </label>
            </div>

            <p id="ai-gateway-form-validation" style={validationError ? invalidStyle : validStyle}>
              {validationError || "Configuration is ready for backend validation."}
            </p>
            <button
              type="submit"
              disabled={Boolean(validationError) || saving || failClosed}
              aria-describedby="ai-gateway-form-validation"
              style={{
                ...buttonStyle,
                opacity: validationError || saving || failClosed ? 0.55 : 1,
              }}
            >
              {saving ? "Saving…" : "Save gateway policy"}
            </button>
          </form>
        </div>
      ) : null}
    </section>
  );
}

function Metadata({ label, value }) {
  return (
    <div style={metadataItemStyle}>
      <dt style={metadataLabelStyle}>{label}</dt>
      <dd style={metadataValueStyle}>{value ?? "Unavailable"}</dd>
    </div>
  );
}

const formatBudget = (value) => {
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString("en-US", { style: "currency", currency: "USD" })
    : "Unavailable";
};

const sectionLabelStyle = { margin: "0 0 6px", color: "#67e8f9", fontSize: 12, fontWeight: 800, letterSpacing: "0.12em", textTransform: "uppercase" };
const contentStyle = { display: "grid", gap: 18, paddingTop: 16 };
const statusCardStyle = { padding: 18, border: "1px solid #334155", borderRadius: 12, background: "#0f172a" };
const statusHeadingStyle = { display: "flex", alignItems: "flex-start", justifyContent: "space-between", gap: 16 };
const subheadingStyle = { margin: 0, color: "#f8fafc", fontSize: 17 };
const healthyBadgeStyle = { padding: "5px 9px", borderRadius: 999, background: "#14532d", color: "#bbf7d0", fontSize: 12, fontWeight: 800 };
const dangerBadgeStyle = { padding: "5px 9px", borderRadius: 999, background: "#7f1d1d", color: "#fecaca", fontSize: 12, fontWeight: 800 };
const metadataGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(190px, 1fr))", gap: 12, margin: "16px 0 0" };
const metadataItemStyle = { minWidth: 0, padding: 12, borderRadius: 9, background: "#111827" };
const metadataLabelStyle = { color: "#94a3b8", fontSize: 12, fontWeight: 700 };
const metadataValueStyle = { margin: "5px 0 0", color: "#f8fafc", fontSize: 14, overflowWrap: "anywhere" };
const formStyle = { padding: 18, border: "1px solid #334155", borderRadius: 12, background: "#111827" };
const descriptionStyle = { margin: "7px 0 0", color: "#cbd5e1", lineHeight: 1.55, fontSize: 13 };
const fieldGridStyle = { display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))", gap: 16, marginTop: 18 };
const fieldLabelStyle = { display: "grid", gap: 7, color: "#e2e8f0", fontWeight: 700, fontSize: 13 };
const toggleLabelStyle = { display: "flex", alignItems: "center", gap: 9, alignSelf: "end", minHeight: 42, color: "#e2e8f0", fontWeight: 700, fontSize: 13 };
const inputStyle = { width: "100%", boxSizing: "border-box", padding: 11, borderRadius: 8, border: "1px solid #475569", background: "#020617", color: "#f8fafc" };
const validStyle = { margin: "14px 0 0", color: "#86efac", fontSize: 12 };
const invalidStyle = { margin: "14px 0 0", color: "#fca5a5", fontSize: 12 };
const buttonStyle = { marginTop: 12, padding: "10px 15px", border: 0, borderRadius: 8, background: "#0891b2", color: "#fff", fontWeight: 800, cursor: "pointer" };
const mutedStyle = { color: "#94a3b8" };
const errorStyle = { marginTop: 14, padding: 12, borderRadius: 8, background: "#450a0a", color: "#fecaca" };
const successStyle = { marginTop: 14, padding: 12, borderRadius: 8, background: "#052e16", color: "#bbf7d0" };
const warningStyle = { marginTop: 14, padding: 12, borderRadius: 8, background: "#422006", color: "#fde68a" };

export default AiGatewayConfigPanel;
