import { isSendEcho, SEND_ECHO_MS } from "../composerSendEcho";

const SENT = { text: "I’m in indianapolis", at: 1_000 };

describe("isSendEcho", () => {
  it.each([
    // Seen in the Simulator: the whole message, its last word corrected, came back.
    "I'm in Indianapolis",
    // And the half the keyboard remembered, then sent with the next message.
    "I'm in ",
    "I’m in indianapolis",
    "i'm",
  ])("drops the keyboard giving back %p", (text) => {
    expect(isSendEcho(SENT, text, SENT.at + 200)).toBe(true);
  });

  it("drops a whole message with a word autocorrect fixed", () => {
    const sent = { text: "thx for teh help", at: 0 };
    expect(isSendEcho(sent, "thx for the help", 100)).toBe(true);
  });

  it.each([
    ["once the moment has passed", "I'm in Indianapolis", SEND_ECHO_MS + 1],
    ["a new message", "hello there", 200],
    ["more than was sent", "I'm in indianapolis and it's raining", 200],
    ["a different message of the same length", "what about tomorrow then", 200],
    ["an empty field", "", 200],
  ])("keeps %s", (_label, text, after) => {
    expect(isSendEcho(SENT, text, SENT.at + after)).toBe(false);
  });

  it("keeps everything when nothing was cleared", () => {
    expect(isSendEcho(null, "I'm in Indianapolis", 0)).toBe(false);
  });
});
