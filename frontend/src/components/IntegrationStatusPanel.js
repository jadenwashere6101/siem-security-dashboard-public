import React, { useCallback, useEffect, useState } from "react";
import {
  enableHalfOpenIntegrationCircuitBreaker,
  forceOpenIntegrationCircuitBreaker,
  getIntegrationStatus,
  resetIntegrationCircuitBreaker,
} from "../services/integrationService";
import { readStoredSessionIdentity } from "../utils/sessionIdentity";

const SIMULATION_NOTICE =
  "Simulation only: all integration adapters run in simulation mode. No real outbound notifications, webhooks, or firewall changes are active.";

function normalizeAdapters(raw) {
  if (!Array.isArray(raw)) {
    return [];
  }
  return raw;
}

function formatFlag(value) {
  if (value === true) return "Yes";
  if (value === false) return "No";
  return "—";
}

function formatCircuitScalar(value) {
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "boolean") {
    return formatFlag(value);
  }
  return String(value);
}

function CircuitBreakerPanel({ circuit, adapterName, canManageCircuit = false, onCircuitUpdated }) {
  const [reason, setReason] = useState("");
  const [overrideCooldown, setOverrideCooldown] = useState(false);
  const [busyAction, setBusyAction] = useState(null);
  const [controlError, setControlError] = useState("");

  useEffect(() => {
    setReason("");
    setOverrideCooldown(false);
    setControlError("");
    setBusyAction(null);
  }, [adapterName]);

  if (!circuit || typeof circuit !== "object") {
    return null;
  }

  const rows = [
    { label: "State", value: formatCircuitScalar(circuit.state) },
    { label: "Consecutive failures", value: formatCircuitScalar(circuit.consecutive_failures) },
    { label: "Failure threshold", value: formatCircuitScalar(circuit.failure_threshold) },
    { label: "Cooldown (seconds)", value: formatCircuitScalar(circuit.cooldown_seconds) },
    { label: "Cooldown until", value: formatCircuitScalar(circuit.cooldown_until) },
    { label: "Last failure reason", value: formatCircuitScalar(circuit.last_failure_reason) },
    {
      label: "Last failure classification",
      value: formatCircuitScalar(circuit.last_failure_classification),
    },
    { label: "Timeout (seconds)", value: formatCircuitScalar(circuit.timeout_seconds) },
    { label: "Retry eligible", value: formatCircuitScalar(circuit.retry_eligible) },
    { label: "Half-open probe allowed", value: formatCircuitScalar(circuit.half_open_probe_available) },
    { label: "Last manual action", value: formatCircuitScalar(circuit.last_manual_action) },
    { label: "Last manual by", value: formatCircuitScalar(circuit.last_manual_action_by) },
    { label: "Last manual at", value: formatCircuitScalar(circuit.last_manual_action_at) },
    { label: "Last manual reason", value: formatCircuitScalar(circuit.last_manual_reason) },
    { label: "State persisted", value: formatCircuitScalar(circuit.state_persisted) },
  ];

  const runControl = async (action, fn) => {
    const trimmed = reason.trim();
    if (!trimmed) {
      setControlError("Enter a non-empty reason before running a control.");
      return;
    }
    setBusyAction(action);
    setControlError("");
    try {
      await fn(trimmed);
      setReason("");
      setOverrideCooldown(false);
      if (typeof onCircuitUpdated === "function") {
        await onCircuitUpdated();
      }
    } catch (err) {
      setControlError(err.message || "Control request failed.");
    } finally {
      setBusyAction(null);
    }
  };

  const name = String(adapterName || "").trim();
  const showControls = Boolean(canManageCircuit && name && typeof onCircuitUpdated === "function");

  return (
    <div style={circuitBreakerBlockStyle}>
      <div style={circuitBreakerHeadingRowStyle}>
        <span style={circuitBreakerTitleStyle}>Circuit breaker</span>
        <span style={circuitSimulationBadgeStyle}>Simulation</span>
      </div>
      <p style={circuitBreakerDisclaimerStyle}>
        Circuit breaker state is simulation-only and stored in memory on the server. It is not
        shared across processes and resets when the backend restarts.
      </p>
      <dl style={circuitDlStyle}>
        {rows.map(({ label, value }) => (
          <div key={label} style={circuitDlRowStyle}>
            <dt style={circuitDtStyle}>{label}</dt>
            <dd style={circuitDdStyle}>{value}</dd>
          </div>
        ))}
      </dl>
      {showControls ? (
        <div style={circuitControlsSectionStyle}>
          <p style={circuitControlsIntroStyle}>
            <strong>Simulation circuit breaker controls (super admin).</strong> These requests only
            update in-memory simulation state on the server. They do not run adapter code, open real
            connections, or execute a half-open probe. &quot;Enable half-open probe&quot; only marks
            that the next simulated adapter call may use one bounded probe when playbook execution
            reaches it.
          </p>
          <label htmlFor={`circuit-reason-${name}`} style={circuitLabelStyle}>
            Reason (required)
          </label>
          <textarea
            id={`circuit-reason-${name}`}
            value={reason}
            onChange={(e) => {
              setReason(e.target.value);
              if (controlError) setControlError("");
            }}
            rows={3}
            style={circuitReasonTextareaStyle}
            placeholder="Describe why you are changing simulation breaker state."
            disabled={busyAction != null}
          />
          <label style={circuitCheckboxRowStyle}>
            <input
              type="checkbox"
              checked={overrideCooldown}
              onChange={(e) => setOverrideCooldown(e.target.checked)}
              disabled={busyAction != null}
            />
            <span>Override cooldown when enabling half-open (super-admin bypass; use sparingly)</span>
          </label>
          {controlError ? <div style={circuitControlErrorStyle}>{controlError}</div> : null}
          <div style={circuitControlButtonsRowStyle}>
            <button
              type="button"
              style={circuitControlButtonPrimaryStyle}
              disabled={busyAction != null}
              onClick={() => runControl("reset", (r) => resetIntegrationCircuitBreaker(name, r))}
            >
              {busyAction === "reset" ? "Working…" : "Reset to closed"}
            </button>
            <button
              type="button"
              style={circuitControlButtonDangerStyle}
              disabled={busyAction != null}
              onClick={() =>
                runControl("force_open", (r) => forceOpenIntegrationCircuitBreaker(name, r))
              }
            >
              {busyAction === "force_open" ? "Working…" : "Force open"}
            </button>
            <button
              type="button"
              style={circuitControlButtonSecondaryStyle}
              disabled={busyAction != null}
              onClick={() =>
                runControl("half_open", (r) =>
                  enableHalfOpenIntegrationCircuitBreaker(name, r, overrideCooldown)
                )
              }
            >
              {busyAction === "half_open" ? "Working…" : "Enable half-open probe"}
            </button>
          </div>
        </div>
      ) : null}
    </div>
  );
}

function IntegrationStatusPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
}) {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [sessionRole, setSessionRole] = useState(
    () => readStoredSessionIdentity()?.role ?? null
  );
  const isSuperAdmin = sessionRole === "super_admin";

  const loadStatus = useCallback(async () => {
    try {
      setLoading(true);
      setError("");
      const identity = readStoredSessionIdentity();
      setSessionRole(identity?.role ?? null);
      const data = await getIntegrationStatus();
      setStatus(data && typeof data === "object" ? data : null);
    } catch (err) {
      setError(err.message || "Unable to load integration status.");
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
  }, [loadStatus]);

  const adapters = normalizeAdapters(status?.adapters);
  const showModeSummary = Boolean(status) && !loading && !error;
  const showEmptyAdapters = showModeSummary && adapters.length === 0;
  const showAdapterRows = showModeSummary && adapters.length > 0;

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>SOAR</p>
          <h2 style={cardTitleStyle}>Integration adapter status</h2>
          <p style={cardSubtitleStyle}>
            View of registered simulation adapters from the backend registry.
            {isSuperAdmin
              ? " Super admins can adjust simulation circuit breakers per adapter below."
              : " Analysts have read-only access to this panel."}
          </p>
        </div>
      </div>

      <div style={panelContentStyle}>
        <div style={simulationNoticeStyle} role="note">
          {SIMULATION_NOTICE}
        </div>

        {error ? (
          <div style={errorStateStyle}>
            <span>Error: {error}</span>
            <button type="button" onClick={() => loadStatus()} style={retryButtonStyle}>
              Retry
            </button>
          </div>
        ) : null}

        {loading ? (
          <p style={emptyTextStyle}>Loading integration status...</p>
        ) : null}

        {showModeSummary ? (
          <div style={modeSummaryStyle}>
            <h3 style={subsectionTitleStyle}>Mode summary</h3>
            <div style={summaryGridStyle}>
              <div style={summaryFieldStyle}>
                <span style={summaryLabelStyle}>Integration mode</span>
                <span style={summaryValueStyle}>{String(status.mode ?? "—")}</span>
              </div>
              <div style={summaryFieldStyle}>
                <span style={summaryLabelStyle}>Simulated</span>
                <span style={summaryValueStyle}>{formatFlag(status.simulated)}</span>
              </div>
              <div style={summaryFieldStyle}>
                <span style={summaryLabelStyle}>Real mode</span>
                <span style={summaryValueStyle}>
                  {status.real_mode_enabled === true ? "Enabled" : "Real mode disabled"}
                </span>
              </div>
              <div style={summaryFieldStyle}>
                <span style={summaryLabelStyle}>Real mode status</span>
                <span style={{ ...summaryValueStyle, ...monoValueStyle }}>
                  {String(status.real_mode_status ?? "—")}
                </span>
              </div>
            </div>
          </div>
        ) : null}

        {showEmptyAdapters ? (
          <p style={emptyTextStyle}>No integration adapters registered.</p>
        ) : null}

        {showAdapterRows ? (
          <div style={adapterListStyle}>
            <h3 style={subsectionTitleStyle}>Adapters</h3>
            <ul style={adapterUlStyle}>
              {adapters.map((adapter, index) => {
                const key =
                  adapter && adapter.name != null && adapter.name !== ""
                    ? String(adapter.name)
                    : `adapter-${index}`;
                const actions = Array.isArray(adapter?.supported_actions)
                  ? adapter.supported_actions
                  : [];
                return (
                  <li key={key} style={adapterCardStyle}>
                    <div style={adapterHeaderRowStyle}>
                      <span style={adapterNameStyle}>{key}</span>
                      <span style={modeBadgeStyle}>{String(adapter?.mode ?? "—")}</span>
                    </div>
                    <div style={adapterMetaRowStyle}>
                      <span style={metaMutedStyle}>Simulated:</span>{" "}
                      <span style={metaValueStyle}>{formatFlag(adapter?.simulated)}</span>
                    </div>
                    <CircuitBreakerPanel
                      circuit={adapter?.circuit_breaker}
                      adapterName={key}
                      canManageCircuit={isSuperAdmin}
                      onCircuitUpdated={loadStatus}
                    />
                    <div style={actionsBlockStyle}>
                      <span style={actionsLabelStyle}>Supported actions</span>
                      {actions.length === 0 ? (
                        <span style={metaMutedStyle}>None listed</span>
                      ) : (
                        <div style={actionTagsStyle}>
                          {actions.map((action) => (
                            <span key={String(action)} style={actionTagStyle}>
                              {String(action)}
                            </span>
                          ))}
                        </div>
                      )}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
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
  padding: "24px 20px 22px",
};

const simulationNoticeStyle = {
  marginBottom: "18px",
  padding: "12px 14px",
  borderRadius: "10px",
  border: "1px solid rgba(210, 153, 34, 0.35)",
  backgroundColor: "rgba(210, 153, 34, 0.10)",
  color: "#e6c35c",
  fontSize: "13px",
  fontWeight: "600",
  lineHeight: 1.45,
};

const emptyTextStyle = {
  margin: "0 0 12px 0",
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

const retryButtonStyle = {
  marginLeft: "12px",
  minHeight: "30px",
  padding: "6px 10px",
  borderRadius: "8px",
  border: "1px solid rgba(239, 68, 68, 0.38)",
  backgroundColor: "rgba(239, 68, 68, 0.10)",
  color: "#fca5a5",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const modeSummaryStyle = {
  marginBottom: "20px",
};

const subsectionTitleStyle = {
  margin: "0 0 12px 0",
  fontSize: "15px",
  fontWeight: "700",
  color: "#e6edf3",
};

const summaryGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: "12px",
};

const summaryFieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "6px",
  padding: "12px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
};

const summaryLabelStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.08em",
  textTransform: "uppercase",
};

const summaryValueStyle = {
  color: "#e6edf3",
  fontSize: "14px",
  fontWeight: "600",
};

const monoValueStyle = {
  fontFamily: "'Courier New', monospace",
  fontSize: "12px",
  color: "#d29922",
  fontWeight: "600",
};

const adapterListStyle = {
  marginTop: "8px",
};

const adapterUlStyle = {
  listStyle: "none",
  margin: 0,
  padding: 0,
  display: "flex",
  flexDirection: "column",
  gap: "12px",
};

const adapterCardStyle = {
  border: "1px solid #30363d",
  borderRadius: "10px",
  padding: "14px 16px",
  backgroundColor: "#0d1117",
};

const adapterHeaderRowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  marginBottom: "8px",
  flexWrap: "wrap",
};

const adapterNameStyle = {
  fontSize: "16px",
  fontWeight: "700",
  color: "#e6edf3",
  textTransform: "lowercase",
};

const modeBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  padding: "4px 10px",
  borderRadius: "999px",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  backgroundColor: "rgba(31, 111, 235, 0.14)",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  color: "#93c5fd",
};

const adapterMetaRowStyle = {
  fontSize: "13px",
  marginBottom: "10px",
};

const metaMutedStyle = {
  color: "#8b949e",
};

const metaValueStyle = {
  color: "#e6edf3",
  fontWeight: "600",
};

const actionsBlockStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const actionsLabelStyle = {
  color: "#8b949e",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const actionTagsStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "8px",
};

const actionTagStyle = {
  display: "inline-block",
  padding: "4px 10px",
  borderRadius: "8px",
  fontSize: "12px",
  fontWeight: "600",
  backgroundColor: "#161b22",
  border: "1px solid #30363d",
  color: "#c9d1d9",
};

const circuitBreakerBlockStyle = {
  marginTop: "12px",
  marginBottom: "12px",
  padding: "12px",
  borderRadius: "8px",
  border: "1px solid rgba(139, 148, 158, 0.35)",
  backgroundColor: "rgba(22, 27, 34, 0.65)",
};

const circuitBreakerHeadingRowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "10px",
  flexWrap: "wrap",
  marginBottom: "8px",
};

const circuitBreakerTitleStyle = {
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "#c9d1d9",
};

const circuitSimulationBadgeStyle = {
  display: "inline-flex",
  alignItems: "center",
  padding: "2px 8px",
  borderRadius: "999px",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
  backgroundColor: "rgba(210, 153, 34, 0.12)",
  border: "1px solid rgba(210, 153, 34, 0.35)",
  color: "#e6c35c",
};

const circuitBreakerDisclaimerStyle = {
  margin: "0 0 12px 0",
  fontSize: "12px",
  lineHeight: 1.5,
  color: "#8b949e",
  fontWeight: "500",
};

const circuitDlStyle = {
  margin: 0,
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))",
  gap: "10px 16px",
};

const circuitDlRowStyle = {
  margin: 0,
};

const circuitDtStyle = {
  margin: "0 0 4px 0",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "#8b949e",
};

const circuitDdStyle = {
  margin: 0,
  fontSize: "13px",
  fontWeight: "600",
  color: "#e6edf3",
  fontFamily: "'Courier New', monospace",
  wordBreak: "break-word",
};

const circuitControlsSectionStyle = {
  marginTop: "14px",
  paddingTop: "14px",
  borderTop: "1px solid rgba(139, 148, 158, 0.25)",
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const circuitControlsIntroStyle = {
  margin: 0,
  fontSize: "12px",
  lineHeight: 1.55,
  color: "#c9d1d9",
  fontWeight: "500",
};

const circuitLabelStyle = {
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
  color: "#8b949e",
};

const circuitReasonTextareaStyle = {
  width: "100%",
  boxSizing: "border-box",
  resize: "vertical",
  minHeight: "72px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#010409",
  color: "#e6edf3",
  fontSize: "13px",
  fontFamily: "inherit",
};

const circuitCheckboxRowStyle = {
  display: "flex",
  alignItems: "flex-start",
  gap: "10px",
  fontSize: "12px",
  color: "#8b949e",
  lineHeight: 1.45,
};

const circuitControlErrorStyle = {
  padding: "8px 10px",
  borderRadius: "8px",
  fontSize: "12px",
  fontWeight: "600",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
  color: "#fca5a5",
};

const circuitControlButtonsRowStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "8px",
};

const circuitControlButtonPrimaryStyle = {
  minHeight: "36px",
  padding: "8px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.45)",
  backgroundColor: "rgba(31, 111, 235, 0.18)",
  color: "#dbeafe",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const circuitControlButtonSecondaryStyle = {
  minHeight: "36px",
  padding: "8px 14px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#e6edf3",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const circuitControlButtonDangerStyle = {
  minHeight: "36px",
  padding: "8px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(239, 68, 68, 0.45)",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  color: "#fecaca",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

export default IntegrationStatusPanel;
