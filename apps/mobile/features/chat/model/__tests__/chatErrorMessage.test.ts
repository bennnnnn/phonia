import { resolveChatError } from "@/features/chat/model/errorMessage";
import i18n, { ensureLocale } from "@/lib/i18n";
import de from "@/lib/i18n/de.json";

describe("chatErrorMessage", () => {
  const t = (key: string) => key;

  it("maps known error codes to i18n", () => {
    expect(resolveChatError({ message: "", code: "busy", isPaid: false, t })).toEqual({
      kind: "busy",
      message: "chat.busy",
    });
    expect(
      resolveChatError({ message: "", code: "model_unavailable", isPaid: false, t }),
    ).toEqual({
      kind: "model_unavailable",
      message: "chat.model_unavailable",
    });
  });

  it("distinguishes an unsaved send from an active reply's busy notice", () => {
    expect(resolveChatError({ message: "Still saving", code: "send_rejected", isPaid: false, t })).toEqual({
      kind: "send_rejected",
      message: "chat.send_rejected",
    });
  });

  it("names the plan's limit by code, never by the English", () => {
    expect(
      resolveChatError({ message: "Reworded limit.", code: "quota_exceeded", isPaid: false, t }),
    ).toEqual({ kind: "quota", message: "chat.quota_exceeded_free" });
    expect(
      resolveChatError({ message: "Image limit.", code: "daily_limit", isPaid: true, t }).message,
    ).toBe("chat.quota_exceeded_pro");
    // The words alone are not a code: a spend-cap message is not an upgrade prompt.
    expect(
      resolveChatError({ message: "You've used up today's free limit.", isPaid: false, t }).kind,
    ).toBe("generic");
  });

  // The socket's frames for a turn the spend gate refused: the server's English showed in
  // every language. Redis down at the spend read sent spend_cap too ("Recall is at capacity
  // for today… Try again after midnight UTC.").
  it("says the day's spend cap in the phone's language, and an outage as Recall unavailable", () => {
    const capacity = "Recall is at capacity for today, so new messages are paused for everyone.";
    expect(resolveChatError({ message: capacity, code: "spend_cap", isPaid: false, t })).toEqual({
      kind: "generic",
      message: "chat.spend_cap",
    });
    expect(
      resolveChatError({ message: "Service temporarily unavailable.", code: "unavailable", isPaid: true, t }),
    ).toEqual({ kind: "generic", message: "common.service_unavailable" });
  });

  // The turn's own failure frames (modules/chat/stream_events.py) named no code, and their
  // English showed: "Something went wrong. Try again.", "Chat not found.", "The server is
  // restarting. Send again in a moment.", "Failed to save the response. Please retry."
  it.each([
    ["failed", "Something went wrong. Try again.", "chat.error_generic"],
    ["not_found", "Chat not found.", "chat.error_generic"],
    ["server_restarting", "The server is restarting. Send again in a moment.", "chat.server_restarting"],
    ["reply_not_saved", "Failed to save the response. Please retry.", "chat.reply_not_saved"],
  ])("words the turn's %s frame in the phone's language", (code, english, key) => {
    expect(resolveChatError({ message: english, code, isPaid: false, t })).toEqual({ kind: "generic", message: key });
  });

  describe("on a German phone", () => {
    beforeAll(async () => { await ensureLocale("de"); });
    afterAll(async () => { await ensureLocale("en"); });

    it.each([
      ["spend_cap", "Recall is at capacity for today, so new messages are paused for everyone.", "chat.spend_cap"],
    ] as const)("says the %s frame in German", (code, english, key) => {
      const german = i18n.getFixedT("de");
      const resolved = resolveChatError({ message: english, code, isPaid: false, t: german });
      expect(resolved.message).toBe(de[key]);
      expect(resolved.message).not.toBe(english);
    });
  });

  it("falls back for an empty message", () => {
    expect(resolveChatError({ message: "", isPaid: false, t })).toEqual({
      kind: "generic",
      message: "chat.error_generic",
    });
  });
});
