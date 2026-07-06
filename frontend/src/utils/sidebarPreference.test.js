import { readStoredSidebarCollapsed, writeStoredSidebarCollapsed } from "./sidebarPreference";

beforeEach(() => {
  window.localStorage.clear();
});

test("returns null when no preference has been stored", () => {
  expect(readStoredSidebarCollapsed()).toBeNull();
});

test("round-trips a stored true value", () => {
  writeStoredSidebarCollapsed(true);

  expect(readStoredSidebarCollapsed()).toBe(true);
});

test("round-trips a stored false value", () => {
  writeStoredSidebarCollapsed(false);

  expect(readStoredSidebarCollapsed()).toBe(false);
});

test("returns null for malformed JSON in storage", () => {
  window.localStorage.setItem("siem_sidebar_collapsed", "{not-json");

  expect(readStoredSidebarCollapsed()).toBeNull();
});

test("returns null when the stored value is not a strict boolean", () => {
  window.localStorage.setItem("siem_sidebar_collapsed", JSON.stringify("collapsed"));

  expect(readStoredSidebarCollapsed()).toBeNull();
});

test("returns null instead of throwing when storage access fails on read", () => {
  const getItemSpy = jest
    .spyOn(window.localStorage.__proto__, "getItem")
    .mockImplementation(() => {
      throw new Error("storage unavailable");
    });

  expect(() => readStoredSidebarCollapsed()).not.toThrow();
  expect(readStoredSidebarCollapsed()).toBeNull();

  getItemSpy.mockRestore();
});

test("does not throw when storage access fails on write", () => {
  const setItemSpy = jest
    .spyOn(window.localStorage.__proto__, "setItem")
    .mockImplementation(() => {
      throw new Error("storage unavailable");
    });

  expect(() => writeStoredSidebarCollapsed(true)).not.toThrow();

  setItemSpy.mockRestore();
});
