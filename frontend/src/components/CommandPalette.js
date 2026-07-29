import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { assertReadOnlyPaletteCommand, groupCommands } from "../utils/anakinCommandRegistry";
import { theme } from "../theme";

function CommandPalette({ commands = [], objects = [], onExecute, disabled = false }) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [activeIndex, setActiveIndex] = useState(0);
  const inputRef = useRef(null);
  const returnFocusRef = useRef(null);

  const results = useMemo(() => {
    const normalizedQuery = query.trim().toLowerCase();
    const commandResults = commands
      .filter(assertReadOnlyPaletteCommand)
      .filter((command) => matches(command, normalizedQuery));
    const objectResults = objects
      .filter((object) => matches(object, normalizedQuery))
      .map((object) => ({
        ...object,
        group: object.group || "Objects",
        intent: "lookup",
        readOnly: true,
      }));
    return [...commandResults, ...objectResults].slice(0, 30);
  }, [commands, objects, query]);

  const groupedResults = useMemo(() => groupCommands(results), [results]);

  const execute = useCallback((command) => {
    if (disabled || !assertReadOnlyPaletteCommand(command)) return;
    onExecute?.(command);
    setOpen(false);
    setQuery("");
    window.requestAnimationFrame?.(() => returnFocusRef.current?.focus?.());
  }, [disabled, onExecute]);

  useEffect(() => {
    const onKeyDown = (event) => {
      const isPaletteShortcut = (event.metaKey || event.ctrlKey) && event.key.toLowerCase() === "k";
      if (isPaletteShortcut) {
        event.preventDefault();
        returnFocusRef.current = document.activeElement;
        setOpen(true);
        setActiveIndex(0);
        window.requestAnimationFrame?.(() => inputRef.current?.focus());
        return;
      }
      if (!open) return;
      if (event.key === "Escape") {
        event.preventDefault();
        setOpen(false);
        setQuery("");
        window.requestAnimationFrame?.(() => returnFocusRef.current?.focus?.());
      } else if (event.key === "ArrowDown") {
        event.preventDefault();
        setActiveIndex((current) => Math.min(current + 1, Math.max(0, results.length - 1)));
      } else if (event.key === "ArrowUp") {
        event.preventDefault();
        setActiveIndex((current) => Math.max(0, current - 1));
      } else if (event.key === "Enter" && results[activeIndex]) {
        event.preventDefault();
        execute(results[activeIndex]);
      }
    };
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [activeIndex, execute, open, results]);

  if (!open) return null;

  let flatIndex = 0;
  return (
    <div role="dialog" aria-label="Command palette" style={backdropStyle}>
      <div style={paletteStyle}>
        <label htmlFor="command-palette-search" style={labelStyle}>Command palette</label>
        <input
          id="command-palette-search"
          ref={inputRef}
          value={query}
          onChange={(event) => {
            setQuery(event.target.value);
            setActiveIndex(0);
          }}
          placeholder="Navigate, look up objects, filter, or Ask Anakin..."
          style={inputStyle}
        />
        <div role="listbox" aria-label="Command palette results" style={resultsStyle}>
          {results.length === 0 ? <p style={emptyStyle}>No read-only commands or objects found.</p> : null}
          {groupedResults.map((group) => (
            <div key={group.group}>
              <p style={groupStyle}>{group.group}</p>
              {group.items.map((command) => {
                const index = flatIndex;
                flatIndex += 1;
                return (
                  <button
                    key={command.id}
                    type="button"
                    role="option"
                    aria-label={command.label}
                    aria-selected={index === activeIndex}
                    onMouseEnter={() => setActiveIndex(index)}
                    onClick={() => execute(command)}
                    style={{
                      ...resultStyle,
                      ...(index === activeIndex ? activeResultStyle : null),
                    }}
                  >
                    <span style={resultLabelStyle}>{command.label}</span>
                    <span style={resultMetaStyle}>{command.description || command.meta || command.intent}</span>
                  </button>
                );
              })}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function matches(item, query) {
  if (!query) return true;
  return [item.label, item.description, item.meta, item.intent, ...(item.keywords || [])]
    .filter(Boolean)
    .join(" ")
    .toLowerCase()
    .includes(query);
}

const backdropStyle = {
  position: "fixed",
  inset: 0,
  zIndex: 9998,
  backgroundColor: "rgba(13, 17, 23, 0.68)",
  display: "flex",
  alignItems: "flex-start",
  justifyContent: "center",
  padding: "72px 16px 16px",
};
const paletteStyle = {
  width: "min(760px, 100%)",
  border: `1px solid ${theme.color.aiBorder}`,
  borderRadius: theme.radius.lg,
  backgroundColor: theme.color.bgRaised,
  boxShadow: theme.shadow.overlay,
  padding: theme.spacing.lg,
};
const labelStyle = { display: "block", marginBottom: "8px", color: theme.color.aiSoft, fontSize: "12px", fontWeight: 900, textTransform: "uppercase" };
const inputStyle = {
  width: "100%",
  boxSizing: "border-box",
  border: `1px solid ${theme.color.border}`,
  borderRadius: theme.radius.sm,
  backgroundColor: theme.color.bg,
  color: theme.color.text,
  padding: "12px",
  fontSize: "15px",
};
const resultsStyle = { marginTop: theme.spacing.md, maxHeight: "min(540px, calc(100vh - 190px))", overflowY: "auto" };
const groupStyle = { margin: "14px 0 6px", color: theme.color.textMuted, fontSize: "11px", fontWeight: 900, textTransform: "uppercase" };
const resultStyle = {
  display: "block",
  width: "100%",
  textAlign: "left",
  border: "1px solid transparent",
  borderRadius: theme.radius.sm,
  backgroundColor: "transparent",
  color: theme.color.text,
  padding: "10px",
  cursor: "pointer",
};
const activeResultStyle = { borderColor: theme.color.aiBorder, backgroundColor: theme.color.aiBg };
const resultLabelStyle = { display: "block", fontWeight: 800 };
const resultMetaStyle = { display: "block", color: theme.color.textMuted, fontSize: "12px", marginTop: "3px" };
const emptyStyle = { color: theme.color.textMuted, margin: "12px 0" };

export default CommandPalette;
