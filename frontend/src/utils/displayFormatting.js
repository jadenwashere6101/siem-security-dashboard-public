export const formatTimestamp = (value, displaySettings, fallback = "N/A") => {
  if (!value) {
    return fallback;
  }

  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return fallback;
  }

  const timezoneMode = displaySettings?.timezoneMode === "utc" ? "utc" : "local";
  const timestampFormat = displaySettings?.timestampFormat === "12h" ? "12h" : "24h";

  const options = {
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
    hour12: timestampFormat === "12h",
    timeZoneName: "short",
  };

  if (timezoneMode === "utc") {
    options.timeZone = "UTC";
  }

  return new Intl.DateTimeFormat("en-US", options).format(parsed);
};
