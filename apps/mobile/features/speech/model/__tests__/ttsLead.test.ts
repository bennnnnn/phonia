import {
  splitTtsChunks,
  splitTtsLead,
  TTS_LEAD_MAX_CHARS,
  TTS_LEAD_MIN_CHARS,
} from "@/features/speech/model/ttsLead";

describe("splitTtsLead", () => {
  it("keeps a short reply intact", () => {
    expect(splitTtsLead("Hello there.")).toEqual({
      lead: "Hello there.",
      rest: "",
    });
  });

  it("does not stop after a one-word opener", () => {
    const restBody =
      "Here is a longer explanation that should stay in the lead until we have enough audio to cover the next request. Then this leftover paragraph is fetched only after playback has already started.";
    const { lead, rest } = splitTtsLead(`Sure. ${restBody}`);
    expect(lead.startsWith("Sure.")).toBe(true);
    expect(lead.length).toBeGreaterThanOrEqual(TTS_LEAD_MIN_CHARS);
    expect(rest.length).toBeGreaterThan(0);
  });

  it("stays within the max window", () => {
    const text = `${"alpha ".repeat(40).trim()}. Extra sentence after the cut.`;
    const { lead, rest } = splitTtsLead(text);
    expect(lead.length).toBeLessThanOrEqual(TTS_LEAD_MAX_CHARS);
    expect(rest.length).toBeGreaterThan(0);
  });

  it("treats CJK and Ethiopic sentence marks as boundaries", () => {
    const restBody =
      "Here is a longer explanation that should stay in the lead until we have enough audio to cover the next request. Then this leftover paragraph is fetched only after playback has already started.";
    const { lead } = splitTtsLead(`好的。${restBody}`);
    expect(lead.startsWith("好的。")).toBe(true);
    const amharic = splitTtsLead(`እሺ።${restBody}`);
    expect(amharic.lead.startsWith("እሺ።")).toBe(true);
  });
});

describe("splitTtsChunks", () => {
  it("returns one clip for a short reply", () => {
    expect(splitTtsChunks("Hello there.")).toEqual(["Hello there."]);
  });

  it("splits a long page into short clips", () => {
    const sentence = "This is a complete sentence that should fill a clip window. ";
    const text = sentence.repeat(12).trim();
    const chunks = splitTtsChunks(text);
    expect(chunks.length).toBeGreaterThan(2);
    expect(chunks.join(" ")).toBe(text.split(/\s+/).join(" "));
    expect(chunks.every((chunk) => chunk.length <= TTS_LEAD_MAX_CHARS)).toBe(true);
  });
});
