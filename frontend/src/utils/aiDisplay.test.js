import { providerStatusLabel } from "./aiDisplay";

test("providerStatusLabel includes selected AI profile when present", () => {
  expect(
    providerStatusLabel({
      provider: "ollama",
      model: "llama3.2:3b",
      profile: "fast_triage",
      status: "success",
    })
  ).toBe("ollama / llama3.2:3b · fast_triage · success");
});
