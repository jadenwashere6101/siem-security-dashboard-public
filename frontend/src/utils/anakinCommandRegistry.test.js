import {
  ANAKIN_COMMAND_INTENTS,
  assertReadOnlyPaletteCommand,
  buildCommandContext,
  commandToAiOptions,
  createCommandRegistry,
  createDefaultAnakinCommands,
  sanitizeCommandContext,
  normalizeContextualAiOptions,
} from "./anakinCommandRegistry";

test("command registry filters by availability and role context", () => {
  const registry = createCommandRegistry([
    { id: "always", label: "Always", group: "Test" },
    { id: "operate", label: "Operate", group: "Test", requiresCanOperate: true },
    { id: "hidden", label: "Hidden", group: "Test", availability: () => false },
  ]);

  expect(registry.available({ user: { canTakeAlertActions: false } }).map((command) => command.id)).toEqual(["always"]);
  expect(registry.available({ user: { canTakeAlertActions: true } }).map((command) => command.id)).toEqual(["always", "operate"]);
});

test("command context sanitizes unrelated and sensitive state", () => {
  const context = buildCommandContext({
    activeSection: "dashboard",
    selectedAlertId: 7,
    alerts: [{ alert_id: 7, alert_type: "failed_login", source_ip: "203.0.113.10", secret: "nope" }],
    metrics: { totalAlerts: 1 },
    currentUsername: "analyst1",
    userRole: "analyst",
    canTakeAlertActions: true,
  });

  expect(context.object.alert).toEqual(
    expect.objectContaining({ id: 7, alert_type: "failed_login", source_ip: "203.0.113.10" })
  );
  expect(context.object.alert.secret).toBeUndefined();
  expect(context.user).toEqual({ username: "analyst1", role: "analyst", canTakeAlertActions: true });
});

test("palette read-only safety blocks mutations but allows approval navigation wording", () => {
  expect(assertReadOnlyPaletteCommand({ id: "nav.approvals", label: "SOAR Approvals", readOnly: true })).toBe(true);
  expect(assertReadOnlyPaletteCommand({ id: "approve.item", label: "Approve item", readOnly: true })).toBe(false);
  expect(assertReadOnlyPaletteCommand({ id: "retry.dead-letter", label: "Retry dead letter", readOnly: true })).toBe(false);
  expect(assertReadOnlyPaletteCommand({ id: "safe", label: "Safe", readOnly: false })).toBe(false);
});

test("default Anakin commands map to existing AI option shapes", () => {
  const commands = createDefaultAnakinCommands();
  expect(commands.map((command) => command.intent)).toEqual(
    expect.arrayContaining([
      ANAKIN_COMMAND_INTENTS.ask,
      ANAKIN_COMMAND_INTENTS.summarize,
      ANAKIN_COMMAND_INTENTS.investigate,
      ANAKIN_COMMAND_INTENTS.explain,
      ANAKIN_COMMAND_INTENTS.draft,
      ANAKIN_COMMAND_INTENTS.suggestedActions,
    ])
  );

  const draft = commandToAiOptions(
    commands.find((command) => command.intent === ANAKIN_COMMAND_INTENTS.draft),
    sanitizeCommandContext({ workspace: { activeSection: "dashboard" } })
  );
  expect(draft).toEqual(expect.objectContaining({ draftType: "investigation_checklist" }));
});

test("contextual AI options choose explicit intents without nested precedence", () => {
  expect(normalizeContextualAiOptions({ draftType: "case_summary" }).intent).toBe(ANAKIN_COMMAND_INTENTS.draft);
  expect(normalizeContextualAiOptions({ investigation: true }).intent).toBe(ANAKIN_COMMAND_INTENTS.investigate);
  expect(normalizeContextualAiOptions({ action: "explain" }).intent).toBe("explain");
  expect(normalizeContextualAiOptions({}).intent).toBe(ANAKIN_COMMAND_INTENTS.ask);
});
