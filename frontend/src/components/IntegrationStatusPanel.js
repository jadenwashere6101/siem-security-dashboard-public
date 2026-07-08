import React, { useCallback, useEffect, useState } from "react";
import {
  enableHalfOpenIntegrationCircuitBreaker,
  forceOpenIntegrationCircuitBreaker,
  getIntegrationStatus,
  getNotificationReadiness,
  resetIntegrationCircuitBreaker,
  sendNotificationTest,
} from "../services/integrationService";
import { readStoredSessionIdentity } from "../utils/sessionIdentity";
import ExecutionSafetyModelPanel from "./ExecutionSafetyModelPanel";

// spec: SPEC-UI-004 / SPEC-INTEG-005 - integration copy is adapter-specific and guard-controlled.
const INTEGRATION_NOTICE =
  "Operational view of integration readiness. Opening this page does not test, send, or execute integrations.";

const ADAPTER_OPERATIONS = {
  slack: {
    label: "Slack",
    description: "Sends SOAR playbook notifications to a Slack incoming webhook when real mode is enabled.",
    usedBy: "14 core playbooks",
    requiredEnv: ["INTEGRATION_MODE", "SOAR_ENV", "SOAR_REAL_SLACK_ENABLED", "SLACK_WEBHOOK_URL"],
    credentialFlags: [{ key: "webhook_configured", env: "SLACK_WEBHOOK_URL" }],
    enabledEnv: "SOAR_REAL_SLACK_ENABLED",
  },
  teams: {
    label: "Teams",
    description: "Sends SOAR playbook notifications to a Microsoft Teams webhook when configured.",
    usedBy: "Not used by default",
    requiredEnv: ["INTEGRATION_MODE", "SOAR_ENV", "SOAR_REAL_TEAMS_ENABLED", "TEAMS_WEBHOOK_URL"],
    credentialFlags: [{ key: "webhook_configured", env: "TEAMS_WEBHOOK_URL" }],
    enabledEnv: "SOAR_REAL_TEAMS_ENABLED",
  },
  email: {
    label: "Email",
    description: "Sends SOAR playbook notification emails through SMTP when real mode is enabled.",
    usedBy: "1 core playbook",
    requiredEnv: [
      "INTEGRATION_MODE",
      "SOAR_ENV",
      "SOAR_REAL_EMAIL_ENABLED",
      "SMTP_HOST",
      "SMTP_USERNAME",
      "SMTP_FROM_EMAIL",
      "SMTP_TO_EMAIL",
    ],
    credentialFlags: [
      { key: "smtp_host_configured", env: "SMTP_HOST" },
      { key: "smtp_username_configured", env: "SMTP_USERNAME" },
      { key: "smtp_from_configured", env: "SMTP_FROM_EMAIL" },
      { key: "smtp_to_configured", env: "SMTP_TO_EMAIL" },
    ],
    enabledEnv: "SOAR_REAL_EMAIL_ENABLED",
  },
  firewall: {
    label: "Firewall",
    description: "Plans containment actions in simulation only; it does not change firewall rules.",
    usedBy: "7 core playbooks",
    requiredEnv: [],
    dryRunOnly: true,
  },
  webhook: {
    label: "Webhook",
    description: "Posts sanitized SOAR events to a configured HTTPS webhook when real mode is enabled.",
    usedBy: "Not used by default",
    requiredEnv: ["INTEGRATION_MODE", "SOAR_ENV", "SOAR_REAL_WEBHOOK_ENABLED", "WEBHOOK_URL"],
    credentialFlags: [{ key: "webhook_url_configured", env: "WEBHOOK_URL" }],
    enabledEnv: "SOAR_REAL_WEBHOOK_ENABLED",
  },
};

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

function formatOperationalState(value) {
  const normalized = String(value || "").trim().toLowerCase();
  if (normalized === "closed") return "Healthy";
  if (normalized === "open") return "Error";
  if (normalized === "half_open") return "Recovering";
  return formatCircuitScalar(value);
}

function adapterKey(adapter, index) {
  return adapter && adapter.name != null && adapter.name !== ""
    ? String(adapter.name).trim().toLowerCase()
    : `adapter-${index}`;
}

function getOperationMeta(name) {
  return ADAPTER_OPERATIONS[name] || {
    label: name,
    description: "Registered SOAR integration adapter.",
    usedBy: "Not used by default",
    requiredEnv: [],
    credentialFlags: [],
  };
}

function extractEnvNames(value) {
  const text = String(value || "");
  const matches = text.match(/\b[A-Z][A-Z0-9_]{2,}\b/g);
  return Array.from(new Set(matches || []));
}

function missingConfigNames(adapter, name, status) {
  const meta = getOperationMeta(name);
  if (meta.dryRunOnly || adapter?.real_mode_ready === true) {
    return [];
  }

  const names = new Set();
  if (status?.configured_mode && status.configured_mode !== "real") {
    names.add("INTEGRATION_MODE");
  }

  if (adapter?.real_mode_allowed === false) {
    if (meta.enabledEnv) names.add(meta.enabledEnv);
    names.add("SOAR_ENV");
  }

  for (const item of meta.credentialFlags || []) {
    if (adapter?.[item.key] === false) {
      names.add(item.env);
    }
  }

  for (const envName of extractEnvNames(adapter?.real_mode_status)) {
    names.add(envName);
  }

  return Array.from(names).filter((item) => meta.requiredEnv.includes(item));
}

function adapterMode(adapter, name) {
  if (name === "firewall" || getOperationMeta(name).dryRunOnly) {
    return "Simulation";
  }
  if (adapter?.real_mode_ready === true || adapter?.real_client === true || adapter?.mode === "real") {
    return "Real";
  }
  if (adapter?.disabled === true || adapter?.enabled === false) {
    return "Disabled";
  }
  return "Simulation";
}

function externalDeliveryLabel(adapter, name) {
  if (name === "firewall" || getOperationMeta(name).dryRunOnly) {
    return "Disabled";
  }
  return adapter?.real_mode_ready === true || adapter?.real_client === true ? "Enabled" : "Disabled";
}

function healthStatus(adapter, name, status) {
  const circuitState = String(adapter?.circuit_breaker?.state || "").toLowerCase();
  if (status?.error || circuitState === "open" || adapter?.status === "error") {
    return "Error";
  }
  if (adapter?.real_mode_ready === false && missingConfigNames(adapter, name, status).length > 0) {
    return "Warning";
  }
  return "Healthy";
}

function statusBadgeStyle(value) {
  const normalized = String(value || "").toLowerCase();
  if (normalized === "real" || normalized === "enabled" || normalized === "healthy" || normalized === "yes") {
    return { ...badgeBaseStyle, ...badgeGoodStyle };
  }
  if (normalized === "error" || normalized === "disabled" || normalized === "no") {
    return { ...badgeBaseStyle, ...badgeDangerStyle };
  }
  return { ...badgeBaseStyle, ...badgeWarnStyle };
}

function firstAvailable(...values) {
  for (const value of values) {
    if (value !== null && value !== undefined && value !== "") {
      return String(value);
    }
  }
  return "Not available";
}

function normalizeReadinessProviders(raw) {
  if (!raw || !Array.isArray(raw.providers)) {
    return [];
  }
  return raw.providers;
}

function readinessProviderKey(provider, index) {
  return provider && provider.provider != null && provider.provider !== ""
    ? String(provider.provider).trim().toLowerCase()
    : `readiness-${index}`;
}

function testedLabel(provider) {
  const status = String(provider?.last_test_status || "").toLowerCase();
  const tested = String(provider?.tested || "").toLowerCase();
  if (status === "blocked") {
    return "Never Tested (Guard Blocked)";
  }
  if (tested === "passed") return "Passed";
  if (tested === "failed") return "Failed";
  return "Never Tested";
}

function formatLastTest(value) {
  if (!value) {
    return "Never";
  }
  return String(value);
}

function NotificationReadinessPanel({ readiness, loading, error, canTest, onRefresh }) {
  const providers = normalizeReadinessProviders(readiness);
  const [busyProvider, setBusyProvider] = useState(null);
  const [testError, setTestError] = useState("");
  const [testMessage, setTestMessage] = useState("");

  const runTest = async (provider) => {
    const key = String(provider?.provider || "").trim().toLowerCase();
    const label = provider?.label || key;
    if (!key || provider?.configured !== true) {
      return;
    }
    const confirmed = window.confirm(
      `Send one manual readiness test notification to ${label}?`
    );
    if (!confirmed) {
      return;
    }
    setBusyProvider(key);
    setTestError("");
    setTestMessage("");
    try {
      const result = await sendNotificationTest(key);
      setTestMessage(result?.message || "Notification test completed.");
      if (typeof onRefresh === "function") {
        await onRefresh();
      }
    } catch (err) {
      setTestError(err.message || "Notification test failed.");
    } finally {
      setBusyProvider(null);
    }
  };

  return (
    <div style={readinessPanelStyle}>
      <div style={readinessHeaderStyle}>
        <div>
          <h3 style={subsectionTitleStyle}>Notification readiness</h3>
        </div>
        <button type="button" style={refreshReadinessButtonStyle} onClick={onRefresh}>
          Refresh
        </button>
      </div>
      {error ? <div style={readinessErrorStyle}>Error: {error}</div> : null}
      {testError ? <div style={readinessErrorStyle}>Error: {testError}</div> : null}
      {testMessage ? <div style={readinessMessageStyle}>{testMessage}</div> : null}
      {loading ? <p style={emptyTextStyle}>Loading notification readiness...</p> : null}
      {!loading && !error && providers.length === 0 ? (
        <p style={emptyTextStyle}>No notification readiness providers returned.</p>
      ) : null}
      {!loading && !error && providers.length > 0 ? (
        <ul style={readinessListStyle}>
          {providers.map((provider, index) => {
            const key = readinessProviderKey(provider, index);
            const missing = Array.isArray(provider?.missing_configuration)
              ? provider.missing_configuration
              : [];
            const configured = provider?.configured === true;
            const ready = provider?.ready === true;
            const busy = busyProvider === key;
            return (
              <li key={key} style={readinessCardStyle}>
                <div style={adapterHeaderRowStyle}>
                  <span style={adapterNameStyle}>{provider?.label || key}</span>
                  <div style={badgeRowStyle}>
                    <span style={statusBadgeStyle(configured ? "yes" : "no")}>
                      Configured {configured ? "Yes" : "No"}
                    </span>
                    <span style={statusBadgeStyle(provider?.tested)}>
                      {testedLabel(provider)}
                    </span>
                    <span style={statusBadgeStyle(ready ? "yes" : "no")}>
                      Ready {ready ? "Yes" : "No"}
                    </span>
                  </div>
                </div>
                <div style={readinessGridStyle}>
                  <div style={operationalFieldStyle}>
                    <span style={summaryLabelStyle}>Configured</span>
                    <span style={metaValueStyle}>{configured ? "Yes" : "No"}</span>
                  </div>
                  <div style={operationalFieldStyle}>
                    <span style={summaryLabelStyle}>Tested</span>
                    <span style={metaValueStyle}>{testedLabel(provider)}</span>
                  </div>
                  <div style={operationalFieldStyle}>
                    <span style={summaryLabelStyle}>Ready</span>
                    <span style={metaValueStyle}>{ready ? "Yes" : "No"}</span>
                  </div>
                  <div style={operationalFieldStyle}>
                    <span style={summaryLabelStyle}>Last Test</span>
                    <span style={metaValueStyle}>{formatLastTest(provider?.last_test_at)}</span>
                  </div>
                </div>
                {provider?.last_test_status === "blocked" && provider?.last_test_message ? (
                  <div style={guardBlockedStyle}>{provider.last_test_message}</div>
                ) : null}
                <div style={readinessFooterStyle}>
                  <div style={missingConfigInlineStyle}>
                    <span style={actionsLabelStyle}>Missing Configuration</span>
                    {missing.length === 0 ? (
                      <span style={metaMutedStyle}>None</span>
                    ) : (
                      <div style={actionTagsStyle}>
                        {missing.map((envName) => (
                          <span key={envName} style={missingTagStyle}>
                            {envName}
                          </span>
                        ))}
                      </div>
                    )}
                  </div>
                  <button
                    type="button"
                    style={configured ? testButtonStyle : disabledTestButtonStyle}
                    disabled={!canTest || !configured || busy}
                    title={!configured ? "Provider is not configured." : undefined}
                    onClick={() => runTest(provider)}
                  >
                    {busy ? "Sending..." : "Test"}
                  </button>
                </div>
                {!configured ? (
                  <p style={notConfiguredHelpStyle}>Not Configured</p>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </div>
  );
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
    { label: "State", value: formatOperationalState(circuit.state) },
    { label: "Raw state", value: formatCircuitScalar(circuit.state) },
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
        <span style={circuitBreakerTitleStyle}>Reliability internals</span>
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
            <strong>Advanced simulation controls (super admin).</strong> These requests only
            update in-memory simulation state on the server. They do not run adapter code, open real
            connections, or execute a recovery probe. &quot;Simulate Recovery&quot; only marks
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
              {busyAction === "reset" ? "Working…" : "Restore Healthy State"}
            </button>
            <button
              type="button"
              style={circuitControlButtonDangerStyle}
              disabled={busyAction != null}
              onClick={() =>
                runControl("force_open", (r) => forceOpenIntegrationCircuitBreaker(name, r))
              }
            >
              {busyAction === "force_open" ? "Working…" : "Simulate Failure"}
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
              {busyAction === "half_open" ? "Working…" : "Simulate Recovery"}
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
  const [readiness, setReadiness] = useState(null);
  const [loading, setLoading] = useState(true);
  const [readinessLoading, setReadinessLoading] = useState(true);
  const [error, setError] = useState("");
  const [readinessError, setReadinessError] = useState("");
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

  const loadReadiness = useCallback(async () => {
    try {
      setReadinessLoading(true);
      setReadinessError("");
      const data = await getNotificationReadiness();
      setReadiness(data && typeof data === "object" ? data : null);
    } catch (err) {
      setReadinessError(err.message || "Unable to load notification readiness.");
      setReadiness(null);
    } finally {
      setReadinessLoading(false);
    }
  }, []);

  useEffect(() => {
    loadStatus();
    loadReadiness();
  }, [loadStatus, loadReadiness]);

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
            Operational readiness for SOAR notification and response integrations.
            {isSuperAdmin
              ? " Super admins can adjust advanced simulation state inside each adapter."
              : " Analysts have read-only access to this panel."}
          </p>
        </div>
      </div>

      <div style={panelContentStyle}>
        <div style={simulationNoticeStyle} role="note">
          {INTEGRATION_NOTICE}
        </div>
        <ExecutionSafetyModelPanel compact />

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
          <NotificationReadinessPanel
            readiness={readiness}
            loading={readinessLoading}
            error={readinessError}
            canTest={isSuperAdmin}
            onRefresh={loadReadiness}
          />
        ) : null}

        {showModeSummary ? (
          <div style={modeSummaryStyle}>
            <h3 style={subsectionTitleStyle}>Operational summary</h3>
            <div style={summaryGridStyle}>
              <div style={summaryFieldStyle}>
                <span style={summaryLabelStyle}>Overall mode</span>
                <span style={summaryValueStyle}>
                  {status.real_mode_enabled === true ? "Real" : "Simulation"}
                </span>
              </div>
              <div style={summaryFieldStyle}>
                <span style={summaryLabelStyle}>Simulation safe</span>
                <span style={summaryValueStyle}>{formatFlag(status.simulated)}</span>
              </div>
              <div style={summaryFieldStyle}>
                <span style={summaryLabelStyle}>External delivery</span>
                <span style={summaryValueStyle}>
                  {status.real_mode_enabled === true ? "Enabled" : "Disabled"}
                </span>
              </div>
              <div style={summaryFieldStyle}>
                <span style={summaryLabelStyle}>Readiness</span>
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
            <h3 style={subsectionTitleStyle}>Integrations</h3>
            <ul style={adapterUlStyle}>
              {adapters.map((adapter, index) => {
                const key = adapterKey(adapter, index);
                const meta = getOperationMeta(key);
                const actions = Array.isArray(adapter?.supported_actions)
                  ? adapter.supported_actions
                  : [];
                const mode = adapterMode(adapter, key);
                const health = healthStatus(adapter, key, status);
                const externalDelivery = externalDeliveryLabel(adapter, key);
                const ready = adapter?.real_mode_ready === true;
                const missing = missingConfigNames(adapter, key, status);
                return (
                  <li key={key} style={adapterCardStyle}>
                    <div style={adapterHeaderRowStyle}>
                      <div>
                        <span style={adapterNameStyle}>{meta.label}</span>
                        <p style={adapterDescriptionStyle}>{meta.description}</p>
                      </div>
                      <div style={badgeRowStyle}>
                        <span style={statusBadgeStyle(mode)}>{mode}</span>
                        <span style={statusBadgeStyle(health)}>{health}</span>
                      </div>
                    </div>

                    <div style={operationalGridStyle}>
                      <div style={operationalFieldStyle}>
                        <span style={summaryLabelStyle}>Mode</span>
                        <span style={metaValueStyle}>{mode}</span>
                      </div>
                      <div style={operationalFieldStyle}>
                        <span style={summaryLabelStyle}>Health</span>
                        <span style={metaValueStyle}>{health}</span>
                      </div>
                      <div style={operationalFieldStyle}>
                        <span style={summaryLabelStyle}>Used by</span>
                        <span style={metaValueStyle}>{meta.usedBy}</span>
                      </div>
                      <div style={operationalFieldStyle}>
                        <span style={summaryLabelStyle}>External delivery</span>
                        <span style={metaValueStyle}>{externalDelivery}</span>
                      </div>
                      <div style={operationalFieldStyle}>
                        <span style={summaryLabelStyle}>Ready for real mode</span>
                        <span style={metaValueStyle}>{ready ? "Yes" : "No"}</span>
                      </div>
                      <div style={operationalFieldStyle}>
                        <span style={summaryLabelStyle}>Last delivery</span>
                        <span style={metaValueStyle}>
                          {firstAvailable(adapter?.last_successful_delivery, adapter?.last_delivery)}
                        </span>
                      </div>
                      <div style={operationalFieldStyle}>
                        <span style={summaryLabelStyle}>Last tested</span>
                        <span style={metaValueStyle}>{firstAvailable(adapter?.last_tested)}</span>
                      </div>
                    </div>

                    {missing.length > 0 ? (
                      <div style={missingConfigStyle}>
                        <span style={actionsLabelStyle}>Missing config</span>
                        <div style={actionTagsStyle}>
                          {missing.map((envName) => (
                            <span key={envName} style={missingTagStyle}>
                              {envName}
                            </span>
                          ))}
                        </div>
                      </div>
                    ) : null}

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
                    <details style={advancedDetailsStyle}>
                      <summary style={advancedSummaryStyle}>Advanced</summary>
                      <div style={advancedContentStyle}>
                        <div style={advancedMetaStyle}>
                          <div style={operationalFieldStyle}>
                            <span style={summaryLabelStyle}>Raw adapter mode</span>
                            <span style={metaValueStyle}>{String(adapter?.mode ?? "—")}</span>
                          </div>
                          <div style={operationalFieldStyle}>
                            <span style={summaryLabelStyle}>Simulation safe</span>
                            <span style={metaValueStyle}>{formatFlag(adapter?.simulated)}</span>
                          </div>
                          <div style={operationalFieldStyle}>
                            <span style={summaryLabelStyle}>Real client</span>
                            <span style={metaValueStyle}>{formatFlag(adapter?.real_client)}</span>
                          </div>
                        </div>
                        <CircuitBreakerPanel
                          circuit={adapter?.circuit_breaker}
                          adapterName={key}
                          canManageCircuit={isSuperAdmin}
                          onCircuitUpdated={loadStatus}
                        />
                      </div>
                    </details>
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

const readinessPanelStyle = {
  marginBottom: "22px",
  padding: "14px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
};

const readinessHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  gap: "12px",
  marginBottom: "12px",
  flexWrap: "wrap",
};

const refreshReadinessButtonStyle = {
  minHeight: "34px",
  padding: "7px 12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#e6edf3",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const readinessListStyle = {
  listStyle: "none",
  margin: 0,
  padding: 0,
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
  gap: "12px",
};

const readinessCardStyle = {
  border: "1px solid rgba(48, 54, 61, 0.95)",
  borderRadius: "8px",
  padding: "12px",
  backgroundColor: "rgba(1, 4, 9, 0.38)",
};

const readinessGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(2, minmax(0, 1fr))",
  gap: "10px",
  margin: "12px 0",
};

const readinessFooterStyle = {
  display: "flex",
  alignItems: "flex-end",
  justifyContent: "space-between",
  gap: "12px",
  flexWrap: "wrap",
};

const missingConfigInlineStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
  minWidth: "180px",
  flex: "1 1 180px",
};

const testButtonStyle = {
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

const disabledTestButtonStyle = {
  ...testButtonStyle,
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#8b949e",
  cursor: "not-allowed",
};

const notConfiguredHelpStyle = {
  margin: "10px 0 0",
  color: "#e6c35c",
  fontSize: "12px",
  fontWeight: "700",
};

const guardBlockedStyle = {
  margin: "0 0 12px",
  padding: "8px 10px",
  borderRadius: "8px",
  border: "1px solid rgba(210, 153, 34, 0.32)",
  backgroundColor: "rgba(210, 153, 34, 0.08)",
  color: "#e6c35c",
  fontSize: "12px",
  fontWeight: "600",
  lineHeight: 1.45,
};

const readinessErrorStyle = {
  marginBottom: "10px",
  padding: "8px 10px",
  borderRadius: "8px",
  fontSize: "12px",
  fontWeight: "600",
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.28)",
  color: "#fca5a5",
};

const readinessMessageStyle = {
  marginBottom: "10px",
  padding: "8px 10px",
  borderRadius: "8px",
  fontSize: "12px",
  fontWeight: "600",
  backgroundColor: "rgba(46, 160, 67, 0.12)",
  border: "1px solid rgba(63, 185, 80, 0.28)",
  color: "#8ddb8c",
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

const badgeBaseStyle = {
  display: "inline-flex",
  alignItems: "center",
  minHeight: "24px",
  padding: "4px 10px",
  borderRadius: "999px",
  fontSize: "11px",
  fontWeight: "700",
  letterSpacing: "0.04em",
  textTransform: "uppercase",
};

const badgeGoodStyle = {
  backgroundColor: "rgba(46, 160, 67, 0.14)",
  border: "1px solid rgba(63, 185, 80, 0.34)",
  color: "#8ddb8c",
};

const badgeWarnStyle = {
  backgroundColor: "rgba(210, 153, 34, 0.12)",
  border: "1px solid rgba(210, 153, 34, 0.35)",
  color: "#e6c35c",
};

const badgeDangerStyle = {
  backgroundColor: "rgba(239, 68, 68, 0.12)",
  border: "1px solid rgba(239, 68, 68, 0.34)",
  color: "#fca5a5",
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
};

const adapterDescriptionStyle = {
  margin: "6px 0 0 0",
  color: "#8b949e",
  fontSize: "13px",
  lineHeight: 1.45,
  maxWidth: "680px",
};

const badgeRowStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "flex-end",
  gap: "8px",
  flexWrap: "wrap",
};

const metaMutedStyle = {
  color: "#8b949e",
};

const metaValueStyle = {
  color: "#e6edf3",
  fontWeight: "600",
};

const operationalGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
  gap: "10px",
  margin: "14px 0",
};

const operationalFieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "5px",
  minHeight: "54px",
  padding: "10px 11px",
  borderRadius: "8px",
  border: "1px solid rgba(48, 54, 61, 0.88)",
  backgroundColor: "rgba(1, 4, 9, 0.38)",
};

const missingConfigStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
  marginBottom: "14px",
  padding: "10px 11px",
  borderRadius: "8px",
  border: "1px solid rgba(210, 153, 34, 0.32)",
  backgroundColor: "rgba(210, 153, 34, 0.08)",
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

const missingTagStyle = {
  ...actionTagStyle,
  border: "1px solid rgba(210, 153, 34, 0.4)",
  backgroundColor: "rgba(210, 153, 34, 0.10)",
  color: "#e6c35c",
  fontFamily: "'Courier New', monospace",
};

const advancedDetailsStyle = {
  marginTop: "14px",
  borderTop: "1px solid rgba(48, 54, 61, 0.75)",
  paddingTop: "12px",
};

const advancedSummaryStyle = {
  color: "#93c5fd",
  fontSize: "13px",
  fontWeight: "700",
  cursor: "pointer",
  userSelect: "none",
};

const advancedContentStyle = {
  marginTop: "12px",
};

const advancedMetaStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(150px, 1fr))",
  gap: "10px",
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
