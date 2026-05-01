const TIMESTAMP_FORMAT_OPTIONS = {
  month: "short",
  day: "2-digit",
  year: "numeric",
  hour: "2-digit",
  minute: "2-digit",
  hour12: false,
  timeZone: "UTC",
  timeZoneName: "short",
};

export const formatAdminTimestamp = (value, fallback) => {
  if (fallback !== undefined && !value) return fallback;
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("en-US", TIMESTAMP_FORMAT_OPTIONS).format(date);
};
