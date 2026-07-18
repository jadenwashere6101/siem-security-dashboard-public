export function providerCostLabel(metadata) {
  if (!metadata) return "Provider unavailable";
  if (metadata.local_request) return "Local model · no API cost";
  if (metadata.paid_request && metadata.estimated_cost_usd != null) {
    return `Paid model · est. $${Number(metadata.estimated_cost_usd).toFixed(4)}`;
  }
  if (metadata.status === "disabled") return "AI disabled";
  return "Cost unavailable";
}

export function providerStatusLabel(metadata) {
  if (!metadata) return "No provider metadata";
  const provider = metadata.provider || "none";
  const model = metadata.model || "no model";
  return `${provider} / ${model} · ${metadata.status || "unknown"}`;
}

export function sourceCountLabel(context) {
  const count = Array.isArray(context?.sources) ? context.sources.length : 0;
  const omitted = Number(context?.omitted_count || 0);
  if (omitted > 0) return `${count} sources · ${omitted} omitted`;
  return `${count} sources`;
}

export function toolUsageLabel(tools) {
  if (!tools?.used) return "No read tools used";
  const calls = Array.isArray(tools.calls) ? tools.calls : [];
  const failures = calls.filter((call) => call.status && call.status !== "success").length;
  const omitted = Number(tools.omitted_count || 0);
  const parts = [`${calls.length} read tools`];
  if (failures) parts.push(`${failures} limited/failed`);
  if (tools.truncated || omitted > 0) parts.push(`${omitted} omitted`);
  return parts.join(" · ");
}
