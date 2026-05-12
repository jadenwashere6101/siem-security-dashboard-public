import React, { useCallback, useEffect, useState } from "react";
import {
  getPlaybook,
  getPlaybookExecution,
  listPlaybookExecutions,
  listPlaybooks,
  createPlaybookDefinition,
  updatePlaybookDefinition,
  setPlaybookDefinitionEnabled,
  retryExecution,
  abandonExecution,
  resumeExecution,
  listPlaybookSchedules,
  getPlaybookSchedule,
} from "../services/playbookService";
import { listNotificationDeliveries } from "../services/notificationDeliveryService";
import { formatAdminTimestamp } from "../utils/adminPanelDisplay";

const PAGE_LIMIT = 50;
const EXEC_STATUSES = ["pending", "running", "awaiting_approval", "success", "failed", "abandoned"];
const APPROVAL_PAUSED_MESSAGE =
  "Approval-gated simulation paused; no later steps will run until approval.";
const ENABLED_OPTIONS = [
  { value: "all", label: "All definitions" },
  { value: "enabled", label: "Enabled only" },
  { value: "disabled", label: "Disabled only" },
];
const SAFE_SCHEDULE_METADATA_KEYS = [
  "description",
  "owner",
  "source",
  "environment",
  "created_by",
  "reason",
  "ticket_id",
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

function formatDetailValue(value, emptyValue = "—") {
  return value === null || value === undefined || value === "" ? emptyValue : value;
}

function formatFlagValue(value) {
  if (value === true) {
    return "Yes";
  }
  if (value === false) {
    return "No";
  }
  return "Unknown";
}

function normalizeStepsLog(stepsLog) {
  if (Array.isArray(stepsLog)) {
    return stepsLog;
  }
  if (typeof stepsLog === "string" && stepsLog.trim()) {
    try {
      const parsed = JSON.parse(stepsLog);
      return Array.isArray(parsed) ? parsed : [];
    } catch (err) {
      return [];
    }
  }
  return [];
}

function getExecutionStatusSummary(status) {
  switch (status) {
    case "pending":
      return "Pending simulation; no steps have been consumed yet.";
    case "running":
      return "Simulation is marked running and may have partial step output.";
    case "awaiting_approval":
      return "Simulation is paused at an approval gate.";
    case "success":
      return "Simulation completed successfully.";
    case "failed":
      return "Simulation failed before completing all steps.";
    case "abandoned":
      return "Execution was abandoned and will not continue in this view.";
    default:
      return "Execution status is unknown.";
  }
}

function getEmptyTimelineText(status) {
  switch (status) {
    case "pending":
      return "No simulated steps have run yet.";
    case "running":
      return "No step output has been recorded yet.";
    case "awaiting_approval":
      return "No approval gate output has been recorded yet.";
    case "success":
      return "Playbook completed with no defined steps.";
    case "failed":
      return "Execution failed before step output was recorded.";
    default:
      return "No step output is available.";
  }
}

function formatStepLabel(step, index) {
  const rawIndex =
    step.step_index !== null && step.step_index !== undefined ? step.step_index : index;
  return `Step ${Number.isFinite(Number(rawIndex)) ? Number(rawIndex) + 1 : index + 1}`;
}

function getStepAction(step) {
  return step.action || step.step_action || step.action_type || step.step?.action || "unspecified";
}

function getStepMessage(step) {
  return step.message || step.summary || step.result?.message || step.output?.message || "";
}

function getStepFlag(step, flagName) {
  if (step[flagName] !== undefined) {
    return step[flagName];
  }
  return step.output?.[flagName];
}

function getStepApprovalValue(step, fieldName) {
  if (step[fieldName] !== null && step[fieldName] !== undefined && step[fieldName] !== "") {
    return step[fieldName];
  }
  return step.output?.[fieldName];
}

function getStepSkipReason(step) {
  return getStepApprovalValue(step, "skip_reason") || step.reason || "";
}

function getStepEventLabel(step) {
  switch (step.event) {
    case "approval_requested":
      return "Approval requested";
    case "approval_approved":
      return "Approval approved";
    case "approval_resumed":
      return "Simulation resumed";
    case "approval_denied":
      return "Approval denied";
    case "approval_expired":
      return "Approval expired";
    case "skipped_after_approval_gate":
      return "Skipped after approval gate";
    default:
      break;
  }

  if (step.status === "skipped") {
    return "Skipped";
  }
  if (step.status === "aborted") {
    return "Aborted";
  }
  if (getStepAction(step) === "require_approval" && step.status === "failed") {
    return "Approval gate failed";
  }
  return formatDetailValue(step.status, "unknown");
}

function isAwaitingApproval(detailRecord) {
  if (detailRecord?.status === "awaiting_approval") {
    return true;
  }
  return normalizeStepsLog(detailRecord?.steps_log).some(
    (step) =>
      step.event === "approval_requested" &&
      (step.approval_status === "pending" || step.output?.approval_status === "pending")
  );
}

function getExecutionControls(status, isSuperAdmin) {
  if (!isSuperAdmin) {
    return { canRetry: false, canAbandon: false, canResume: false };
  }
  return {
    canRetry: status === "failed" || status === "abandoned",
    canAbandon: status === "pending" || status === "running" || status === "awaiting_approval",
    canResume: status === "awaiting_approval",
  };
}

function getStepErrorText(step) {
  if (!step.error) {
    return "";
  }
  if (typeof step.error === "string") {
    return step.error;
  }
  return step.error.message || JSON.stringify(step.error);
}

function getStepResultText(step) {
  const result = step.result || step.output;
  if (!result) {
    return "";
  }
  if (typeof result === "string") {
    return result;
  }
  return JSON.stringify(result, null, 2);
}

function getStepAdapterResult(step) {
  const adapterResult = step?.output?.adapter_result;
  if (!adapterResult || typeof adapterResult !== "object" || Array.isArray(adapterResult)) {
    return null;
  }
  return adapterResult;
}

function getAdapterMetadataEntries(adapterResult) {
  const metadata = adapterResult?.metadata;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    return [];
  }
  return Object.entries(metadata);
}

function getSafeScheduleMetadataEntries(schedule) {
  const metadata = schedule?.metadata || schedule?.details;
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    return [];
  }
  return SAFE_SCHEDULE_METADATA_KEYS.filter((key) => metadata[key] !== undefined).map((key) => [
    key,
    metadata[key],
  ]);
}

function formatAdapterFieldValue(value) {
  if (value === true || value === false) {
    return formatFlagValue(value);
  }
  if (value === null || value === undefined || value === "") {
    return "—";
  }
  if (typeof value === "object") {
    return JSON.stringify(value);
  }
  return String(value);
}

const UNSAFE_DELIVERY_METADATA_KEY_SNIPPETS = [
  "webhook",
  "token",
  "secret",
  "password",
  "authorization",
  "cookie",
  "bearer",
  "api_key",
  "apikey",
  "raw_payload",
  "raw_response",
  "header",
];

function deliveryMetadataKeyIsSafe(key) {
  if (!key || typeof key !== "string") {
    return false;
  }
  const lk = key.toLowerCase();
  if (lk.includes("://")) {
    return false;
  }
  return !UNSAFE_DELIVERY_METADATA_KEY_SNIPPETS.some((frag) => lk.includes(frag));
}

function formatDeliveryMetadataValue(value) {
  if (typeof value === "string" && /https?:\/\//i.test(value)) {
    return "[REDACTED_URL]";
  }
  return formatAdapterFieldValue(value);
}

function getSafeNotificationDeliveryMetadataEntries(metadata) {
  if (!metadata || typeof metadata !== "object" || Array.isArray(metadata)) {
    return [];
  }
  return Object.entries(metadata).filter(([key]) => deliveryMetadataKeyIsSafe(key));
}

const DELIVERY_HISTORY_DISCLAIMER =
  // spec: SPEC-NOTIFY-001
  "Delivery history shows recorded notification attempts (simulation or real mode). " +
  "It is operational evidence only — it does not guarantee that a human received a message at the provider.";

function PlaybooksPanel({
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterWrapperStyle,
  filterLabelStyle,
  selectStyle,
  userRole,
}) {
  const isSuperAdmin = userRole === "super_admin";
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
  const [executionActionInProgress, setExecutionActionInProgress] = useState({});
  const [executionActionError, setExecutionActionError] = useState({});

  const [detailKind, setDetailKind] = useState(null);
  const [detailRecord, setDetailRecord] = useState(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState("");

  const [deliveryAttempts, setDeliveryAttempts] = useState([]);
  const [deliveryLoading, setDeliveryLoading] = useState(false);
  const [deliveryError, setDeliveryError] = useState("");

  // Form state for create/edit
  const [formMode, setFormMode] = useState(null); // null, "create", or "edit"
  const [formId, setFormId] = useState("");
  const [formName, setFormName] = useState("");
  const [formDescription, setFormDescription] = useState("");
  const [formEnabled, setFormEnabled] = useState(false);
  const [formTriggerJson, setFormTriggerJson] = useState("{}");
  const [formStepsJson, setFormStepsJson] = useState("[]");
  const [formValidationError, setFormValidationError] = useState("");
  const [formSubmitting, setFormSubmitting] = useState(false);
  const [formSubmitError, setFormSubmitError] = useState("");
  const [formSubmitSuccess, setFormSubmitSuccess] = useState("");

  // Schedule state
  const [schedules, setSchedules] = useState([]);
  const [schedLoading, setSchedLoading] = useState(true);
  const [schedRefreshing, setSchedRefreshing] = useState(false);
  const [schedError, setSchedError] = useState("");

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

  const loadSchedules = useCallback(
    async ({ quiet = false } = {}) => {
      try {
        if (quiet) {
          setSchedRefreshing(true);
        } else {
          setSchedLoading(true);
        }
        setSchedError("");
        const data = await listPlaybookSchedules({
          limit: PAGE_LIMIT,
        });
        setSchedules(Array.isArray(data?.items) ? data.items : []);
      } catch (err) {
        setSchedError(err.message || "Unable to load playbook schedules.");
        if (!quiet) {
          setSchedules([]);
        }
      } finally {
        setSchedLoading(false);
        setSchedRefreshing(false);
      }
    },
    []
  );

  const handleRefreshAll = useCallback(() => {
    loadDefinitions({ quiet: true });
    loadExecutions({ quiet: true });
    loadSchedules({ quiet: true });
  }, [loadDefinitions, loadExecutions, loadSchedules]);

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

  const handleViewSchedule = useCallback(async (scheduleId) => {
    setDetailKind("schedule");
    setDetailRecord(null);
    setDetailError("");
    setDetailLoading(true);
    try {
      const row = await getPlaybookSchedule(scheduleId);
      setDetailRecord(row || null);
    } catch (err) {
      setDetailRecord(null);
      setDetailError(err.message || "Unable to load schedule details.");
    } finally {
      setDetailLoading(false);
    }
  }, []);

  useEffect(() => {
    if (detailKind !== "execution" || !detailRecord?.id) {
      setDeliveryAttempts([]);
      setDeliveryError("");
      setDeliveryLoading(false);
      return undefined;
    }

    let cancelled = false;
    setDeliveryLoading(true);
    setDeliveryError("");
    setDeliveryAttempts([]);

    listNotificationDeliveries({
      playbook_execution_id: detailRecord.id,
      limit: 50,
    })
      .then((data) => {
        if (cancelled) {
          return;
        }
        setDeliveryAttempts(Array.isArray(data?.items) ? data.items : []);
        setDeliveryLoading(false);
      })
      .catch((err) => {
        if (cancelled) {
          return;
        }
        setDeliveryAttempts([]);
        setDeliveryError(err.message || "Unable to load notification deliveries.");
        setDeliveryLoading(false);
      });

    return () => {
      cancelled = true;
    };
  }, [detailKind, detailRecord?.id]);

  const handleApplyExecutionPlaybookFilter = useCallback(() => {
    setExecPlaybookIdApplied(execPlaybookIdDraft.trim());
  }, [execPlaybookIdDraft]);

  const runExecutionAction = useCallback(
    async (executionId, actionFn) => {
      setExecutionActionInProgress((current) => ({ ...current, [executionId]: true }));
      setExecutionActionError((current) => ({ ...current, [executionId]: null }));
      try {
        await actionFn(executionId);
        setExecutionActionError((current) => ({ ...current, [executionId]: null }));
        await loadExecutions({ quiet: true });
      } catch (err) {
        setExecutionActionError((current) => ({
          ...current,
          [executionId]: err.message || "Simulation control action failed.",
        }));
      } finally {
        setExecutionActionInProgress((current) => ({ ...current, [executionId]: false }));
      }
    },
    [loadExecutions]
  );

  const handleRetryExecution = useCallback(
    (executionId) => runExecutionAction(executionId, retryExecution),
    [runExecutionAction]
  );

  const handleAbandonExecution = useCallback(
    (executionId) => {
      const confirmed = window.confirm(
        "Abandon this execution? It will stop and cannot be resumed."
      );
      if (!confirmed) {
        return;
      }
      runExecutionAction(executionId, abandonExecution);
    },
    [runExecutionAction]
  );

  const handleResumeExecution = useCallback(
    (executionId) => runExecutionAction(executionId, resumeExecution),
    [runExecutionAction]
  );

  // Form handlers
  const validateIdFormat = (id) => {
    if (!id) return false;
    return /^[a-z0-9_-]+$/.test(id);
  };

  const validateForm = () => {
    setFormValidationError("");
    const id = formId.trim();
    const name = formName.trim();
    const triggerJson = formTriggerJson.trim();
    const stepsJson = formStepsJson.trim();

    if (formMode === "create" && !id) {
      setFormValidationError("ID is required for creating a definition.");
      return false;
    }
    if (formMode === "create" && !validateIdFormat(id)) {
      setFormValidationError("ID must contain only lowercase letters, digits, underscores, and hyphens.");
      return false;
    }
    if (!name) {
      setFormValidationError("Name is required.");
      return false;
    }

    let triggerObj;
    try {
      triggerObj = JSON.parse(triggerJson);
    } catch (e) {
      setFormValidationError(`Invalid trigger_config JSON: ${e.message}`);
      return false;
    }
    if (typeof triggerObj !== "object" || Array.isArray(triggerObj)) {
      setFormValidationError("Trigger config must be a JSON object, not an array.");
      return false;
    }

    let stepsArr;
    try {
      stepsArr = JSON.parse(stepsJson);
    } catch (e) {
      setFormValidationError(`Invalid steps JSON: ${e.message}`);
      return false;
    }
    if (!Array.isArray(stepsArr)) {
      setFormValidationError("Steps must be a JSON array, not an object.");
      return false;
    }

    return true;
  };

  const handleOpenCreateForm = () => {
    setFormMode("create");
    setFormId("");
    setFormName("");
    setFormDescription("");
    setFormEnabled(false);
    setFormTriggerJson("{}");
    setFormStepsJson('[{"action": "monitor", "params": {}, "on_failure": "abort"}]');
    setFormValidationError("");
    setFormSubmitError("");
    setFormSubmitSuccess("");
  };

  const handleOpenEditForm = (definition) => {
    setFormMode("edit");
    setFormId(definition.id);
    setFormName(definition.name || "");
    setFormDescription(definition.description || "");
    setFormEnabled(definition.enabled || false);
    setFormTriggerJson(JSON.stringify(definition.trigger_config || {}, null, 2));
    setFormStepsJson(JSON.stringify(definition.steps || [], null, 2));
    setFormValidationError("");
    setFormSubmitError("");
    setFormSubmitSuccess("");
  };

  const handleCloseForm = () => {
    setFormMode(null);
    setFormValidationError("");
    setFormSubmitError("");
    setFormSubmitSuccess("");
  };

  const handleSubmitForm = async () => {
    if (!validateForm()) {
      return;
    }

    setFormSubmitting(true);
    setFormSubmitError("");
    setFormSubmitSuccess("");

    try {
      const id = formId.trim();
      const name = formName.trim();
      const description = formDescription.trim() || null;
      const enabled = formEnabled;
      const triggerConfig = JSON.parse(formTriggerJson.trim());
      const steps = JSON.parse(formStepsJson.trim());

      const payload = {
        name,
        description,
        enabled,
        trigger_config: triggerConfig,
        steps,
      };

      if (formMode === "create") {
        await createPlaybookDefinition({ id, ...payload });
        setFormSubmitSuccess(`Created playbook "${name}".`);
      } else if (formMode === "edit") {
        await updatePlaybookDefinition(id, payload);
        setFormSubmitSuccess(`Updated playbook "${name}".`);
      }

      await loadDefinitions({ quiet: true });
      setTimeout(() => {
        handleCloseForm();
      }, 1500);
    } catch (err) {
      setFormSubmitError(err.message || "Failed to submit form.");
    } finally {
      setFormSubmitting(false);
    }
  };

  const handleToggleEnabled = async (definition) => {
    try {
      await setPlaybookDefinitionEnabled(definition.id, !definition.enabled);
      await loadDefinitions({ quiet: true });
    } catch (err) {
      setDefError(err.message || "Failed to update enabled status.");
    }
  };

  useEffect(() => {
    loadDefinitions();
  }, [loadDefinitions]);

  useEffect(() => {
    loadExecutions();
  }, [loadExecutions]);

  useEffect(() => {
    loadSchedules();
  }, [loadSchedules]);

  const mono = { fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace", fontSize: "12px" };

  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <p style={sectionLabelStyle}>SOAR</p>
          <h2 style={cardTitleStyle}>Playbooks</h2>
          <p style={cardSubtitleStyle}>
            Simulation-only playbook controls. Retry, abandon, and resume actions are available
            to super_admin users. Analyst users have read-only access.
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
            onClick={() => setActivePanel("schedules")}
            style={{
              ...subTabStyle,
              ...(activePanel === "schedules" ? subTabActiveStyle : subTabInactiveStyle),
            }}
          >
            Schedules
          </button>
          <button
            type="button"
            onClick={handleRefreshAll}
            disabled={defLoading || execLoading || schedLoading || defRefreshing || execRefreshing || schedRefreshing}
            style={{
              ...refreshButtonStyle,
              opacity: defLoading || execLoading || schedLoading || defRefreshing || execRefreshing || schedRefreshing ? 0.65 : 1,
            }}
          >
            {defRefreshing || execRefreshing || schedRefreshing ? "Refreshing…" : "Refresh"}
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
              {isSuperAdmin && (
                <button
                  type="button"
                  onClick={handleOpenCreateForm}
                  style={newDefinitionButtonStyle}
                >
                  + New Definition
                </button>
              )}
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
                      {isSuperAdmin && <th style={headerCellStyle}>Actions</th>}
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
                        {isSuperAdmin && (
                          <td style={bodyCellStyle}>
                            <div style={actionButtonsWrapperStyle}>
                              <button
                                type="button"
                                onClick={() => handleOpenEditForm(row)}
                                style={smallActionButtonStyle}
                              >
                                Edit
                              </button>
                              <button
                                type="button"
                                onClick={() => handleToggleEnabled(row)}
                                style={smallActionButtonStyle}
                              >
                                {row.enabled ? "Disable" : "Enable"}
                              </button>
                            </div>
                          </td>
                        )}
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
        ) : activePanel === "executions" ? (
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
                      {isSuperAdmin && <th style={headerCellStyle}>Actions</th>}
                      <th style={headerCellStyle}>View</th>
                    </tr>
                  </thead>
                  <tbody>
                    {executions.map((row) => {
                      const controls = getExecutionControls(row.status, isSuperAdmin);
                      const actionBusy = Boolean(executionActionInProgress[row.id]);
                      const actionError = executionActionError[row.id];
                      return (
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
                          {isSuperAdmin && (
                            <td style={bodyCellStyle}>
                              <div style={actionButtonsWrapperStyle}>
                                {controls.canRetry ? (
                                  <button
                                    type="button"
                                    onClick={() => handleRetryExecution(row.id)}
                                    disabled={actionBusy}
                                    style={{
                                      ...smallActionButtonStyle,
                                      opacity: actionBusy ? 0.65 : 1,
                                    }}
                                  >
                                    Retry simulation
                                  </button>
                                ) : null}
                                {controls.canAbandon ? (
                                  <button
                                    type="button"
                                    onClick={() => handleAbandonExecution(row.id)}
                                    disabled={actionBusy}
                                    style={{
                                      ...smallActionButtonStyle,
                                      opacity: actionBusy ? 0.65 : 1,
                                    }}
                                  >
                                    Abandon
                                  </button>
                                ) : null}
                                {controls.canResume ? (
                                  <button
                                    type="button"
                                    onClick={() => handleResumeExecution(row.id)}
                                    disabled={actionBusy}
                                    style={{
                                      ...smallActionButtonStyle,
                                      opacity: actionBusy ? 0.65 : 1,
                                    }}
                                  >
                                    Resume simulation
                                  </button>
                                ) : null}
                              </div>
                              {actionError ? (
                                <div style={actionErrorStyle}>{actionError}</div>
                              ) : null}
                            </td>
                          )}
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
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </>
        ) : (
          <>
            <div style={toolbarStyle} />
            <div style={noticeStyle}>
              <p style={metadataOnlyNoticeStyle}>
                Schedules are metadata-only. No scheduler or daemon exists, and these records do not execute playbooks.
              </p>
            </div>
            {schedError ? <div style={errorStateStyle}>{schedError}</div> : null}
            {schedLoading ? (
              <p style={emptyTextStyle}>Loading playbook schedules…</p>
            ) : schedules.length === 0 ? (
              <p style={emptyTextStyle}>No playbook schedules found.</p>
            ) : (
              <div style={tableWrapperStyle}>
                <table style={tableStyle}>
                  <thead>
                    <tr>
                      <th style={headerCellStyle}>ID</th>
                      <th style={headerCellStyle}>Playbook</th>
                      <th style={headerCellStyle}>Enabled</th>
                      <th style={headerCellStyle}>Paused</th>
                      <th style={headerCellStyle}>Schedule</th>
                      <th style={headerCellStyle}>Missed-Run Policy</th>
                      <th style={headerCellStyle}>Last Run</th>
                      <th style={headerCellStyle}>Next Run</th>
                      <th style={headerCellStyle}>View</th>
                    </tr>
                  </thead>
                  <tbody>
                    {schedules.map((row) => (
                      <tr key={row.id} style={rowStyle}>
                        <td style={{ ...bodyCellStyle, ...mono }}>{row.id}</td>
                        <td style={{ ...bodyCellStyle, ...mono }}>{row.playbook_id}</td>
                        <td style={bodyCellStyle}>{row.enabled ? "Yes" : "No"}</td>
                        <td style={bodyCellStyle}>{row.paused ? "Yes" : "No"}</td>
                        <td style={bodyCellStyle}>{row.schedule_expression}</td>
                        <td style={bodyCellStyle}>{row.missed_run_policy}</td>
                        <td style={bodyCellStyle}>{formatAdminTimestamp(row.last_run_at, "—")}</td>
                        <td style={bodyCellStyle}>{formatAdminTimestamp(row.next_run_at, "—")}</td>
                        <td style={bodyCellStyle}>
                          <button
                            type="button"
                            onClick={() => handleViewSchedule(row.id)}
                            style={viewButtonStyle}
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
                : detailKind === "schedule"
                ? "Schedule detail"
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
              ) : detailKind === "schedule" ? (
                <>
                  <div style={statusSummaryStyle}>
                    Metadata-only schedule visibility. This record does not execute a playbook.
                  </div>
                  <div style={detailGridStyle}>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Schedule ID</span>
                      <span style={detailValueStyle}>{formatDetailValue(detailRecord.id)}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Playbook ID</span>
                      <span style={detailValueStyle}>{formatDetailValue(detailRecord.playbook_id)}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Enabled</span>
                      <span style={detailValueStyle}>{formatFlagValue(detailRecord.enabled)}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Paused</span>
                      <span style={detailValueStyle}>{formatFlagValue(detailRecord.paused)}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Schedule Expression</span>
                      <span style={detailValueStyle}>
                        {formatDetailValue(detailRecord.schedule_expression)}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Timezone</span>
                      <span style={detailValueStyle}>{formatDetailValue(detailRecord.timezone)}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Missed-Run Policy</span>
                      <span style={detailValueStyle}>
                        {formatDetailValue(detailRecord.missed_run_policy)}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Max Catchup Runs</span>
                      <span style={detailValueStyle}>
                        {formatDetailValue(detailRecord.max_catchup_runs)}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Max Concurrent Runs</span>
                      <span style={detailValueStyle}>
                        {formatDetailValue(detailRecord.max_concurrent_runs)}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Last Run</span>
                      <span style={detailValueStyle}>
                        {formatAdminTimestamp(detailRecord.last_run_at, "—")}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Next Run</span>
                      <span style={detailValueStyle}>
                        {formatAdminTimestamp(detailRecord.next_run_at, "—")}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Last Success</span>
                      <span style={detailValueStyle}>
                        {formatAdminTimestamp(detailRecord.last_success_at, "—")}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Last Failure</span>
                      <span style={detailValueStyle}>
                        {formatAdminTimestamp(detailRecord.last_failure_at, "—")}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Last Scheduled Execution ID</span>
                      <span style={detailValueStyle}>
                        {formatDetailValue(detailRecord.last_scheduled_execution_id)}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Created</span>
                      <span style={detailValueStyle}>
                        {formatAdminTimestamp(detailRecord.created_at, "—")}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Updated</span>
                      <span style={detailValueStyle}>
                        {formatAdminTimestamp(detailRecord.updated_at, "—")}
                      </span>
                    </div>
                  </div>
                  {getSafeScheduleMetadataEntries(detailRecord).length > 0 ? (
                    <div style={adapterMetadataStyle}>
                      <div style={adapterMetadataTitleStyle}>Safe Metadata</div>
                      <div style={timelineMetaGridStyle}>
                        {getSafeScheduleMetadataEntries(detailRecord).map(([key, value]) => (
                          <div key={key} style={detailFieldStyle}>
                            <span style={detailLabelStyle}>{key}</span>
                            <span style={detailValueStyle}>{formatAdapterFieldValue(value)}</span>
                          </div>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </>
              ) : (
                <>
                  <div style={detailGridStyle}>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Execution ID</span>
                      <span style={detailValueStyle}>{detailRecord.id}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Playbook ID</span>
                      <span style={detailValueStyle}>{formatDetailValue(detailRecord.playbook_id)}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Status</span>
                      <span style={detailValueStyle}>{formatDetailValue(detailRecord.status)}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Alert ID</span>
                      <span style={detailValueStyle}>{formatDetailValue(detailRecord.alert_id)}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Incident ID</span>
                      <span style={detailValueStyle}>{formatDetailValue(detailRecord.incident_id)}</span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Last Completed Step</span>
                      <span style={detailValueStyle}>
                        {formatDetailValue(detailRecord.last_completed_step)}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Created</span>
                      <span style={detailValueStyle}>
                        {formatAdminTimestamp(detailRecord.created_at, "—")}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Started</span>
                      <span style={detailValueStyle}>
                        {formatAdminTimestamp(detailRecord.started_at, "—")}
                      </span>
                    </div>
                    <div style={detailFieldStyle}>
                      <span style={detailLabelStyle}>Completed</span>
                      <span style={detailValueStyle}>
                        {formatAdminTimestamp(detailRecord.completed_at, "—")}
                      </span>
                    </div>
                  </div>
                  <div style={statusSummaryStyle}>
                    {getExecutionStatusSummary(detailRecord.status)}
                  </div>
                  {isAwaitingApproval(detailRecord) ? (
                    <div style={approvalNoticeStyle}>{APPROVAL_PAUSED_MESSAGE}</div>
                  ) : null}
                  <div style={timelineHeaderStyle}>Notification delivery history</div>
                  <p style={deliveryEvidenceNoteStyle}>{DELIVERY_HISTORY_DISCLAIMER}</p>
                  {deliveryLoading ? (
                    <p style={emptyTextStyle}>Loading notification deliveries…</p>
                  ) : null}
                  {deliveryError ? <div style={errorStateStyle}>{deliveryError}</div> : null}
                  {!deliveryLoading && !deliveryError && deliveryAttempts.length === 0 ? (
                    <p style={emptyTextStyle}>No delivery attempts recorded for this execution.</p>
                  ) : null}
                  {deliveryAttempts.length > 0 ? (
                    <div style={timelineListStyle}>
                      {deliveryAttempts.map((attempt) => {
                        const metaEntries = getSafeNotificationDeliveryMetadataEntries(
                          attempt.metadata
                        );
                        return (
                          <div key={attempt.id} style={timelineCardStyle}>
                            <div style={timelineCardHeaderStyle}>
                              <span style={timelineStepLabelStyle}>Delivery #{attempt.id}</span>
                              <span style={timelineActionStyle}>
                                {formatDetailValue(attempt.provider)} /{" "}
                                {formatDetailValue(attempt.mode)}
                              </span>
                              <span style={timelineStatusStyle}>
                                {formatDetailValue(attempt.status)}
                              </span>
                            </div>
                            <div style={timelineMetaGridStyle}>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Correlation ID</span>
                                <span style={detailValueStyle}>
                                  {formatDetailValue(attempt.correlation_id)}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Adapter</span>
                                <span style={detailValueStyle}>
                                  {formatDetailValue(attempt.adapter_name)}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Action</span>
                                <span style={detailValueStyle}>
                                  {formatDetailValue(attempt.action)}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Circuit breaker</span>
                                <span style={detailValueStyle}>
                                  {formatDetailValue(attempt.circuit_breaker_state)}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Timeout (seconds)</span>
                                <span style={detailValueStyle}>
                                  {formatDetailValue(attempt.timeout_seconds)}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Created</span>
                                <span style={detailValueStyle}>
                                  {formatAdminTimestamp(attempt.created_at, "—")}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Requested</span>
                                <span style={detailValueStyle}>
                                  {formatAdminTimestamp(attempt.requested_at, "—")}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Started</span>
                                <span style={detailValueStyle}>
                                  {formatAdminTimestamp(attempt.started_at, "—")}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Completed</span>
                                <span style={detailValueStyle}>
                                  {formatAdminTimestamp(attempt.completed_at, "—")}
                                </span>
                              </div>
                              {attempt.failure_code ? (
                                <div style={detailFieldStyle}>
                                  <span style={detailLabelStyle}>Failure code</span>
                                  <span style={detailValueStyle}>
                                    {formatDetailValue(attempt.failure_code)}
                                  </span>
                                </div>
                              ) : null}
                              {attempt.failure_message ? (
                                <div style={detailFieldStyle}>
                                  <span style={detailLabelStyle}>Failure message</span>
                                  <span style={detailValueStyle}>
                                    {formatDeliveryMetadataValue(attempt.failure_message)}
                                  </span>
                                </div>
                              ) : null}
                            </div>
                            {metaEntries.length > 0 ? (
                              <div style={adapterMetadataStyle}>
                                <div style={adapterMetadataTitleStyle}>Safe metadata</div>
                                <div style={timelineMetaGridStyle}>
                                  {metaEntries.map(([key, value]) => (
                                    <div key={key} style={detailFieldStyle}>
                                      <span style={detailLabelStyle}>{key}</span>
                                      <span style={detailValueStyle}>
                                        {formatDeliveryMetadataValue(value)}
                                      </span>
                                    </div>
                                  ))}
                                </div>
                              </div>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  ) : null}
                  <div style={timelineHeaderStyle}>Step Timeline</div>
                  {normalizeStepsLog(detailRecord.steps_log).length === 0 ? (
                    <p style={emptyTextStyle}>{getEmptyTimelineText(detailRecord.status)}</p>
                  ) : (
                    <div style={timelineListStyle}>
                      {normalizeStepsLog(detailRecord.steps_log).map((step, index) => {
                        const adapterResult = getStepAdapterResult(step);
                        const adapterMetadata = getAdapterMetadataEntries(adapterResult);

                        return (
                          <div key={`${step.step_id || step.step_index || index}`} style={timelineCardStyle}>
                            <div style={timelineCardHeaderStyle}>
                              <span style={timelineStepLabelStyle}>{formatStepLabel(step, index)}</span>
                              <span style={timelineActionStyle}>{getStepAction(step)}</span>
                              <span style={timelineStatusStyle}>{getStepEventLabel(step)}</span>
                            </div>
                            <div style={timelineMetaGridStyle}>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Mode</span>
                                <span style={detailValueStyle}>
                                  {formatDetailValue(step.mode || step.execution_mode || "simulation")}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Simulated</span>
                                <span style={detailValueStyle}>
                                  {formatFlagValue(getStepFlag(step, "simulated"))}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Executed</span>
                                <span style={detailValueStyle}>
                                  {formatFlagValue(getStepFlag(step, "executed"))}
                                </span>
                              </div>
                              {getStepApprovalValue(step, "approval_request_id") ? (
                                <div style={detailFieldStyle}>
                                  <span style={detailLabelStyle}>Approval Request ID</span>
                                  <span style={detailValueStyle}>
                                    {getStepApprovalValue(step, "approval_request_id")}
                                  </span>
                                </div>
                              ) : null}
                              {getStepApprovalValue(step, "approval_status") ? (
                                <div style={detailFieldStyle}>
                                  <span style={detailLabelStyle}>Approval Status</span>
                                  <span style={detailValueStyle}>
                                    {getStepApprovalValue(step, "approval_status")}
                                  </span>
                                </div>
                              ) : null}
                              {getStepApprovalValue(step, "risk_level") ? (
                                <div style={detailFieldStyle}>
                                  <span style={detailLabelStyle}>Risk Level</span>
                                  <span style={detailValueStyle}>
                                    {getStepApprovalValue(step, "risk_level")}
                                  </span>
                                </div>
                              ) : null}
                              {getStepSkipReason(step) ? (
                                <div style={detailFieldStyle}>
                                  <span style={detailLabelStyle}>Skip Reason</span>
                                  <span style={detailValueStyle}>{getStepSkipReason(step)}</span>
                                </div>
                              ) : null}
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Started</span>
                                <span style={detailValueStyle}>
                                  {formatAdminTimestamp(step.started_at, "—")}
                                </span>
                              </div>
                              <div style={detailFieldStyle}>
                                <span style={detailLabelStyle}>Completed</span>
                                <span style={detailValueStyle}>
                                  {formatAdminTimestamp(step.completed_at, "—")}
                                </span>
                              </div>
                            </div>
                            {getStepMessage(step) ? (
                              <p style={timelineTextStyle}>{getStepMessage(step)}</p>
                            ) : null}
                            {adapterResult ? (
                              <div style={adapterResultStyle}>
                                <div style={adapterResultTitleStyle}>Simulated adapter output</div>
                                <div style={timelineMetaGridStyle}>
                                  <div style={detailFieldStyle}>
                                    <span style={detailLabelStyle}>Adapter</span>
                                    <span style={detailValueStyle}>
                                      {formatAdapterFieldValue(adapterResult.adapter)}
                                    </span>
                                  </div>
                                  <div style={detailFieldStyle}>
                                    <span style={detailLabelStyle}>Adapter Action</span>
                                    <span style={detailValueStyle}>
                                      {formatAdapterFieldValue(adapterResult.action)}
                                    </span>
                                  </div>
                                  <div style={detailFieldStyle}>
                                    <span style={detailLabelStyle}>Success</span>
                                    <span style={detailValueStyle}>
                                      {formatAdapterFieldValue(adapterResult.success)}
                                    </span>
                                  </div>
                                  <div style={detailFieldStyle}>
                                    <span style={detailLabelStyle}>Simulated</span>
                                    <span style={detailValueStyle}>
                                      {formatAdapterFieldValue(adapterResult.simulated)}
                                    </span>
                                  </div>
                                  <div style={detailFieldStyle}>
                                    <span style={detailLabelStyle}>Executed</span>
                                    <span style={detailValueStyle}>
                                      {formatAdapterFieldValue(adapterResult.executed)}
                                    </span>
                                  </div>
                                </div>
                                {adapterResult.message ? (
                                  <p style={timelineTextStyle}>{adapterResult.message}</p>
                                ) : null}
                                {adapterMetadata.length > 0 ? (
                                  <div style={adapterMetadataStyle}>
                                    <div style={adapterMetadataTitleStyle}>Metadata</div>
                                    <div style={timelineMetaGridStyle}>
                                      {adapterMetadata.map(([key, value]) => (
                                        <div key={key} style={detailFieldStyle}>
                                          <span style={detailLabelStyle}>{key}</span>
                                          <span style={detailValueStyle}>
                                            {formatAdapterFieldValue(value)}
                                          </span>
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                ) : null}
                              </div>
                            ) : null}
                            {step.error_code ? (
                              <p style={timelineTextStyle}>Error code: {step.error_code}</p>
                            ) : null}
                            {getStepErrorText(step) ? (
                              <p style={timelineErrorTextStyle}>{getStepErrorText(step)}</p>
                            ) : null}
                            {getStepResultText(step) ? (
                              <pre style={timelineResultStyle}>{getStepResultText(step)}</pre>
                            ) : null}
                          </div>
                        );
                      })}
                    </div>
                  )}
                </>
              )}
              {detailKind === "definition" ? (
                <div style={jsonBlockWrapStyle}>
                  <div style={jsonBlockTitleStyle}>trigger_config</div>
                  <pre style={jsonPreStyle}>{JSON.stringify(detailRecord.trigger_config, null, 2)}</pre>
                </div>
              ) : detailKind === "execution" ? (
                <details style={jsonBlockWrapStyle}>
                  <summary style={jsonBlockTitleStyle}>Raw steps_log JSON</summary>
                  <pre style={jsonPreStyle}>{JSON.stringify(detailRecord.steps_log, null, 2)}</pre>
                </details>
              ) : null}
              {detailKind === "schedule" ? (
                <p style={emptyTextStyle}>
                  Schedule details are shown from allowlisted metadata fields only.
                </p>
              ) : null}
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

        {formMode && isSuperAdmin && (
          <div style={formPanelStyle}>
            <div style={formHeaderStyle}>
              <h3 style={formTitleStyle}>
                {formMode === "create" ? "Create New Playbook Definition" : "Edit Playbook Definition"}
              </h3>
              <button type="button" style={formCloseButtonStyle} onClick={handleCloseForm}>
                ✕
              </button>
            </div>

            <p style={formSubtitleStyle}>
              Definition management only. Execution is not enabled yet.
            </p>

            {formValidationError && <div style={errorStateStyle}>{formValidationError}</div>}
            {formSubmitError && <div style={errorStateStyle}>{formSubmitError}</div>}
            {formSubmitSuccess && <div style={successStateStyle}>{formSubmitSuccess}</div>}

            <div style={formFieldStyle}>
              <label style={formLabelStyle} htmlFor="form-id">ID {formMode === "create" ? "(required)" : "(read-only)"}</label>
              <input
                id="form-id"
                type="text"
                value={formId}
                onChange={(e) => setFormId(e.target.value)}
                disabled={formMode === "edit"}
                placeholder="e.g., block_and_notify"
                style={formInputStyle}
              />
            </div>

            <div style={formFieldStyle}>
              <label style={formLabelStyle} htmlFor="form-name">Name (required)</label>
              <input
                id="form-name"
                type="text"
                value={formName}
                onChange={(e) => setFormName(e.target.value)}
                placeholder="e.g., Block High-Risk IPs"
                style={formInputStyle}
              />
            </div>

            <div style={formFieldStyle}>
              <label style={formLabelStyle} htmlFor="form-description">Description (optional)</label>
              <input
                id="form-description"
                type="text"
                value={formDescription}
                onChange={(e) => setFormDescription(e.target.value)}
                placeholder="e.g., Auto-block IPs with reputation score > 80"
                style={formInputStyle}
              />
            </div>

            <div style={formFieldStyle}>
              <label style={formCheckboxLabelStyle} htmlFor="form-enabled">
                <input
                  id="form-enabled"
                  type="checkbox"
                  checked={formEnabled}
                  onChange={(e) => setFormEnabled(e.target.checked)}
                />
                <span>Enabled</span>
              </label>
            </div>

            <div style={formFieldStyle}>
              <label style={formLabelStyle} htmlFor="form-trigger">Trigger Config (JSON object)</label>
              <textarea
                id="form-trigger"
                value={formTriggerJson}
                onChange={(e) => setFormTriggerJson(e.target.value)}
                placeholder='{"alert_type": "password_spraying", "min_severity": "HIGH"}'
                style={formTextareaStyle}
              />
            </div>

            <div style={formFieldStyle}>
              <label style={formLabelStyle} htmlFor="form-steps">Steps (JSON array)</label>
              <textarea
                id="form-steps"
                value={formStepsJson}
                onChange={(e) => setFormStepsJson(e.target.value)}
                placeholder='[{"action": "monitor", "params": {}, "on_failure": "abort"}]'
                style={formTextareaStyle}
              />
            </div>

            <div style={formActionsStyle}>
              <button
                type="button"
                onClick={handleSubmitForm}
                disabled={formSubmitting}
                style={formSubmitButtonStyle}
              >
                {formSubmitting ? "Submitting…" : formMode === "create" ? "Create" : "Update"}
              </button>
              <button
                type="button"
                onClick={handleCloseForm}
                disabled={formSubmitting}
                style={formCancelButtonStyle}
              >
                Cancel
              </button>
            </div>
          </div>
        )}
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
  overflowWrap: "anywhere",
};

const statusSummaryStyle = {
  margin: "4px 0 14px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.25)",
  backgroundColor: "rgba(88, 166, 255, 0.08)",
  color: "#c9d1d9",
  fontSize: "13px",
};

const approvalNoticeStyle = {
  margin: "0 0 14px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(250, 204, 21, 0.35)",
  backgroundColor: "rgba(250, 204, 21, 0.08)",
  color: "#fde68a",
  fontSize: "13px",
  fontWeight: "700",
};

const deliveryEvidenceNoteStyle = {
  margin: "0 0 12px",
  fontSize: "12px",
  lineHeight: 1.45,
  color: "#8b949e",
};

const timelineHeaderStyle = {
  margin: "14px 0 8px",
  color: "#e6edf3",
  fontSize: "14px",
  fontWeight: "700",
};

const timelineListStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const timelineCardStyle = {
  padding: "12px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#050810",
};

const timelineCardHeaderStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  flexWrap: "wrap",
  marginBottom: "10px",
};

const timelineStepLabelStyle = {
  color: "#93c5fd",
  fontSize: "13px",
  fontWeight: "700",
};

const timelineActionStyle = {
  color: "#e6edf3",
  fontSize: "13px",
  fontWeight: "700",
  overflowWrap: "anywhere",
};

const timelineStatusStyle = {
  padding: "2px 8px",
  borderRadius: "999px",
  border: "1px solid rgba(139, 148, 158, 0.35)",
  color: "#c9d1d9",
  fontSize: "12px",
  fontWeight: "700",
  textTransform: "uppercase",
};

const timelineMetaGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(140px, 1fr))",
  gap: "8px",
};

const timelineTextStyle = {
  margin: "10px 0 0",
  color: "#c9d1d9",
  fontSize: "13px",
  lineHeight: 1.45,
  overflowWrap: "anywhere",
};

const timelineErrorTextStyle = {
  ...timelineTextStyle,
  color: "#fecaca",
};

const timelineResultStyle = {
  margin: "10px 0 0",
  padding: "10px",
  borderRadius: "6px",
  border: "1px solid #30363d",
  backgroundColor: "#0b1020",
  color: "#c9d1d9",
  fontSize: "12px",
  lineHeight: 1.45,
  maxHeight: "180px",
  overflow: "auto",
  whiteSpace: "pre-wrap",
  wordBreak: "break-word",
};

const adapterResultStyle = {
  margin: "10px 0 0",
  padding: "10px",
  borderRadius: "6px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(88, 166, 255, 0.08)",
};

const adapterResultTitleStyle = {
  color: "#bfdbfe",
  fontSize: "12px",
  fontWeight: "800",
  marginBottom: "8px",
  textTransform: "uppercase",
};

const adapterMetadataStyle = {
  marginTop: "10px",
};

const adapterMetadataTitleStyle = {
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  marginBottom: "6px",
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

const newDefinitionButtonStyle = {
  minHeight: "38px",
  padding: "8px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.14)",
  color: "#93c5fd",
  fontSize: "13px",
  fontWeight: "600",
  cursor: "pointer",
};

const actionButtonsWrapperStyle = {
  display: "flex",
  gap: "6px",
  flexWrap: "wrap",
};

const smallActionButtonStyle = {
  padding: "4px 8px",
  borderRadius: "4px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.08)",
  color: "#93c5fd",
  fontSize: "11px",
  fontWeight: "600",
  cursor: "pointer",
};

const actionErrorStyle = {
  marginTop: "6px",
  color: "#fecaca",
  fontSize: "12px",
  lineHeight: 1.35,
  overflowWrap: "anywhere",
};

const formPanelStyle = {
  marginTop: "20px",
  padding: "16px",
  borderRadius: "10px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.08)",
};

const formHeaderStyle = {
  display: "flex",
  alignItems: "center",
  justifyContent: "space-between",
  marginBottom: "12px",
};

const formTitleStyle = {
  margin: 0,
  fontSize: "16px",
  color: "#e6edf3",
};

const formCloseButtonStyle = {
  padding: "6px 10px",
  borderRadius: "6px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "14px",
  cursor: "pointer",
};

const formSubtitleStyle = {
  margin: "0 0 12px 0",
  fontSize: "13px",
  color: "#8b949e",
  fontStyle: "italic",
};

const formFieldStyle = {
  marginBottom: "12px",
};

const formLabelStyle = {
  display: "block",
  fontSize: "12px",
  color: "#8b949e",
  fontWeight: "700",
  marginBottom: "6px",
  textTransform: "uppercase",
};

const formCheckboxLabelStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  fontSize: "13px",
  color: "#e6edf3",
  cursor: "pointer",
};

const formInputStyle = {
  width: "100%",
  minHeight: "36px",
  padding: "8px 10px",
  borderRadius: "6px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  fontSize: "13px",
  fontFamily: "inherit",
  boxSizing: "border-box",
};

const formTextareaStyle = {
  width: "100%",
  minHeight: "120px",
  padding: "8px 10px",
  borderRadius: "6px",
  border: "1px solid #30363d",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  fontSize: "12px",
  fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace",
  boxSizing: "border-box",
  resize: "vertical",
};

const formActionsStyle = {
  display: "flex",
  gap: "10px",
  marginTop: "16px",
};

const formSubmitButtonStyle = {
  minHeight: "40px",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.14)",
  color: "#93c5fd",
  fontSize: "13px",
  fontWeight: "700",
  cursor: "pointer",
};

const formCancelButtonStyle = {
  minHeight: "40px",
  padding: "10px 14px",
  borderRadius: "8px",
  border: "1px solid #30363d",
  backgroundColor: "#161b22",
  color: "#c9d1d9",
  fontSize: "13px",
  fontWeight: "700",
  cursor: "pointer",
};

const successStateStyle = {
  marginBottom: "12px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(34, 197, 94, 0.35)",
  backgroundColor: "rgba(34, 197, 94, 0.08)",
  color: "#86efac",
  fontSize: "13px",
};

const noticeStyle = {
  marginBottom: "14px",
  padding: "10px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(88, 166, 255, 0.08)",
};

const metadataOnlyNoticeStyle = {
  margin: 0,
  color: "#c9d1d9",
  fontSize: "13px",
};
