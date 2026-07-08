import React from "react";

import { ALLOWED_AUTO_REFRESH_INTERVALS } from "../utils/uiSettings";

const AUTO_REFRESH_OPTION_LABELS = {
  0: "Off",
  5000: "5 sec",
  10000: "10 sec",
  30000: "30 sec",
  60000: "60 sec",
};

function SettingsPanel({
  settings,
  landingPageOptions,
  onDefaultLandingPageChange,
  onAutoRefreshIntervalChange,
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
      </div>
    </section>
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

export default SettingsPanel;
