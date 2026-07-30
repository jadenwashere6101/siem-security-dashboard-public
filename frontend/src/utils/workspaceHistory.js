export const DEFAULT_WORKSPACE_HISTORY_LIMIT = 50;
export const SIEM_WORKSPACE_HISTORY_STATE_KEY = "siemWorkspaceHistory";

let entrySequence = 0;

function stableStringify(value) {
  if (value === null || typeof value !== "object") return JSON.stringify(value);
  if (Array.isArray(value)) return `[${value.map(stableStringify).join(",")}]`;
  return `{${Object.keys(value)
    .sort((a, b) => a.localeCompare(b))
    .map((key) => `${JSON.stringify(key)}:${stableStringify(value[key])}`)
    .join(",")}}`;
}

function isPrimitiveSerializable(value) {
  return value == null || ["string", "number", "boolean"].includes(typeof value);
}

export function sanitizeSnapshot(value) {
  if (isPrimitiveSerializable(value)) return value;
  if (Array.isArray(value)) {
    return value
      .filter((item) => isPrimitiveSerializable(item) || typeof item === "object")
      .map(sanitizeSnapshot)
      .filter((item) => item !== undefined);
  }
  if (typeof value !== "object") return undefined;
  return Object.fromEntries(
    Object.entries(value)
      .map(([key, item]) => [key, sanitizeSnapshot(item)])
      .filter(([, item]) => item !== undefined)
  );
}

export function normalizeWorkspaceHistoryEntry(entry = {}) {
  const sectionId = String(entry.sectionId || "").trim();
  if (!sectionId) return null;
  const state = sanitizeSnapshot(entry.state || {});
  const target = entry.target == null ? null : sanitizeSnapshot(entry.target);
  const scrollTop = Number.isFinite(Number(entry.scrollTop)) ? Math.max(0, Number(entry.scrollTop)) : null;
  entrySequence += 1;
  const normalized = {
    id: entry.id || `workspace-history-${Date.now()}-${entrySequence}`,
    sectionId,
    label: entry.label ? String(entry.label) : sectionId,
    target,
    state,
    scrollTop,
    createdAt: entry.createdAt || new Date().toISOString(),
  };
  return {
    ...normalized,
    dedupeKey: entry.dedupeKey || stableStringify({
      sectionId: normalized.sectionId,
      target: normalized.target,
      state: normalized.state,
    }),
  };
}

export function createWorkspaceHistory(initialEntry = null) {
  return {
    past: [],
    current: initialEntry ? normalizeWorkspaceHistoryEntry(initialEntry) : null,
    future: [],
  };
}

export function clearWorkspaceHistory(initialEntry = null) {
  return createWorkspaceHistory(initialEntry);
}

export function replaceCurrentWorkspaceHistoryEntry(history, entry) {
  const normalized = normalizeWorkspaceHistoryEntry(entry);
  if (!normalized) return history;
  return {
    past: Array.isArray(history?.past) ? history.past : [],
    current: normalized,
    future: Array.isArray(history?.future) ? history.future : [],
  };
}

export function pushWorkspaceHistoryEntry(history, entry, { limit = DEFAULT_WORKSPACE_HISTORY_LIMIT } = {}) {
  const normalized = normalizeWorkspaceHistoryEntry(entry);
  if (!normalized) return history || createWorkspaceHistory();
  const current = history?.current || null;
  if (current?.dedupeKey === normalized.dedupeKey) {
    return { past: history?.past || [], current: { ...normalized, id: current.id }, future: [] };
  }
  const past = current ? [...(history?.past || []), current] : [...(history?.past || [])];
  const boundedPast = past.slice(Math.max(0, past.length - Math.max(1, limit - 1)));
  return { past: boundedPast, current: normalized, future: [] };
}

export function updateCurrentWorkspaceHistoryEntry(history, patch) {
  if (!history?.current) return history;
  return replaceCurrentWorkspaceHistoryEntry(history, {
    ...history.current,
    ...patch,
    state: {
      ...(history.current.state || {}),
      ...patch?.state,
    },
  });
}

export function goBackWorkspaceHistory(history) {
  const past = Array.isArray(history?.past) ? history.past : [];
  if (!history?.current || past.length === 0) return { history, entry: null };
  const entry = past[past.length - 1];
  return {
    entry,
    history: {
      past: past.slice(0, -1),
      current: entry,
      future: [history.current, ...(history.future || [])],
    },
  };
}

export function goForwardWorkspaceHistory(history) {
  const future = Array.isArray(history?.future) ? history.future : [];
  if (!history?.current || future.length === 0) return { history, entry: null };
  const entry = future[0];
  return {
    entry,
    history: {
      past: [...(history.past || []), history.current],
      current: entry,
      future: future.slice(1),
    },
  };
}

export function restoreWorkspaceHistoryEntry(history, entryId) {
  if (!entryId || !history?.current) return { history, entry: null };
  if (history.current.id === entryId) return { history, entry: history.current };
  const allEntries = [...(history.past || []), history.current, ...(history.future || [])];
  const index = allEntries.findIndex((entry) => entry.id === entryId);
  if (index < 0) return { history, entry: null };
  const entry = allEntries[index];
  return {
    entry,
    history: {
      past: allEntries.slice(0, index),
      current: entry,
      future: allEntries.slice(index + 1),
    },
  };
}

export function canGoBackWorkspaceHistory(history) {
  return Boolean(history?.past?.length);
}

export function canGoForwardWorkspaceHistory(history) {
  return Boolean(history?.future?.length);
}

export function createWorkspaceBrowserState(entry) {
  return {
    [SIEM_WORKSPACE_HISTORY_STATE_KEY]: true,
    entryId: entry?.id || null,
  };
}

export function isWorkspaceBrowserState(state) {
  return Boolean(state?.[SIEM_WORKSPACE_HISTORY_STATE_KEY] && state.entryId);
}
