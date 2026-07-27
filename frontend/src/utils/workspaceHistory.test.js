import {
  canGoBackWorkspaceHistory,
  canGoForwardWorkspaceHistory,
  clearWorkspaceHistory,
  createWorkspaceBrowserState,
  createWorkspaceHistory,
  goBackWorkspaceHistory,
  goForwardWorkspaceHistory,
  isWorkspaceBrowserState,
  normalizeWorkspaceHistoryEntry,
  pushWorkspaceHistoryEntry,
  restoreWorkspaceHistoryEntry,
  sanitizeSnapshot,
  updateCurrentWorkspaceHistoryEntry,
} from "./workspaceHistory";

test("normalizes entries and strips non-serializable snapshot values", () => {
  const entry = normalizeWorkspaceHistoryEntry({
    sectionId: " dashboard ",
    state: {
      selectedAlertId: 7,
      fn: () => {},
      nested: { ok: true, bad: Symbol("x") },
    },
    scrollTop: "42",
  });

  expect(entry.sectionId).toBe("dashboard");
  expect(entry.state).toEqual({ selectedAlertId: 7, nested: { ok: true } });
  expect(entry.scrollTop).toBe(42);
  expect(entry.dedupeKey).toContain("dashboard");
});

test("rejects entries without a section id", () => {
  expect(normalizeWorkspaceHistoryEntry({ state: { selectedAlertId: 1 } })).toBeNull();
});

test("pushes bounded history and clears forward stack", () => {
  let history = createWorkspaceHistory({ sectionId: "dashboard" });
  history = pushWorkspaceHistoryEntry(history, { sectionId: "soar-incidents" }, { limit: 3 });
  history = pushWorkspaceHistoryEntry(history, { sectionId: "response-registry" }, { limit: 3 });
  history = pushWorkspaceHistoryEntry(history, { sectionId: "recon-history" }, { limit: 3 });

  expect(history.current.sectionId).toBe("recon-history");
  expect(history.past.map((entry) => entry.sectionId)).toEqual(["soar-incidents", "response-registry"]);
  expect(history.future).toEqual([]);
});

test("dedupes consecutive equivalent destinations", () => {
  let history = createWorkspaceHistory({ sectionId: "dashboard" });
  history = pushWorkspaceHistoryEntry(history, { sectionId: "dashboard" });

  expect(history.past).toHaveLength(0);
  expect(history.current.sectionId).toBe("dashboard");
});

test("goes back and forward while preserving stacks", () => {
  let history = createWorkspaceHistory({ sectionId: "dashboard" });
  history = pushWorkspaceHistoryEntry(history, { sectionId: "soar-incidents" });
  history = pushWorkspaceHistoryEntry(history, { sectionId: "response-registry" });

  const back = goBackWorkspaceHistory(history);
  expect(back.entry.sectionId).toBe("soar-incidents");
  expect(canGoForwardWorkspaceHistory(back.history)).toBe(true);

  const forward = goForwardWorkspaceHistory(back.history);
  expect(forward.entry.sectionId).toBe("response-registry");
  expect(canGoBackWorkspaceHistory(forward.history)).toBe(true);
});

test("restores an arbitrary entry id from combined stacks", () => {
  let history = createWorkspaceHistory({ sectionId: "dashboard" });
  history = pushWorkspaceHistoryEntry(history, { sectionId: "soar-incidents" });
  history = pushWorkspaceHistoryEntry(history, { sectionId: "response-registry" });
  const dashboardId = history.past[0].id;

  const restored = restoreWorkspaceHistoryEntry(history, dashboardId);
  expect(restored.entry.sectionId).toBe("dashboard");
  expect(restored.history.current.id).toBe(dashboardId);
  expect(restored.history.future.map((entry) => entry.sectionId)).toEqual([
    "soar-incidents",
    "response-registry",
  ]);
});

test("updates current entry without creating stack entries", () => {
  const history = updateCurrentWorkspaceHistoryEntry(
    createWorkspaceHistory({ sectionId: "dashboard", state: { searchTerm: "" } }),
    { state: { searchTerm: "vpn" }, scrollTop: 300 }
  );

  expect(history.past).toHaveLength(0);
  expect(history.current.state.searchTerm).toBe("vpn");
  expect(history.current.scrollTop).toBe(300);
});

test("clears history to an optional initial entry", () => {
  const history = clearWorkspaceHistory({ sectionId: "dashboard" });
  expect(history.past).toEqual([]);
  expect(history.current.sectionId).toBe("dashboard");
  expect(history.future).toEqual([]);
});

test("identifies SIEM-owned browser history state", () => {
  const state = createWorkspaceBrowserState({ id: "entry-1" });
  expect(isWorkspaceBrowserState(state)).toBe(true);
  expect(isWorkspaceBrowserState({ entryId: "entry-1" })).toBe(false);
});

test("sanitizeSnapshot keeps arrays of lightweight values", () => {
  expect(sanitizeSnapshot({ expanded: [1, "2", null, () => {}] })).toEqual({
    expanded: [1, "2", null],
  });
});
