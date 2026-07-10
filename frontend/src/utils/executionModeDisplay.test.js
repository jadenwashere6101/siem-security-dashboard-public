import { executionModeLabel, executionModeNoun, normalizeExecutionMode } from "./executionModeDisplay";

test.each([
  [{ mode: "real" }, "real", "real execution", "Real"],
  [{ execution_mode: "simulation" }, "simulation", "simulation", "Simulation"],
  [{ mode: "read-only" }, "read_only", "read-only execution", "Read-only"],
  [{ mode: "future" }, "unknown", "execution", "Unknown"],
  [{}, "unknown", "execution", "Unknown"],
])("normalizes execution presentation conservatively", (record, mode, noun, label) => {
  const normalized = normalizeExecutionMode(record.mode, record.execution_mode);
  expect(normalized).toBe(mode);
  expect(executionModeNoun(normalized)).toBe(noun);
  expect(executionModeLabel(normalized)).toBe(label);
});
