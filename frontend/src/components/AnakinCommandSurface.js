import React, { useEffect, useMemo, useRef, useState } from "react";

import { WORKFLOW_TASK_DESCRIPTIONS } from "./AnakinWorkflowControls";
import "./AnakinCommandSurface.css";

const TASK_WORKFLOWS = new Set([
  "quick_explain",
  "deep_investigate",
  "decision_support",
  "generate_artifact",
]);

const TASK_LABELS = {
  quick_explain: "Explain this alert",
  deep_investigate: "Investigate further",
  decision_support: "Recommend next action",
  generate_artifact: "Draft an analyst artifact",
};

function AnakinCommandSurface({
  open: controlledOpen,
  onOpen,
  onClose,
  commands = [],
  context,
  onExecute,
  disabled = false,
  state = null,
  thread = null,
  turns = [],
  threadLoading = false,
  threadError = "",
  activeRequest = null,
  onRetry,
  onCancel,
  onChooseWorkflow,
  onReset,
  onNewThread,
  triggerAriaLabel = "Ask Anakin",
}) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [question, setQuestion] = useState("");
  const [rememberOpen, setRememberOpen] = useState(false);
  const triggerRef = useRef(null);
  const closeRef = useRef(null);
  const transcriptRef = useRef(null);
  const isControlled = controlledOpen !== undefined;
  const open = isControlled ? controlledOpen : internalOpen;
  const busy = state?.status === "loading" || Boolean(activeRequest && !activeRequest.terminal);

  const shortcutCommands = useMemo(
    () => commands.filter((command) => TASK_WORKFLOWS.has(command.workflow) && !command.disabled),
    [commands]
  );

  useEffect(() => {
    if (!open) return undefined;
    const previousFocus = document.activeElement;
    const fallbackTrigger = triggerRef.current;
    const onKeyDown = (event) => {
      if (event.key !== "Escape") return;
      event.preventDefault();
      closeSurface();
    };
    window.addEventListener("keydown", onKeyDown);
    window.requestAnimationFrame?.(() => closeRef.current?.focus());
    return () => {
      window.removeEventListener("keydown", onKeyDown);
      window.requestAnimationFrame?.(() => previousFocus?.focus?.() || fallbackTrigger?.focus?.());
    };
    // closeSurface is intentionally represented by the stable controlled callbacks.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [open, onClose]);

  useEffect(() => {
    if (!open || !transcriptRef.current) return;
    transcriptRef.current.scrollTop = transcriptRef.current.scrollHeight;
  }, [activeRequest, open, state?.status, turns]);

  const setOpen = (nextOpen) => {
    if (!isControlled) setInternalOpen(nextOpen);
    if (nextOpen) onOpen?.(triggerRef.current);
    else {
      onClose?.();
      window.setTimeout(() => triggerRef.current?.focus?.(), 0);
    }
  };

  const closeSurface = () => setOpen(false);

  const execute = (command, runtime = {}) => {
    if (typeof onExecute !== "function" || command?.disabled || disabled) return;
    onExecute(command, { ...runtime, threadId: thread?.thread_id || null });
  };

  const submitQuestion = () => {
    const prompt = question.trim();
    if (!prompt || busy || disabled) return;
    execute(
      {
        id: "anakin.ask-freeform",
        label: "Ask Anakin",
        group: "Anakin",
        intent: "ask",
        workflow: "auto",
        readOnly: true,
      },
      { question: prompt }
    );
    setQuestion("");
  };

  const activeEntity = thread?.focus_state?.active || thread?.primary_entity || null;
  const contextLabel = formatEntity(activeEntity, context);
  const remembered = rememberedState(thread);

  return (
    <div className="anakin-shell" data-anakin-surface="canonical">
      {!open ? (
        <button
          type="button"
          ref={triggerRef}
          onClick={() => setOpen(true)}
          disabled={disabled}
          aria-label={triggerAriaLabel}
          aria-expanded="false"
          aria-controls="anakin-conversation-panel"
          className="anakin-trigger"
        >
          Ask Anakin
        </button>
      ) : null}

      {open ? (
        <aside
          id="anakin-conversation-panel"
          role="dialog"
          aria-modal="false"
          aria-label="Anakin conversation"
          className="anakin-conversation-panel"
        >
          <header className="anakin-header">
            <div className="anakin-header-copy">
              <span className="anakin-eyebrow">Anakin</span>
              <h2>Ask Anakin</h2>
              <div className="anakin-context-row">
                <span className="anakin-context-chip">{contextLabel}</span>
                {busy ? <span className="anakin-status-chip">Working</span> : null}
              </div>
            </div>
            <div className="anakin-header-actions">
              <button type="button" onClick={onNewThread} disabled={busy || !thread} className="anakin-text-button">
                New thread
              </button>
              <button type="button" onClick={onReset} disabled={busy || !thread} className="anakin-text-button">
                Reset
              </button>
              <button ref={closeRef} type="button" onClick={closeSurface} aria-label="Close Anakin conversation" className="anakin-icon-button">
                ×
              </button>
            </div>
          </header>

          <div ref={transcriptRef} className="anakin-transcript" aria-live="polite">
            {threadLoading ? <StatusMessage>Restoring this conversation…</StatusMessage> : null}
            {threadError ? <StatusMessage tone="error">{threadError}</StatusMessage> : null}
            {!threadLoading && !threadError && turns.length === 0 && state?.status === "idle" ? (
              <div className="anakin-empty-state">
                <strong>What needs a closer look?</strong>
                <p>Ask about the selected alert, IP, incident, or current dashboard activity.</p>
              </div>
            ) : null}
            {turns.map((turn) => <ConversationTurn key={turn.turn_id || turn.id || turn.sequence} turn={turn} />)}
            <TransientResponse
              state={state}
              turns={turns}
              onRetry={onRetry}
              onCancel={onCancel}
              onChooseWorkflow={onChooseWorkflow}
            />
          </div>

          <section className="anakin-compose" aria-label="Ask a follow-up">
            <div className="anakin-shortcuts" aria-label="Optional Anakin shortcuts">
              {shortcutCommands.map((command) => (
                <button
                  key={command.id}
                  type="button"
                  onClick={() => execute(command)}
                  disabled={busy || disabled}
                  title={command.description || WORKFLOW_TASK_DESCRIPTIONS[command.workflow]}
                  className="anakin-shortcut"
                >
                  {TASK_LABELS[command.workflow] || command.label}
                </button>
              ))}
            </div>
            <form
              onSubmit={(event) => {
                event.preventDefault();
                submitQuestion();
              }}
              className="anakin-form"
            >
              <label htmlFor="anakin-question">Ask Anakin</label>
              <textarea
                id="anakin-question"
                value={question}
                onChange={(event) => setQuestion(event.target.value)}
                placeholder="Ask about the selected alert, IP, incident, or current dashboard activity"
                rows={3}
                disabled={disabled}
              />
              <button type="submit" disabled={busy || disabled || !question.trim()} aria-label="Submit Ask Anakin question" className="anakin-send-button">
                Ask
              </button>
            </form>
            <button
              type="button"
              className="anakin-memory-toggle"
              onClick={() => setRememberOpen((current) => !current)}
              aria-expanded={rememberOpen}
            >
              What Anakin remembers
            </button>
            {rememberOpen ? <RememberedState items={remembered} /> : null}
          </section>
        </aside>
      ) : null}
    </div>
  );
}

function ConversationTurn({ turn }) {
  const assistant = turn.role === "assistant";
  const artifact = turn.assertion_type === "artifact_preview" || turn.artifact_safety?.preview_only;
  return (
    <article className={`anakin-turn ${assistant ? "anakin-turn-assistant" : "anakin-turn-user"}`} data-turn-sequence={turn.sequence}>
      <div className="anakin-turn-heading">
        <strong>{assistant ? "Anakin" : "You"}</strong>
        {turn.workflow ? <span>{TASK_LABELS[turn.workflow] || "Analysis"}</span> : null}
      </div>
      <p>{safeText(turn.content) || "This turn did not include displayable text."}</p>
      {turn.lifecycle_status && !["completed", "recorded"].includes(turn.lifecycle_status) ? (
        <small>{lifecycleLabel(turn.lifecycle_status)}</small>
      ) : null}
      {artifact ? <ArtifactSafety /> : null}
    </article>
  );
}

function TransientResponse({ state, turns, onRetry, onCancel, onChooseWorkflow }) {
  if (!state || state.status === "idle") return null;
  const response = state.response || {};
  const conversationTurnId = response.conversation?.assistant_turn?.turn_id;
  if (conversationTurnId && turns.some((turn) => turn.turn_id === conversationTurnId)) return null;
  if (state.status === "loading") {
    return (
      <div className="anakin-progress" role="status">
        <span className="anakin-progress-dot" aria-hidden="true" />
        <span>{progressLabel(response)}</span>
        {onCancel ? <button type="button" onClick={onCancel}>Stop waiting</button> : null}
      </div>
    );
  }
  if (state.status === "error") {
    return (
      <div className="anakin-error" role="alert">
        <p>{state.error || "Anakin could not complete this question."}</p>
        {onRetry ? <button type="button" onClick={onRetry}>Retry</button> : null}
      </div>
    );
  }
  const answer = responseText(response);
  const allowed = Array.isArray(response?.result?.allowed_workflows) ? response.result.allowed_workflows : [];
  return (
    <article className="anakin-turn anakin-turn-assistant">
      <div className="anakin-turn-heading"><strong>Anakin</strong></div>
      <p>{answer || "Anakin needs more context before it can answer safely."}</p>
      {allowed.length ? (
        <div className="anakin-clarification-actions" aria-label="Choose an analysis task">
          {allowed.map((workflow) => (
            <button key={workflow} type="button" onClick={() => onChooseWorkflow?.(workflow)}>
              {TASK_LABELS[workflow] || "Ask Anakin"}
            </button>
          ))}
        </div>
      ) : null}
      {response.draft || response.workflow === "generate_artifact" ? <ArtifactSafety /> : null}
      {state.stale ? <small>This result belongs to a previously selected context.</small> : null}
    </article>
  );
}

function ArtifactSafety() {
  return (
    <div className="anakin-artifact-safety" aria-label="Artifact preview safety">
      <span>Preview only</span>
      <span>Not applied</span>
      <span>Not persisted as an operational record</span>
      <span>Approval required before apply</span>
    </div>
  );
}

function RememberedState({ items }) {
  return (
    <div className="anakin-memory" role="region" aria-label="What Anakin remembers">
      {items.length ? items.map((item) => <p key={item.label}><strong>{item.label}:</strong> {item.value}</p>) : (
        <p>No conclusions or unresolved questions have been recorded in this thread yet.</p>
      )}
    </div>
  );
}

function StatusMessage({ children, tone = "neutral" }) {
  return <p className={`anakin-message anakin-message-${tone}`} role={tone === "error" ? "alert" : "status"}>{children}</p>;
}

function rememberedState(thread) {
  if (!thread) return [];
  const state = thread.state || {};
  const items = [];
  const active = thread.focus_state?.active || thread.primary_entity;
  if (active?.type && active?.id) items.push({ label: "Active context", value: formatEntity(active) });
  const summary = safeText(state.compact_summary || thread.summary);
  if (summary) items.push({ label: "Current conclusion", value: summary });
  if (Array.isArray(state.unresolved_questions) && state.unresolved_questions.length) {
    items.push({ label: "Open questions", value: `${state.unresolved_questions.length}` });
  }
  if (Array.isArray(state.corrections) && state.corrections.length) {
    items.push({ label: "Analyst corrections", value: `${state.corrections.length}` });
  }
  return items;
}

function responseText(response) {
  const candidates = [
    response.answer,
    response.result?.answer,
    response.investigation?.summary,
    response.result?.summary,
    response.draft?.content,
    response.error,
  ];
  return candidates.map(safeText).find(Boolean) || "";
}

function progressLabel(response) {
  const workflow = response.workflow;
  if (workflow === "deep_investigate") return "Correlating evidence and checking competing explanations…";
  if (workflow === "decision_support") return "Evaluating the safest next action…";
  if (workflow === "generate_artifact") return "Drafting a preview for analyst review…";
  return "Reviewing the available context…";
}

function lifecycleLabel(value) {
  const labels = {
    queued: "Waiting to begin",
    running: "In progress",
    failed: "Did not complete",
    partial: "Completed with evidence gaps",
    degraded: "Completed with limited evidence",
  };
  return labels[value] || "Saved in this conversation";
}

function formatEntity(entity, context) {
  if (entity?.type && entity?.id) {
    const labels = {
      alert: "Alert",
      incident: "Incident",
      source_ip: "Source IP",
      recon_activity: "Recon activity",
      response_registry: "Response indicator",
      investigation: "Investigation",
      dashboard: "Dashboard activity",
      general: "Current workspace",
    };
    const label = labels[entity.type] || "Current context";
    if (["dashboard", "general"].includes(entity.type)) return label;
    return `${label} ${entity.id}`;
  }
  const activeSection = context?.workspace?.activeSection;
  return activeSection ? `${String(activeSection).replaceAll("-", " ")} context` : "Current workspace";
}

function safeText(value) {
  return typeof value === "string" || typeof value === "number" ? String(value).trim() : "";
}

export default AnakinCommandSurface;
