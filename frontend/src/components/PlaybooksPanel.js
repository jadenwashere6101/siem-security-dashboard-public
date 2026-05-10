import React, { useCallback, useEffect, useState } from "react";
import {
  getPlaybook,
  getPlaybookExecution,
  listPlaybookExecutions,
  listPlaybooks,
} from "../services/playbookService";
import { formatAdminTimestamp } from "../utils/adminPanelDisplay";

const PAGE_LIMIT = 50;
const EXEC_STATUSES = ["pending", "running", "success", "failed", "abandoned"];
const ENABLED_OPTIONS = [
  { value: "all", label: "All definitions" },
  { value: "enabled", label: "Enabled only" },
  { value: "disabled", label: "Disabled only" },
];

function summarizeTrigger(triggerConfig) {
  if (!triggerConfig || typeof triggerConfig !== "object") {
    return "—";
  }
  const keys = Object.keys(triggerConfig);
  if (keys.length === 0) {
    return "Any alert";
  }
  const preview = keys.slice(0, 4).join(", ");
  return keys.length > 4 ? `${preview}…` : preview;
}

function stepCount(steps) {
  return Array.isArray(steps) ? steps.length : 0;
}

function PlaybooksPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterWrapperStyle,
  filterLabelStyle,
  selectStyle,
}) {
  const [activePanel, setActivePanel] = useState("definitions");

  const [definitions, setDefinitions] = useState([]);
  const [defLoading, setDefLoading] = useState(true);
  const [defRefreshing, setDefRefreshing] = useState(false);
  const [defError, setDefError] = useState("");
  const [enabledOption, setEnabledOption] = useState("all");

  const [executions, setExecutions] = useState([]);
  const [execLoading, setExecLoading] = useState(true);
  const [execRefreshing, setExecRefreshing] = useState(false);
  const [execError, setExecError] = useState("");
  const [execStatus, setExecStatus] = useState("");
  const [execPlaybookIdDraft, setExecPlaybookIdDraft] = useState("");
  const [execPlaybookIdApplied, setExecPlaybookIdApplied] = useState("");

  const [detailKind, setDetailKind] = useState(null);
  const [detailRecord, setDetailRecord] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  const loadDefinitions = useCallback(
    async ({ quiet = false } = {}) => {
      try {
        if (quiet) {
          setDefRefreshing(true);
        } else {
          setDefLoading(true);
        }
        setDefError("");
        const enabledParam =
          enabledOption === "enabled" ? true : enabledOption === "disabled" ? false : undefined;
        const data = await listPlaybooks({
          enabled: enabledParam,
          limit: PAGE_LIMIT,
        });
        setDefinitions(Array.isArray(data?.items) ? data.items : []);
      } catch (err) {
        setDefError(err.message || "Unable to load playbook definitions.");
        if (!quiet) {
          setDefinitions([]);
        }
      } finally {
        setDefLoading(false);
        setDefRefreshing(false);
      }
    },
    [enabledOption]
  );

  const loadExecutions = useCallback(
    async ({ quiet = false } = {}) => {
      try {
        if (quiet) {
          setExecRefreshing(true);
        } else {
          setExecLoading(true);
        }
        setExecError("");
        const data = await listPlaybookExecutions({
          playbookId: execPlaybookIdApplied.trim() || undefined,
          status: execStatus || undefined,
          limit: PAGE_LIMIT,
        });
        setExecutions(Array.isArray(data?.items) ? data.items : []);
      } catch (err) {
        setExecError(err.message || "Unable to load playbook executions.");
        if (!quiet) {
          setExecutions([]);
        }
      } finally {
        setExecLoading(false);
        setExecRefreshing(false);
      }
    },
    [execPlaybookIdApplied, execStatus]
  );

  const handleRefreshAll = useCallback(() => {
    loadDefinitions({ quiet: true });
    loadExecutions({ quiet: true });
  }, [loadDefinitions, loadExecutions]);

  const handleCloseDetail = useCallback(() => {
    setDetailKind(null);
    setDetailRecord(null);
    setDetailError("");
    setDetailLoading(false);
  }, []);

  const handleViewDefinition = useCallback(async (playbookId) => {
    setDetailKind("definition");
    setDetailRecord(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const row = await getPlaybook(playbookId);
      setDetailRecord(row || null);
    } catch (err) {
      setDetailRecord(null);
      setDetailError(err.message || "Unable to load definition details.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleViewExecution = useCallback(async (executionId) => {
    setDetailKind("execution");
    setDetailRecord(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const row = await getPlaybookExecution(executionId);
      setDetailRecord(row || null);
    } catch (err) {
      setDetailRecord(null);
      setDetailError(err.message || "Unable to load execution details.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  const handleApplyExecutionPlaybookFilter = useCallback(() => {
    setExecPlaybookIdApplied(execPlaybookIdDraft.trim());
  }, [execPlaybookIdDraft]);

  useEffect(() => {
    loadDefinitions();
  }, [loadDefinitions]);

  useEffect(() => {
    loadExecutions();
  }, [loadExecutions]);

  const mono = { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "12px" };

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>SOAR</p>
          <h2 style={cardTitleStyle}>Playbooks</h2>
          <p style={cardSubtitleStyle}>
            Playbooks are visible only; execution is not enabled yet. This view loads configured
            definitions and execution records using read-only APIs.
          </p>
        </div>
        <div style={controlsStyle}>
          <button
            type="button"
            onClick={() => setActivePanel("definitions")}
            style={{
              ...subTabStyle,
              ...(activePanel === "definitions" ? subTabActiveStyle : subTabInactiveStyle),
            }}
          >
            Definitions
          </button>
          <button
            type="button"
            onClick={() => setActivePanel("executions")}
            style={{
              ...subTabStyle,
              ...(activePanel === "executions" ? subTabActiveStyle : subTabInactiveStyle),
            }}
          >
            Executions
          </button>
          <button
            type="button"
            onClick={handleRefreshAll}
            disabled={defLoading || execLoading || defRefreshing || execRefreshing}
            style={{
              ...refreshButtonStyle,
              opacity: defLoading || execLoading || defRefreshing || execRefreshing ? 0.65 : 1,
            }}
          >
            {defRefreshing || execRefreshing ? "Refreshing…" : "Refresh"}
          </button>
        </div>
      </div>

      <div style={panelContentStyle}>
        {activePanel === "definitions" ? (
          <>
            <div style={toolbarStyle}>
              <label style={filterWrapperStyle}>
                <span style={filterLabelStyle}>Enabled filter</span>
                <select
                  value={enabledOption}
                  onChange={(e) => setEnabledOption(e.target.value)}
                  style={selectStyle}
                >
                  {ENABLED_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>
                      {opt.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {defError ? <div style={errorStateStyle}>{defError}</div> : null}
            {defLoading ? (
              <p style={emptyTextStyle}>Loading playbook definitions…</p>
            ) : definitions.length === 0 ? (
              <p style={emptyTextStyle}>
                {enabledOption === "all"
                  ? "No playbook definitions found."
                  : "No playbook definitions match this filter."}
              </p>
            ) : (
              <div style={tableWrapperStyle}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={headerCellStyle}>ID</th>
                      <th style={headerCellStyle}>Name</th>
                      <th style={headerCellStyle}>Enabled</th>
                      <th style={headerCellStyle}>Trigger summary</th>
                      <th style={headerCellStyle}>Steps</th>
                      <th style={headerCellStyle}>Created</th>
                      <th style={headerCellStyle}>Updated</th>
                      <th style={headerCellStyle}>View</th>
                    </tr>
                  </thead>
                  <tbody>
                    {definitions.map((row) => (
                      <tr key={row.id} style={rowStyle}>
                        <td style={{ ...bodyCellStyle, ...mono }}>{row.id}</td>
                        <td style={bodyCellStyle}>{row.name}</td>
                        <td style={bodyCellStyle}>{row.enabled ? "Yes" : "No"}</td>
                        <td style={bodyCellStyle}>{summarizeTrigger(row.trigger_config)}</td>
                        <td style={bodyCellStyle}>{stepCount(row.steps)}</td>
                        <td style={bodyCellStyle}>{formatAdminTimestamp(row.created_at, "—")}</td>
                        <td style={bodyCellStyle}>{formatAdminTimestamp(row.updated_at, "—")}</td>
                        <td style={bodyCellStyle}>
                          <button
                            type="button"
                            style={viewButtonStyle}
                            onClick={() => handleViewDefinition(row.id)}
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : (
          <>
            <div style={toolbarStyle}>
              <label style={filterWrapperStyle}>
                <span style={filterLabelStyle}>Status</span>
                <select
                  value={execStatus}
                  onChange={(e) => setExecStatus(e.target.value)}
                  style={selectStyle}
                >
                  <option value="">All statuses</option>
                  {EXEC_STATUSES.map((s) => (
                    <option key={s} value={s}>
                      {s}
                    </option>
                  ))}
                </select>
              </label>
              <label style={filterWrapperStyle}>
                <span style={filterLabelStyle}>Playbook ID</span>
                <input
                  type="text"
                  value={execPlaybookIdDraft}
                  onChange={(e) => setExecPlaybookIdDraft(e.target.value)}
                  placeholder="Exact playbook id"
                  style={textInputStyle}
                />
              </label>
              <button type="button" onClick={handleApplyExecutionPlaybookFilter} style={applyButtonStyle}>
                Apply playbook filter
              </button>
            </div>
            {execError ? <div style={errorStateStyle}>{execError}</div> : null}
            {execLoading ? (
              <p style={emptyTextStyle}>Loading playbook executions…</p>
            ) : executions.length === 0 ? (
              <p style={emptyTextStyle}>
                {!execStatus && !execPlaybookIdApplied
                  ? "No playbook execution records found."
                  : "No playbook execution records match this filter."}
              </p>
            ) : (
              <div style={tableWrapperStyle}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={headerCellStyle}>ID</th>
                      <th style={headerCellStyle}>Playbook</th>
                      <th style={headerCellStyle}>Status</th>
                      <th style={headerCellStyle}>Alert</th>
                      <th style={headerCellStyle}>Incident</th>
                      <th style={headerCellStyle}>Last step</th>
                      <th style={headerCellStyle}>Created</th>
                      <th style={headerCellStyle}>Started</th>
                      <th style={headerCellStyle}>Completed</th>
                      <th style={headerCellStyle}>View</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executions.map((row) => (
                      <tr key={row.id} style={rowStyle}>
                        <td style={{ ...bodyCellStyle, ...mono }}>{row.id}</td>
                        <td style={{ ...bodyCellStyle, ...mono }}>{row.playbook_id}</td>
                        <td style={bodyCellStyle}>{row.status}</td>
                        <td style={bodyCellStyle}>
                          {row.alert_id === null || row.alert_id === undefined ? "—" : row.alert_id}
                        </td>
                        <td style={bodyCellStyle}>
                          {row.incident_id === null || row.incident_id === undefined
                            ? "—"
                            : row.incident_id}
                        </td>
                        <td style={bodyCellStyle}>
                          {row.last_completed_step === null || row.last_completed_step === undefined
                            ? "—"
                            : row.last_completed_step}
                        </td>
                        <td style={bodyCellStyle}>{formatAdminTimestamp(row.created_at, "—")}</td>
                        <td style={bodyCellStyle}>{formatAdminTimestamp(row.started_at, "—")}</td>
                        <td style={bodyCellStyle}>{formatAdminTimestamp(row.completed_at, "—")}</td>
                        <td style={bodyCellStyle}>
                          <button
                            type="button"
                            style={viewButtonStyle}
                            onClick={() => handleViewExecution(row.id)}
                          >
                            View
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        <div style={detailPanelStyle}>
          <div style={detailHeaderStyle}>
            <h3 style={detailTitleStyle}>
              {detailKind === "definition"
                ? "Definition detail"
                : detailKind === "execution"
                ? "Execution detail"
                : "Detail"}
            </h3>
            {detailKind ? (
              <button type="button" style={detailCloseButtonStyle} onClick={handleCloseDetail}>
                Close
              </button>
            ) : null}
          </div>
          {detailLoading ? (
            <p style={emptyTextStyle}>Loading detail…</p>
          ) : detailError ? (
            <div style={errorStateStyle}>{detailError}</div>
          ) : detailRecord ? (
            <>
              {detailKind === "definition" ? (
                <div style={detailGridStyle}>
                  <div style={detailFieldStyle}>
                    <span style={detailLabelStyle}>ID</span>
                    <span style={detailValueStyle}>{detailRecord.id}</span>
                  </div>
                  <div style={detailFieldStyle}>
                    <span style={detailLabelStyle}>Name</span>
                    <span style={detailValueStyle}>{detailRecord.name}</span>
                  </div>
                  <div style={detailFieldStyle}>
                    <span style={detailLabelStyle}>Enabled</span>
                    <span style={detailValueStyle}>{detailRecord.enabled ? "Yes" : "No"}</span>
                  </div>
                </div>
              ) : (
                <div style={detailGridStyle}>
                  <div style={detailFieldStyle}>
                    <span style={detailLabelStyle}>Execution ID</span>
                    <span style={detailValueStyle}>{detailRecord.id}</span>
                  </div>
                  <div style={detailFieldStyle}>
                    <span style={detailLabelStyle}>Status</span>
                    <span style={detailValueStyle}>{detailRecord.status}</span>
                  </div>
                </div>
              )}
              <div style={jsonBlockWrapStyle}>
                <div style={jsonBlockTitleStyle}>
                  {detailKind === "definition" ? "trigger_config" : "steps_log"}
                </div>
                <pre style={jsonPreStyle}>
                  {JSON.stringify(
                    detailKind === "definition" ? detailRecord.trigger_config : detailRecord.steps_log,
                    null,
                    2
                  )}
                </pre>
              </div>
              {detailKind === "definition" ? (
                <div style={jsonBlockWrapStyle}>
                  <div style={jsonBlockTitleStyle}>steps</div>
                  <pre style={jsonPreStyle}>{JSON.stringify(detailRecord.steps, null, 2)}</pre>
                </div>
              ) : null}
            </>
          ) : (
            <p style={emptyTextStyle}>Select a row and choose View to inspect read-only JSON.</p>
          )}
        </div>
      </div>
    </section>
  );
}

export default PlaybooksPanel;

const sectionLabelStyle = {
  margin: "0 0 8px 0",
  color: "#8b949e",
  fontSize: "10px",
  fontWeight: "700",
  letterSpacing: "0.14em",
  textTransform: "uppercase",
};

const controlsStyle = {
  display: "flex",
  alignItems: "flex-end",
  gap: "10px",
  flexWrap: "wrap",
};

const subTabStyle = {
  minHeight: "36px",
  padding: "8px 12px",
  borderRadius: "8px",
  fontSize: "13px",
  fontWeight: "700",
  cursor: "pointer",
};

const subTabActiveStyle = {
  border: "1px solid rgba(88, 166, 255, 0.45)",
  backgroundColor: "rgba(88, 166, 255, 0.12)",
  color: "#93c5fd",
};

const subTabInactiveStyle = {
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#8b949e",
};

const refreshButtonStyle = {
  minHeight: "40px",
  padding: "10px 14px",
  borderRadius: "10px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.14)",
  color: "#93c5fd",
  fontSize: "13px",
  fontWeight: "700",
  cursor: "pointer",
};

const panelContentStyle = {
  padding: "20px 20px 22px",
};

const toolbarStyle = {
  display: "flex",
  flexWrap: "wrap",
  gap: "12px",
  alignItems: "flex-end",
  marginBottom: "14px",
};

const textInputStyle = {
  minWidth: "200px",
  minHeight: "38px",
  padding: "8px 10px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  fontSize: "13px",
};

const applyButtonStyle = {
  minHeight: "38px",
  padding: "8px 12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "13px",
  fontWeight: "600",
  cursor: "pointer",
};

const errorStateStyle = {
  marginBottom: "12px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(248, 113, 113, 0.35)",
  backgroundColor: "rgba(248, 113, 113, 0.08)",
  color: "#fecaca",
  fontSize: "13px",
};

const emptyTextStyle = {
  margin: "10px 0",
  color: "#8b949e",
  fontSize: "14px",
};

const tableWrapperStyle = {
  overflowX: "auto",
  border: "1px solid #30363d",
  borderRadius: "8px",
};

const tableStyle = {
  width: "100%",
  borderCollapse: "collapse",
  fontSize: "13px",
};

const headerCellStyle = {
  textAlign: "left",
  padding: "10px 12px",
  borderBottom: "1px solid #30363d",
  color: "#8b949e",
  fontWeight: "700",
  backgroundColor: "#0d1117",
};

const bodyCellStyle = {
  padding: "10px 12px",
  borderBottom: "1px solid #21262d",
  color: "#e6edf3",
  verticalAlign: "top",
};

const rowStyle = {
  backgroundColor: "#0b1020",
};

const viewButtonStyle = {
  padding: "6px 10px",
  borderRadius: "6px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.12)",
  color: "#93c5fd",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const detailPanelStyle = {
  marginTop: "20px",
  padding: "16px",
  borderRadius: "10px",
  border: "1px solid #30363d",
  backgroundColor: "#0b1020",
};

const detailHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: "12px",
};

const detailTitleStyle = {
  margin: 0,
  fontSize: "16px",
  color: "#e6edf3",
};

const detailCloseButtonStyle = {
  padding: "6px 10px",
  borderRadius: "6px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "12px",
  cursor: "pointer",
};

const detailGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(180px, 1fr))",
  gap: "10px",
  marginBottom: "12px",
};

const detailFieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "4px",
};

const detailLabelStyle = {
  fontSize: "11px",
  color: "#8b949e",
  fontWeight: "700",
  textTransform: "uppercase",
};

const detailValueStyle = {
  fontSize: "14px",
  color: "#e6edf3",
};

const jsonBlockWrapStyle = {
  marginTop: "10px",
};

const jsonBlockTitleStyle = {
  fontSize: "12px",
  color: "#8b949e",
  marginBottom: "6px",
  fontWeight: "700",
};

const jsonPreStyle = {
  margin: 0,
  padding: "12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#050810",
  color: "#c9d1d9",
  fontSize: "12px",
  lineHeight: 1.45,
  maxHeight: "280px",
  overflow: "auto",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};
