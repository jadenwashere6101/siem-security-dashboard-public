import React, { useEffect, useRef, useState } from "react";
import { providerCostLabel, providerStatusLabel } from "../utils/aiDisplay";
import { getRepoAssistantStatus, sendRepoAssistantMessage } from "../services/repoAssistantService";

const initialState = {
  status: "idle",
  response: null,
  error: "",
  lastRequest: null,
};

function RepoArchitectureAssistantPanel({
  cardStyle = {},
  cardHeaderStyle = {},
  cardTitleStyle = {},
  cardSubtitleStyle = {},
}) {
  const [message, setMessage] = useState("");
  const [refresh, setRefresh] = useState(false);
  const [history, setHistory] = useState([]);
  const [status, setStatus] = useState({ loading: true, error: "", data: null });
  const [requestState, setRequestState] = useState(initialState);
  const controllerRef = useRef(null);
  const requestIdRef = useRef(0);

  useEffect(() => {
    const controller = new AbortController();
    setStatus({ loading: true, error: "", data: null });
    getRepoAssistantStatus({ signal: controller.signal })
      .then((data) => setStatus({ loading: false, error: "", data }))
      .catch((error) => {
        if (error.name !== "AbortError") {
          setStatus({ loading: false, error: error.message || "Failed to load repo assistant status.", data: null });
        }
      });
    return () => controller.abort();
  }, []);

  const cancelRequest = () => {
    requestIdRef.current += 1;
    if (controllerRef.current) {
      controllerRef.current.abort();
    }
    setRequestState((current) =>
      current.status === "loading" ? { ...current, status: "idle", response: null, error: "" } : current
    );
  };

  const submitRequest = async (overrideRequest = null) => {
    const trimmed = String(overrideRequest?.message ?? message).trim();
    if (!trimmed) return;
    cancelRequest();
    const controller = new AbortController();
    controllerRef.current = controller;
    const requestId = requestIdRef.current + 1;
    requestIdRef.current = requestId;
    const payload = overrideRequest || { message: trimmed, client_history: history, refresh };
    setRequestState({ status: "loading", response: null, error: "", lastRequest: payload });

    try {
      const response = await sendRepoAssistantMessage(payload, { signal: controller.signal });
      if (requestIdRef.current !== requestId) return;
      setRequestState({ status: "success", response, error: "", lastRequest: payload });
      setHistory((current) =>
        [
          ...current,
          { role: "user", content: payload.message },
          { role: "assistant", content: response.answer || response.error || "" },
        ].slice(-8)
      );
      setMessage("");
    } catch (error) {
      if (error.name === "AbortError") {
        if (requestIdRef.current !== requestId) return;
        setRequestState((current) => ({ ...current, status: "idle", error: "", response: null }));
        return;
      }
      if (requestIdRef.current !== requestId) return;
      setRequestState({
        status: "error",
        response: error.payload || null,
        error: error.message || "Repository assistant request failed.",
        lastRequest: payload,
      });
    } finally {
      if (controllerRef.current === controller && requestIdRef.current === requestId) {
        controllerRef.current = null;
      }
    }
  };

  const retry = () => {
    if (requestState.lastRequest) {
      submitRequest(requestState.lastRequest);
    }
  };

  const response = requestState.response || {};
  const citations = Array.isArray(response.citations) ? response.citations : [];
  const retrieval = response.retrieval || {};

  return (
    <section style={{ ...cardStyle, ...panelStyle }} aria-label="Repo-aware architecture assistant">
      <div style={{ ...cardHeaderStyle, ...headerStyle }}>
        <div>
          <p style={eyebrowStyle}>Super-admin developer tool</p>
          <h2 style={{ ...cardTitleStyle, marginBottom: "6px" }}>Repo Architecture Assistant</h2>
          <p style={{ ...cardSubtitleStyle, margin: 0 }}>
            Ask read-only questions about current source, policies, docs, tests, and active OpenSpecs.
          </p>
        </div>
        <div style={statusPillStyle}>
          {status.loading ? "Index status loading" : status.error || `${status.data?.indexed_files || 0} files indexed`}
        </div>
      </div>

      <form
        onSubmit={(event) => {
          event.preventDefault();
          submitRequest();
        }}
        style={formStyle}
      >
        <label htmlFor="repo-assistant-question" style={labelStyle}>
          Repository question
        </label>
        <textarea
          id="repo-assistant-question"
          value={message}
          onChange={(event) => setMessage(event.target.value)}
          rows={4}
          placeholder="Example: Where do detection rules live, and which policies govern deployment?"
          style={textareaStyle}
        />
        <div style={actionsStyle}>
          <label style={checkboxLabelStyle}>
            <input
              type="checkbox"
              checked={refresh}
              onChange={(event) => setRefresh(event.target.checked)}
            />
            Refresh index before answering
          </label>
          <button type="submit" disabled={!message.trim() || requestState.status === "loading"} style={primaryButtonStyle}>
            Ask Repo AI
          </button>
          {requestState.status === "loading" ? (
            <button type="button" onClick={cancelRequest} style={secondaryButtonStyle}>
              Cancel
            </button>
          ) : null}
        </div>
      </form>

      {requestState.status === "loading" ? (
        <div role="status" style={noticeStyle}>Retrieving cited repository evidence...</div>
      ) : null}

      {requestState.status === "error" ? (
        <div style={errorBoxStyle}>
          <p style={errorTextStyle}>{requestState.error}</p>
          <button type="button" onClick={retry} style={secondaryButtonStyle}>Retry</button>
        </div>
      ) : null}

      {requestState.status === "success" ? (
        <article style={answerCardStyle}>
          {response.insufficient_evidence ? (
            <p style={warningStyle}>{response.error || "Not enough current repository evidence was found."}</p>
          ) : null}
          {response.status === "grounding_failure" ? (
            <p style={warningStyle}>The model response was blocked because its citations did not match retrieved files.</p>
          ) : null}
          <div style={answerStyle}>{response.answer || response.error || "No answer was returned."}</div>
          <div style={metadataGridStyle}>
            <span>{providerStatusLabel(response.metadata)}</span>
            <span>{providerCostLabel(response.metadata)}</span>
            <span>
              Retrieval: {retrieval.matched_chunks || 0} chunks from {retrieval.indexed_files || 0} files
              {retrieval.refreshed ? " · refreshed" : ""}
            </span>
          </div>

          <h3 style={sectionHeadingStyle}>Citations</h3>
          {citations.length ? (
            <ul style={citationListStyle}>
              {citations.map((citation) => (
                <li key={`${citation.path}:${citation.line_start}-${citation.line_end}`} style={citationItemStyle}>
                  <code>{citation.path}:{citation.line_start}-{citation.line_end}</code>
                  <span>{`Tier ${citation.trust_tier} · ${citation.source_kind} · ${citation.label}`}</span>
                </li>
              ))}
            </ul>
          ) : (
            <p style={mutedStyle}>No validated citations were returned.</p>
          )}

          {Array.isArray(retrieval.excluded_matches) && retrieval.excluded_matches.length ? (
            <>
              <h3 style={sectionHeadingStyle}>Excluded matches</h3>
              <ul style={citationListStyle}>
                {retrieval.excluded_matches.map((match) => (
                  <li key={`${match.path}:${match.reason}`} style={citationItemStyle}>
                    <code>{match.path}</code>
                    <span>{match.reason}</span>
                  </li>
                ))}
              </ul>
            </>
          ) : null}

          <button type="button" onClick={() => setRequestState(initialState)} style={secondaryButtonStyle}>
            Dismiss
          </button>
        </article>
      ) : null}
    </section>
  );
}

const panelStyle = {
  display: "grid",
  gap: "18px",
  color: "#e2e8f0",
};
const headerStyle = {
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "space-between",
  gap: "16px",
  flexWrap: "wrap",
};
const eyebrowStyle = { margin: "0 0 6px", color: "#67e8f9", fontSize: "12px", letterSpacing: "0.12em", textTransform: "uppercase" };
const statusPillStyle = { border: "1px solid rgba(148, 163, 184, 0.35)", borderRadius: "999px", padding: "8px 12px", color: "#cbd5e1", fontSize: "12px" };
const formStyle = { display: "grid", gap: "10px" };
const labelStyle = { color: "#cbd5e1", fontSize: "13px", fontWeight: 700 };
const textareaStyle = {
  width: "100%",
  boxSizing: "border-box",
  borderRadius: "12px",
  border: "1px solid rgba(148, 163, 184, 0.35)",
  background: "#0f172a",
  color: "#e2e8f0",
  padding: "12px",
  resize: "vertical",
};
const actionsStyle = { display: "flex", alignItems: "center", gap: "10px", flexWrap: "wrap", justifyContent: "space-between" };
const checkboxLabelStyle = { display: "inline-flex", alignItems: "center", gap: "8px", color: "#cbd5e1", fontSize: "13px" };
const primaryButtonStyle = { border: "none", borderRadius: "10px", padding: "10px 14px", background: "#0ea5e9", color: "#fff", fontWeight: 700, cursor: "pointer" };
const secondaryButtonStyle = { ...primaryButtonStyle, background: "#334155" };
const noticeStyle = { border: "1px solid rgba(14, 165, 233, 0.35)", borderRadius: "12px", padding: "12px", color: "#bae6fd", background: "rgba(14, 165, 233, 0.08)" };
const errorBoxStyle = { border: "1px solid rgba(248, 113, 113, 0.35)", borderRadius: "12px", padding: "12px", background: "rgba(127, 29, 29, 0.25)" };
const errorTextStyle = { margin: "0 0 10px", color: "#fecaca" };
const warningStyle = { margin: "0 0 12px", color: "#fde68a" };
const answerCardStyle = { border: "1px solid rgba(148, 163, 184, 0.22)", borderRadius: "14px", padding: "16px", background: "rgba(15, 23, 42, 0.72)" };
const answerStyle = { whiteSpace: "pre-wrap", lineHeight: 1.65, fontSize: "14px" };
const metadataGridStyle = { display: "grid", gap: "4px", marginTop: "14px", color: "#94a3b8", fontSize: "12px" };
const sectionHeadingStyle = { margin: "18px 0 8px", fontSize: "14px", color: "#cbd5e1" };
const citationListStyle = { listStyle: "none", padding: 0, margin: 0, display: "grid", gap: "8px" };
const citationItemStyle = { display: "flex", flexWrap: "wrap", gap: "8px", justifyContent: "space-between", border: "1px solid rgba(148, 163, 184, 0.18)", borderRadius: "10px", padding: "8px", color: "#94a3b8", fontSize: "12px" };
const mutedStyle = { margin: 0, color: "#94a3b8" };

export default RepoArchitectureAssistantPanel;
