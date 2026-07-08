import React from "react";

import {
  ALLOWED_AUTO_REFRESH_INTERVALS,
  ALLOWED_LIVE_LOGS_FONT_SIZES,
  ALLOWED_LIVE_LOGS_TABS,
  ALLOWED_ROWS_PER_PAGE_VALUES,
  ALLOWED_SEVERITY_COLOR_PRESETS,
} from "../utils/uiSettings";

const AUTO_REFRESH_OPTION_LABELS = {
  0: "Off",
  5000: "5 sec",
  10000: "10 sec",
  30000: "30 sec",
  60000: "60 sec",
};

const ROWS_PER_PAGE_LABELS = {
  all: "All",
  10: "10",
  25: "25",
  50: "50",
  100: "100",
};

const LIVE_LOG_FONT_SIZE_LABELS = {
  small: "Small",
  medium: "Medium",
  large: "Large",
};

const LIVE_LOG_TAB_LABELS = {
  eventFeed: "Event Feed",
  rawLog: "Raw Log",
  json: "JSON",
};

const SEVERITY_PRESET_LABELS = {
  default: "Default",
  colorblindSafe: "Colorblind Safe",
  highContrast: "High Contrast",
};

const HIGHLIGHT_TREATMENT_OPTIONS = [
  { id: "border", label: "Border" },
  { id: "background", label: "Background" },
  { id: "glow", label: "Glow" },
];

function SettingsPanel({
  settings,
  landingPageOptions,
  onDefaultLandingPageChange,
  onAutoRefreshIntervalChange,
  onDisplaySettingsChange,
  sections,
  roleFlags,
  cardStyle,
  cardHeaderStyle,
  cardTitleStyle,
  cardSubtitleStyle,
  filterLabelStyle,
  selectStyle,
}) {
  return (
    <section style={cardStyle}>
      <div style={cardHeaderStyle}>
        <div>
          <h2 style={cardTitleStyle}>Settings</h2>
          <p style={cardSubtitleStyle}>
            Configure core SIEM preferences. Additional preferences will appear here in future
            updates.
          </p>
        </div>
      </div>

      <div style={settingsContentStyle}>
        <div style={settingsFieldStyle}>
          <label htmlFor="default-landing-page" style={filterLabelStyle}>
            Default landing page
          </label>
          <select
            id="default-landing-page"
            value={settings.defaultLandingPage}
            onChange={(event) => onDefaultLandingPageChange(event.target.value)}
            style={selectStyle}
          >
            {landingPageOptions.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div style={settingsFieldStyle}>
          <label htmlFor="global-auto-refresh-interval" style={filterLabelStyle}>
            Global auto-refresh interval
          </label>
          <select
            id="global-auto-refresh-interval"
            value={settings.autoRefreshIntervalMs}
            onChange={(event) => onAutoRefreshIntervalChange(Number(event.target.value))}
            style={selectStyle}
          >
            {ALLOWED_AUTO_REFRESH_INTERVALS.map((value) => (
              <option key={value} value={value}>
                {AUTO_REFRESH_OPTION_LABELS[value]}
              </option>
            ))}
          </select>
        </div>

        <div style={settingsFieldStyle}>
          <label htmlFor="display-timezone-mode" style={filterLabelStyle}>
            Timezone display
          </label>
          <select
            id="display-timezone-mode"
            value={settings.display.timezoneMode}
            onChange={(event) => onDisplaySettingsChange({ timezoneMode: event.target.value })}
            style={selectStyle}
          >
            <option value="local">Local Browser Time (recommended)</option>
            <option value="utc">UTC</option>
          </select>
        </div>

        <div style={settingsFieldStyle}>
          <label htmlFor="display-timestamp-format" style={filterLabelStyle}>
            Timestamp format
          </label>
          <select
            id="display-timestamp-format"
            value={settings.display.timestampFormat}
            onChange={(event) => onDisplaySettingsChange({ timestampFormat: event.target.value })}
            style={selectStyle}
          >
            <option value="24h">24-hour</option>
            <option value="12h">12-hour</option>
          </select>
        </div>

        <div style={settingsFieldStyle}>
          <label htmlFor="display-rows-per-page" style={filterLabelStyle}>
            Rows per page / event limit
          </label>
          <select
            id="display-rows-per-page"
            value={String(settings.display.rowsPerPage)}
            onChange={(event) =>
              onDisplaySettingsChange({
                rowsPerPage: event.target.value === "all" ? "all" : Number(event.target.value),
              })
            }
            style={selectStyle}
          >
            {ALLOWED_ROWS_PER_PAGE_VALUES.map((value) => (
              <option key={String(value)} value={String(value)}>
                {ROWS_PER_PAGE_LABELS[value]}
              </option>
            ))}
          </select>
        </div>

        <div style={settingsFieldStyle}>
          <label htmlFor="display-live-logs-font-size" style={filterLabelStyle}>
            Live Logs font size
          </label>
          <select
            id="display-live-logs-font-size"
            value={settings.display.liveLogsFontSize}
            onChange={(event) => onDisplaySettingsChange({ liveLogsFontSize: event.target.value })}
            style={selectStyle}
          >
            {ALLOWED_LIVE_LOGS_FONT_SIZES.map((value) => (
              <option key={value} value={value}>
                {LIVE_LOG_FONT_SIZE_LABELS[value]}
              </option>
            ))}
          </select>
        </div>

        <div style={settingsFieldStyle}>
          <label htmlFor="display-default-live-logs-tab" style={filterLabelStyle}>
            Default Live Logs tab
          </label>
          <select
            id="display-default-live-logs-tab"
            value={settings.display.defaultLiveLogsTab}
            onChange={(event) => onDisplaySettingsChange({ defaultLiveLogsTab: event.target.value })}
            style={selectStyle}
          >
            {ALLOWED_LIVE_LOGS_TABS.map((value) => (
              <option key={value} value={value}>
                {LIVE_LOG_TAB_LABELS[value]}
              </option>
            ))}
          </select>
        </div>

        <div style={settingsFieldStyle}>
          <label htmlFor="display-severity-color-preset" style={filterLabelStyle}>
            Severity color preset
          </label>
          <select
            id="display-severity-color-preset"
            value={settings.display.severityColorPreset}
            onChange={(event) => onDisplaySettingsChange({ severityColorPreset: event.target.value })}
            style={selectStyle}
          >
            {ALLOWED_SEVERITY_COLOR_PRESETS.map((value) => (
              <option key={value} value={value}>
                {SEVERITY_PRESET_LABELS[value]}
              </option>
            ))}
          </select>
        </div>
      </div>

      <div style={settingsSectionStyle}>
        <p style={sectionHeadingStyle}>Column Visibility</p>
        <ColumnVisibilityEditor
          settings={settings}
          onDisplaySettingsChange={onDisplaySettingsChange}
          sections={sections}
          roleFlags={roleFlags}
        />
      </div>

      <div style={settingsSectionStyle}>
        <p style={sectionHeadingStyle}>Live Log Highlighting Rules</p>
        <HighlightRuleEditor settings={settings} onDisplaySettingsChange={onDisplaySettingsChange} />
      </div>
    </section>
  );
}

function ColumnVisibilityEditor({ settings, onDisplaySettingsChange, sections, roleFlags }) {
  const updates = { ...settings.display.columnVisibility };

  const updateTableColumn = (tableName, columnName, value) => {
    updates[tableName] = {
      ...settings.display.columnVisibility[tableName],
      [columnName]: value,
    };
    onDisplaySettingsChange({ columnVisibility: updates });
  };

  const liveLogsVisible = sections.some(
    (section) =>
      section.group === "live logs" &&
      (typeof section.visibleWhen === "function" ? section.visibleWhen(roleFlags) : true)
  );

  return (
    <div style={columnGridStyle}>
      <ColumnToggleGroup
        title="Alerts table"
        columns={settings.display.columnVisibility.alertsTable}
        onToggle={(column, value) => updateTableColumn("alertsTable", column, value)}
      />
      {liveLogsVisible && (
        <ColumnToggleGroup
          title="Live Logs Event Feed table"
          columns={settings.display.columnVisibility.liveLogsTable}
          onToggle={(column, value) => updateTableColumn("liveLogsTable", column, value)}
        />
      )}
      <ColumnToggleGroup
        title="Incidents table"
        columns={settings.display.columnVisibility.incidentsTable}
        onToggle={(column, value) => updateTableColumn("incidentsTable", column, value)}
      />
    </div>
  );
}

function ColumnToggleGroup({ title, columns, onToggle }) {
  return (
    <div style={columnGroupStyle}>
      <p style={columnGroupTitleStyle}>{title}</p>
      {Object.entries(columns).map(([column, visible]) => {
        const isIdColumn = column === "id";
        return (
          <label key={column} style={checkboxLabelStyle}>
            <input
              type="checkbox"
              checked={visible}
              disabled={isIdColumn}
              onChange={(event) => onToggle(column, event.target.checked)}
            />
            <span>
              {column}
              {isIdColumn ? " (always visible)" : ""}
            </span>
          </label>
        );
      })}
    </div>
  );
}

function HighlightRuleEditor({ settings, onDisplaySettingsChange }) {
  const rules = settings.display.liveLogHighlightRules;

  const upsertRule = (index, patch) => {
    const nextRules = rules.map((rule, i) => (i === index ? { ...rule, ...patch } : rule));
    onDisplaySettingsChange({ liveLogHighlightRules: nextRules });
  };

  const addRule = () => {
    onDisplaySettingsChange({
      liveLogHighlightRules: [...rules, { target: "severity", value: "high", treatment: "border" }],
    });
  };

  const removeRule = (index) => {
    onDisplaySettingsChange({
      liveLogHighlightRules: rules.filter((_, i) => i !== index),
    });
  };

  return (
    <div style={highlightContainerStyle}>
      {rules.map((rule, index) => (
        <div key={`${rule.target}-${rule.value}-${index}`} style={highlightRuleStyle}>
          <select
            value={rule.target}
            onChange={(event) => upsertRule(index, { target: event.target.value })}
            style={compactSelectStyle}
          >
            <option value="severity">Severity</option>
            <option value="type">Type</option>
          </select>
          <input
            value={rule.value}
            onChange={(event) => upsertRule(index, { value: event.target.value })}
            style={inputStyle}
          />
          <select
            value={rule.treatment}
            onChange={(event) => upsertRule(index, { treatment: event.target.value })}
            style={compactSelectStyle}
          >
            {HIGHLIGHT_TREATMENT_OPTIONS.map((option) => (
              <option key={option.id} value={option.id}>
                {option.label}
              </option>
            ))}
          </select>
          <button type="button" style={removeButtonStyle} onClick={() => removeRule(index)}>
            Remove
          </button>
        </div>
      ))}
      <button type="button" style={addButtonStyle} onClick={addRule}>
        Add highlight rule
      </button>
    </div>
  );
}

const settingsContentStyle = {
  padding: "20px",
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))",
  gap: "20px",
};

const settingsFieldStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "8px",
};

const settingsSectionStyle = {
  padding: "0 20px 20px 20px",
};

const sectionHeadingStyle = {
  margin: "0 0 12px 0",
  color: "#8b949e",
  fontSize: "12px",
  fontWeight: "700",
  letterSpacing: "0.06em",
  textTransform: "uppercase",
};

const columnGridStyle = {
  display: "grid",
  gridTemplateColumns: "repeat(auto-fit, minmax(240px, 1fr))",
  gap: "14px",
};

const columnGroupStyle = {
  border: "1px solid #30363d",
  borderRadius: "10px",
  padding: "12px",
  backgroundColor: "#0d1117",
};

const columnGroupTitleStyle = {
  margin: "0 0 10px 0",
  color: "#c9d1d9",
  fontSize: "13px",
  fontWeight: "700",
};

const checkboxLabelStyle = {
  display: "flex",
  alignItems: "center",
  gap: "8px",
  color: "#c9d1d9",
  fontSize: "13px",
  marginBottom: "6px",
};

const highlightContainerStyle = {
  display: "flex",
  flexDirection: "column",
  gap: "10px",
};

const highlightRuleStyle = {
  display: "grid",
  gridTemplateColumns: "140px 1fr 140px auto",
  gap: "8px",
};

const compactSelectStyle = {
  minWidth: 0,
  padding: "8px 10px",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  border: "1px solid #30363d",
  borderRadius: "8px",
  fontSize: "13px",
};

const inputStyle = {
  minWidth: 0,
  padding: "8px 10px",
  backgroundColor: "#0d1117",
  color: "#e6edf3",
  border: "1px solid #30363d",
  borderRadius: "8px",
  fontSize: "13px",
};

const removeButtonStyle = {
  padding: "8px 10px",
  borderRadius: "8px",
  border: "1px solid rgba(239, 68, 68, 0.35)",
  backgroundColor: "rgba(239, 68, 68, 0.10)",
  color: "#fca5a5",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

const addButtonStyle = {
  width: "fit-content",
  padding: "8px 12px",
  borderRadius: "8px",
  border: "1px solid rgba(88, 166, 255, 0.35)",
  backgroundColor: "rgba(31, 111, 235, 0.10)",
  color: "#93c5fd",
  fontSize: "12px",
  fontWeight: "700",
  cursor: "pointer",
};

export default SettingsPanel;
