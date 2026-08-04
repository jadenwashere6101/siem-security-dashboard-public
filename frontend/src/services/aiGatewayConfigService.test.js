import { loadAiGatewayConfig, updateAiGatewayConfig } from "./aiGatewayConfigService";

beforeEach(() => {
  global.fetch = jest.fn();
});

test("loads the super-admin gateway configuration with session credentials", async () => {
  fetch.mockResolvedValue({ ok: true, json: async () => ({ status: "default" }) });

  await loadAiGatewayConfig();

  expect(fetch).toHaveBeenCalledWith(
    "/admin/ai-gateway-config",
    expect.objectContaining({ credentials: "include" })
  );
});

test("patches only the supplied non-secret runtime policy", async () => {
  const configuration = {
    gateway_mode: "automatic_fallback",
    anthropic_routing_enabled: true,
    preferred_anthropic_model: "claude-approved-model",
    daily_paid_budget_usd: 25,
  };
  fetch.mockResolvedValue({ ok: true, json: async () => ({ configuration }) });

  await updateAiGatewayConfig(configuration);

  expect(fetch).toHaveBeenCalledWith(
    "/admin/ai-gateway-config",
    expect.objectContaining({
      method: "PATCH",
      credentials: "include",
      body: JSON.stringify(configuration),
    })
  );
});

test("surfaces safe backend validation errors", async () => {
  fetch.mockResolvedValue({
    ok: false,
    json: async () => ({ error: "Anthropic routing requires a positive daily budget." }),
  });

  await expect(updateAiGatewayConfig({ daily_paid_budget_usd: 0 })).rejects.toThrow(
    "Anthropic routing requires a positive daily budget."
  );
});
