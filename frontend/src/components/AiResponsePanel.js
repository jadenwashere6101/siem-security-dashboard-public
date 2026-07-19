import React, { useState } from "react";
import { confirmAiAction, previewAiAction } from "../services/aiService";
import { providerCostLabel, providerStatusLabel, sourceCountLabel, toolUsageLabel } from "../utils/aiDisplay";

function AiResponsePanel({
  state,
  onDismiss,
  onRetry,
  onCancel,
  userRole,
}) {
  if (!state || state.status === "idle") return null;
  const busy = state.status === "loading";
  const response = state.response || {};
  const metadata = response.metadata;
  const context = response.context;
  const tools = response.tools;
  const draft = response.draft;
  const investigation = response.investigation;
  const toolCalls = Array.isArray(tools?.calls) ? tools.calls : [];

  return (
    <aside
      role="dialog"
      aria-modal="false"
      aria-label="AI assistant response"
      style={panelStyle}
    >
      <div style={headerStyle}>
        <div>
          <p style={eyebrowStyle}>Read-only AI assistant</p>
          <h2 style={titleStyle}>{state.title || "SIEM AI"}</h2>
        </div>
        <button type="button" onClick={onDismiss} aria-label="Dismiss AI response" style={iconButtonStyle}>
          ×
        </button>
      </div>

      {busy ? (
        <div style={bodyStyle}>
          <p style={mutedStyle}>Analyzing current SIEM context...</p>
          <button type="button" onClick={onCancel} style={secondaryButtonStyle}>Cancel</button>
        </div>
      ) : null}

      {state.status === "error" ? (
        <div style={bodyStyle}>
          <p style={errorStyle}>{state.error || "AI request failed."}</p>
          <button type="button" onClick={onRetry} style={primaryButtonStyle}>Retry</button>
        </div>
      ) : null}

      {state.status === "success" ? (
        <div style={bodyStyle}>
          {response.insufficient_context ? (
            <p style={warningStyle}>{response.error || "There was not enough SIEM context to answer safely."}</p>
          ) : null}
          {investigation ? <InvestigationReview investigation={investigation} /> : null}
          {draft ? <DraftReview draft={draft} response={response} userRole={userRole} /> : null}
          {!draft && !investigation ? (
            <div style={answerStyle}>{response.answer || response.error || "No AI answer was returned."}</div>
          ) : response.error && !investigation ? (
            <p style={warningStyle}>{response.error}</p>
          ) : null}
          {state.stale ? (
            <p style={warningStyle}>This answer may be stale because the visible SIEM context changed.</p>
          ) : null}
          <div style={metadataStyle}>
            <span>{providerStatusLabel(metadata)}</span>
            <span>{providerCostLabel(metadata)}</span>
            <span>{sourceCountLabel(context)}</span>
            <span>{toolUsageLabel(tools)}</span>
          </div>
          {tools?.used ? (
            <div style={toolBoxStyle} aria-label="Read-only AI tool evidence">
              <p style={toolTitleStyle}>Read-only investigation evidence</p>
              {toolCalls.length ? (
                <ul style={toolListStyle}>
                  {toolCalls.map((call, index) => (
                    <li key={`${call.tool_name || "tool"}-${index}`} style={toolItemStyle}>
                      <strong>{call.tool_name || "unknown_tool"}</strong>
                      <span>{call.status || "unknown"}</span>
                      <span>{Array.isArray(call.sources) ? call.sources.length : 0} sources</span>
                      {call.truncated ? <span>truncated</span> : null}
                    </li>
                  ))}
                </ul>
              ) : (
                <p style={mutedStyle}>No read-tool evidence was returned.</p>
              )}
            </div>
          ) : null}
        </div>
      ) : null}
    </aside>
  );
}

function InvestigationReview({ investigation }) {
  const steps = Array.isArray(investigation?.steps) ? investigation.steps : [];
  const recommendations = Array.isArray(investigation?.recommendations) ? investigation.recommendations : [];
  const correlations = Array.isArray(investigation?.correlations) ? investigation.correlations : [];
  const drafts = Array.isArray(investigation?.drafts) ? investigation.drafts : [];
  const observability = investigation?.observability || {};
  const routing = observability.routing_profile || {};
  const providerResponses = Array.isArray(observability.provider_responses) ? observability.provider_responses : [];

  return (
    <section aria-label="Guided AI investigation" style={investigationBoxStyle}>
      <div style={investigationHeaderStyle}>
        <div>
          <p style={investigationEyebrowStyle}>Guided investigation</p>
          <h3 style={investigationTitleStyle}>{formatDraftKey(investigation?.workflow_type || "advanced investigation")}</h3>
        </div>
        <span style={investigationStatusStyle}>{investigation?.status || "unknown"}</span>
      </div>
      <div style={draftLabelGridStyle}>
        <span>{investigation?.labels?.read_only === true ? "Read-only" : "Read state unknown"}</span>
        <span>{investigation?.labels?.writes_performed === false ? "No production change made" : "Write state unknown"}</span>
        <span>{investigation?.labels?.production_action_required_for_changes ? "Confirmation required for changes" : "Action boundary unknown"}</span>
      </div>
      {investigation?.summary ? <div style={answerStyle}>{investigation.summary}</div> : null}
      <div style={investigationMetaGridStyle}>
        <span>Routing: {routing.profile || "unknown"}</span>
        <span>Latency: {observability.total_latency_ms ?? 0} ms</span>
        <span>Tokens: {(observability.aggregate_prompt_tokens || 0) + (observability.aggregate_completion_tokens || 0)}</span>
        <span>Cost: {observability.aggregate_estimated_cost_usd == null ? "unavailable" : `$${Number(observability.aggregate_estimated_cost_usd).toFixed(4)}`}</span>
      </div>
      <div style={investigationSectionStyle}>
        <p style={toolTitleStyle}>Progress</p>
        <ol style={investigationStepListStyle}>
          {steps.map((step, index) => (
            <li key={`${step.step_type || "step"}-${index}`} style={investigationStepStyle}>
              <strong>{formatDraftKey(step.step_type || "step")}</strong>
              <span>{step.status || "unknown"}</span>
              {step.detail ? <small>{step.detail}</small> : null}
            </li>
          ))}
        </ol>
      </div>
      {correlations.length ? (
        <div style={investigationSectionStyle}>
          <p style={toolTitleStyle}>Source-cited evidence</p>
          <ul style={toolListStyle}>
            {correlations.slice(0, 8).map((item, index) => (
              <li key={`${item.source_path || "source"}-${index}`} style={toolItemStyle}>
                <strong>{item.source_type || "source"}</strong>
                <span>{item.source_path || "unknown source"}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {recommendations.length ? (
        <div style={investigationSectionStyle}>
          <p style={toolTitleStyle}>Recommended analyst next steps</p>
          <ul style={investigationRecommendationListStyle}>
            {recommendations.map((item, index) => (
              <li key={`${item.title || "recommendation"}-${index}`} style={investigationRecommendationStyle}>
                <strong>{item.title || "Recommendation"}</strong>
                <span>{item.recommendation || ""}</span>
                {item.requires_confirmation ? <small>Explicit confirmation required before any production change.</small> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {drafts.length ? (
        <div style={investigationSectionStyle}>
          <p style={toolTitleStyle}>Transient automatic draft</p>
          {drafts.map((draftResponse, index) => {
            const draft = draftResponse?.draft || {};
            return (
              <div key={`${draft.draft_type || "draft"}-${index}`} style={draftBoxStyle}>
                <p style={draftEyebrowStyle}>AI-generated draft</p>
                <h4 style={draftTitleStyle}>{draft.title || "AI draft"}</h4>
                <div style={draftLabelGridStyle}>
                  <span>{draft.labels?.persisted === false ? "Not saved" : "Saved state unknown"}</span>
                  <span>{draft.labels?.applied === false ? "Not applied" : "Apply state unknown"}</span>
                  <span>{draft.labels?.approval_required_before_apply ? "Review required before apply" : "Review state unknown"}</span>
                </div>
              </div>
            );
          })}
        </div>
      ) : null}
      {providerResponses.length ? (
        <div style={investigationSectionStyle}>
          <p style={toolTitleStyle}>Provider path</p>
          <ul style={toolListStyle}>
            {providerResponses.map((item, index) => (
              <li key={`${item.provider || "provider"}-${index}`} style={toolItemStyle}>
                <strong>{item.provider || "none"} / {item.model || "no model"}</strong>
                <span>{item.status || "unknown"}</span>
                {item.fallback_attempted ? <span>fallback: {item.fallback_reason || "attempted"}</span> : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}
      {investigation?.error ? <p style={warningStyle}>{investigation.error}</p> : null}
    </section>
  );
}

function DraftReview({ draft, response, userRole }) {
  const payload = draft?.payload && typeof draft.payload === "object" ? draft.payload : {};
  const validation = draft?.validation || {};
  const labels = draft?.labels || {};
  const entries = Object.entries(payload);
  const actionCandidate = buildActionCandidate(draft, response, userRole);
  const [actionState, setActionState] = useState({ status: "idle", preview: null, result: null, error: "" });
  const [acknowledged, setAcknowledged] = useState(false);

  const previewAction = async () => {
    if (!actionCandidate) return;
    setAcknowledged(false);
    setActionState({ status: "previewing", preview: null, result: null, error: "" });
    try {
      const previewResponse = await previewAiAction(actionCandidate.request);
      setActionState({
        status: "preview_ready",
        preview: previewResponse.preview,
        result: null,
        error: "",
      });
    } catch (error) {
      setActionState({
        status: "error",
        preview: null,
        result: error.payload?.result || null,
        error: error.message || "Unable to preview AI action.",
      });
    }
  };

  const confirmAction = async () => {
    if (!actionCandidate || !actionState.preview || !acknowledged || actionState.preview.stale) return;
    setActionState((current) => ({ ...current, status: "confirming", error: "" }));
    try {
      const confirmResponse = await confirmAiAction({
        ...actionCandidate.request,
        confirm: true,
        confirmation_token: actionState.preview.confirmation_token,
        payload_digest: actionState.preview.payload_digest,
        target_fingerprint: actionState.preview.target_fingerprint,
      });
      setActionState({
        status: "confirmed",
        preview: actionState.preview,
        result: confirmResponse.result,
        error: "",
      });
    } catch (error) {
      setActionState({
        status: "error",
        preview: actionState.preview,
        result: error.payload?.result || null,
        error: error.message || "Unable to confirm AI action.",
      });
    }
  };

  const rejectAction = () => {
    setAcknowledged(false);
    setActionState({
      status: "rejected",
      preview: actionState.preview,
      result: { outcome: "rejected", message: "Action rejected. No production change was made.", no_production_change: true },
      error: "",
    });
  };

  return (
    <section aria-label="AI-generated draft review" style={draftBoxStyle}>
      <div style={draftHeaderStyle}>
        <div>
          <p style={draftEyebrowStyle}>AI-generated draft</p>
          <h3 style={draftTitleStyle}>{draft?.title || "AI draft"}</h3>
        </div>
        <span style={draftStatusStyle}>{validation.valid ? "Schema valid" : "Needs review"}</span>
      </div>
      <div style={draftLabelGridStyle}>
        <span>{labels.read_only === true ? "Read-only" : "Review required"}</span>
        <span>{labels.persisted === false ? "Not saved" : "Saved state unknown"}</span>
        <span>{labels.applied === false ? "Not applied" : "Apply state unknown"}</span>
        <span>{labels.approval_required_before_apply === true ? "Review required before apply" : "Approval status unknown"}</span>
      </div>
      {validation.valid === false && Array.isArray(validation.errors) && validation.errors.length ? (
        <ul style={draftErrorListStyle}>
          {validation.errors.map((error, index) => (
            <li key={`${error}-${index}`}>{error}</li>
          ))}
        </ul>
      ) : null}
      {entries.length ? (
        <dl style={draftPayloadStyle}>
          {entries.map(([key, value]) => (
            <React.Fragment key={key}>
              <dt style={draftTermStyle}>{formatDraftKey(key)}</dt>
              <dd style={draftValueStyle}>{formatDraftValue(value)}</dd>
            </React.Fragment>
          ))}
        </dl>
      ) : (
        <p style={mutedStyle}>No valid draft payload was returned.</p>
      )}
      {actionCandidate ? (
        <section aria-label="Approval-gated AI action review" style={actionBoxStyle}>
          <p style={actionTitleStyle}>Approval-gated action available</p>
          <p style={mutedStyle}>{actionCandidate.label}</p>
          <button
            type="button"
            onClick={previewAction}
            disabled={actionState.status === "previewing" || actionState.status === "confirming"}
            style={secondaryButtonStyle}
          >
            {actionState.status === "previewing" ? "Previewing..." : "Preview exact action payload"}
          </button>
          {actionState.preview ? (
            <div style={actionPreviewStyle}>
              <p style={actionTitleStyle}>Exact payload before confirmation</p>
              <pre style={actionPreStyle}>{JSON.stringify(actionState.preview.payload, null, 2)}</pre>
              <p style={mutedStyle}>Targets: {(actionState.preview.target_resource_keys || []).join(", ")}</p>
              <p style={mutedStyle}>Required role: {actionState.preview.required_role}</p>
              {actionState.preview.stale ? (
                <p style={warningStyle}>This preview is stale. Regenerate it before confirming.</p>
              ) : null}
              {actionState.status !== "confirmed" && actionState.status !== "rejected" ? (
                <>
                  <label style={ackLabelStyle}>
                    <input
                      type="checkbox"
                      checked={acknowledged}
                      onChange={(event) => setAcknowledged(event.target.checked)}
                    />
                    I reviewed the exact payload and want to confirm this AI-assisted action.
                  </label>
                  <div style={actionButtonRowStyle}>
                    <button
                      type="button"
                      onClick={confirmAction}
                      disabled={!acknowledged || actionState.preview.stale || actionState.status === "confirming"}
                      style={primaryButtonStyle}
                    >
                      {actionState.status === "confirming" ? "Confirming..." : "Confirm action"}
                    </button>
                    <button type="button" onClick={rejectAction} style={secondaryButtonStyle}>
                      Reject action
                    </button>
                  </div>
                </>
              ) : null}
            </div>
          ) : null}
          {actionState.result ? (
            <div role="status" style={actionResultStyle}>
              <strong>{actionState.result.outcome || "unknown"}</strong>
              <span>{actionState.result.message || "No result message returned."}</span>
              {actionState.result.no_production_change ? <span>No production change made.</span> : null}
            </div>
          ) : null}
          {actionState.error ? <p style={errorStyle}>{actionState.error}</p> : null}
        </section>
      ) : null}
    </section>
  );
}

function buildActionCandidate(draft, response, userRole) {
  if (!draft || draft.validation?.valid !== true) return null;
  if (draft.draft_type !== "incident_note") return null;
  const incidentId = findSourceRecordId(response?.context, "incident");
  if (!incidentId) return null;
  const noteParts = [
    draft.payload?.summary,
    Array.isArray(draft.payload?.evidence) && draft.payload.evidence.length
      ? `Evidence: ${draft.payload.evidence.join("; ")}`
      : null,
    draft.payload?.uncertainty ? `Uncertainty: ${draft.payload.uncertainty}` : null,
    Array.isArray(draft.payload?.recommended_next_steps) && draft.payload.recommended_next_steps.length
      ? `Next steps: ${draft.payload.recommended_next_steps.join("; ")}`
      : null,
  ].filter(Boolean);
  const noteText = noteParts.join("\n\n").slice(0, 2000);
  if (!noteText || !["analyst", "super_admin"].includes(userRole)) return null;
  return {
    label: "Create an incident note from this reviewed draft. This requires preview and explicit confirmation.",
    request: {
      action_type: "add_incident_note",
      payload: {
        incident_id: incidentId,
        note_text: noteText,
      },
      idempotency_key: `ai-action-incident-note-${incidentId}-${simpleHash(noteText + (draft.generated_at || ""))}`,
      source_draft: {
        draft_type: draft.draft_type,
        generated_at: draft.generated_at,
        labels: draft.labels,
      },
    },
  };
}

function simpleHash(value) {
  let hash = 0;
  const text = String(value || "");
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
  }
  return hash.toString(16);
}

function findSourceRecordId(context, sourceType) {
  const sources = Array.isArray(context?.sources) ? context.sources : [];
  const source = sources.find((item) => item?.source_type === sourceType && Array.isArray(item.record_ids) && item.record_ids.length);
  const value = source?.record_ids?.[0];
  const parsed = Number.parseInt(value, 10);
  return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
}

function formatDraftKey(key) {
  return String(key || "").replace(/_/g, " ");
}

function formatDraftValue(value) {
  if (Array.isArray(value)) {
    return value.map((item, index) => (
      <span key={index} style={draftListItemStyle}>
        {typeof item === "object" ? JSON.stringify(item) : String(item)}
      </span>
    ));
  }
  if (value && typeof value === "object") {
    return JSON.stringify(value, null, 2);
  }
  return String(value ?? "");
}

const panelStyle = {
  position: "fixed",
  right: "18px",
  bottom: "88px",
  width: "min(440px, calc(100vw - 28px))",
  maxHeight: "70vh",
  overflowY: "auto",
  zIndex: 9997,
  border: "1px solid rgba(125, 211, 252, 0.35)",
  borderRadius: "18px",
  background: "linear-gradient(180deg, rgba(15, 23, 42, 0.98), rgba(2, 6, 23, 0.98))",
  color: "#e2e8f0",
  boxShadow: "0 24px 80px rgba(0, 0, 0, 0.45)",
};

const headerStyle = {
  display: "flex",
  justifyContent: "space-between",
  gap: "12px",
  padding: "16px 18px",
  borderBottom: "1px solid rgba(148, 163, 184, 0.2)",
};

const eyebrowStyle = { margin: 0, color: "#67e8f9", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase" };
const titleStyle = { margin: "4px 0 0", fontSize: "18px" };
const iconButtonStyle = { background: "transparent", color: "#e2e8f0", border: "none", fontSize: "24px", cursor: "pointer" };
const bodyStyle = { padding: "16px 18px" };
const mutedStyle = { margin: 0, color: "#94a3b8" };
const errorStyle = { margin: "0 0 12px", color: "#fca5a5" };
const warningStyle = { margin: "0 0 12px", color: "#fde68a" };
const answerStyle = { whiteSpace: "pre-wrap", lineHeight: 1.6, fontSize: "14px" };
const metadataStyle = { display: "grid", gap: "4px", marginTop: "14px", color: "#94a3b8", fontSize: "12px" };
const primaryButtonStyle = { border: "none", borderRadius: "8px", padding: "8px 12px", background: "#0ea5e9", color: "#fff", cursor: "pointer" };
const secondaryButtonStyle = { ...primaryButtonStyle, background: "#334155" };
const toolBoxStyle = { marginTop: "14px", border: "1px solid rgba(148, 163, 184, 0.22)", borderRadius: "12px", padding: "12px", background: "rgba(15, 23, 42, 0.68)" };
const toolTitleStyle = { margin: "0 0 8px", color: "#bae6fd", fontSize: "12px", fontWeight: 800 };
const toolListStyle = { listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "8px" };
const toolItemStyle = { display: "flex", flexWrap: "wrap", gap: "8px", justifyContent: "space-between", color: "#cbd5e1", fontSize: "12px" };
const investigationBoxStyle = { border: "1px solid rgba(125, 211, 252, 0.38)", borderRadius: "14px", padding: "14px", background: "rgba(8, 47, 73, 0.28)", display: "grid", gap: "12px" };
const investigationHeaderStyle = { display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "flex-start" };
const investigationEyebrowStyle = { margin: 0, color: "#67e8f9", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase", fontWeight: 800 };
const investigationTitleStyle = { margin: "3px 0 0", fontSize: "16px", color: "#e0f2fe", textTransform: "capitalize" };
const investigationStatusStyle = { border: "1px solid rgba(125, 211, 252, 0.45)", borderRadius: "999px", padding: "4px 8px", color: "#bae6fd", fontSize: "11px", fontWeight: 800, whiteSpace: "nowrap" };
const investigationMetaGridStyle = { display: "grid", gridTemplateColumns: "repeat(2, minmax(0, 1fr))", gap: "6px", color: "#cbd5e1", fontSize: "12px" };
const investigationSectionStyle = { display: "grid", gap: "8px" };
const investigationStepListStyle = { margin: 0, paddingLeft: "18px", display: "grid", gap: "8px" };
const investigationStepStyle = { color: "#dbeafe", fontSize: "12px", display: "grid", gap: "2px" };
const investigationRecommendationListStyle = { margin: 0, paddingLeft: "18px", display: "grid", gap: "8px" };
const investigationRecommendationStyle = { color: "#e2e8f0", fontSize: "12px", display: "grid", gap: "3px" };
const draftBoxStyle = { border: "1px solid rgba(34, 197, 94, 0.38)", borderRadius: "14px", padding: "14px", background: "rgba(6, 78, 59, 0.2)" };
const draftHeaderStyle = { display: "flex", justifyContent: "space-between", gap: "12px", alignItems: "flex-start", marginBottom: "10px" };
const draftEyebrowStyle = { margin: 0, color: "#86efac", fontSize: "11px", letterSpacing: "0.12em", textTransform: "uppercase", fontWeight: 800 };
const draftTitleStyle = { margin: "3px 0 0", fontSize: "16px", color: "#ecfdf5" };
const draftStatusStyle = { border: "1px solid rgba(134, 239, 172, 0.45)", borderRadius: "999px", padding: "4px 8px", color: "#bbf7d0", fontSize: "11px", fontWeight: 800, whiteSpace: "nowrap" };
const draftLabelGridStyle = { display: "flex", flexWrap: "wrap", gap: "6px", marginBottom: "12px", color: "#d1fae5", fontSize: "12px" };
const draftPayloadStyle = { display: "grid", gap: "10px", margin: 0 };
const draftTermStyle = { color: "#a7f3d0", fontSize: "12px", fontWeight: 800, textTransform: "capitalize" };
const draftValueStyle = { margin: "2px 0 0", color: "#e2e8f0", whiteSpace: "pre-wrap", lineHeight: 1.5 };
const draftListItemStyle = { display: "block", marginBottom: "3px" };
const draftErrorListStyle = { margin: "0 0 12px", paddingLeft: "18px", color: "#fde68a" };
const actionBoxStyle = { marginTop: "14px", border: "1px solid rgba(14, 165, 233, 0.38)", borderRadius: "12px", padding: "12px", background: "rgba(14, 116, 144, 0.14)" };
const actionTitleStyle = { margin: "0 0 8px", color: "#bae6fd", fontSize: "12px", fontWeight: 800 };
const actionPreviewStyle = { marginTop: "10px", display: "grid", gap: "8px" };
const actionPreStyle = { margin: 0, maxHeight: "180px", overflow: "auto", whiteSpace: "pre-wrap", color: "#e0f2fe", background: "rgba(2, 6, 23, 0.55)", borderRadius: "10px", padding: "10px", fontSize: "12px" };
const ackLabelStyle = { display: "flex", gap: "8px", alignItems: "flex-start", color: "#dbeafe", fontSize: "12px" };
const actionButtonRowStyle = { display: "flex", flexWrap: "wrap", gap: "8px" };
const actionResultStyle = { marginTop: "10px", display: "grid", gap: "4px", color: "#d1fae5", fontSize: "12px" };

export default AiResponsePanel;
