import { readAloudIsCut, readAloudPart, TTS_MAX_CHARS } from "@/features/speech/model/readAloudLength";

it("reads a short text whole", () => {
  expect(readAloudPart("  Hello there.  ")).toBe("Hello there.");
});

it("stops a long text at the last sentence end before the limit", () => {
  const sentence = "The quick brown fox jumps over the lazy dog. ";
  const text = sentence.repeat(Math.ceil((TTS_MAX_CHARS * 1.5) / sentence.length));
  const part = readAloudPart(text);
  expect(part.length).toBeLessThanOrEqual(TTS_MAX_CHARS);
  expect(part.endsWith("dog.")).toBe(true);
});

it("never stops in the middle of a word", () => {
  const text = "word ".repeat(TTS_MAX_CHARS);
  const part = readAloudPart(text);
  expect(part.length).toBeLessThanOrEqual(TTS_MAX_CHARS);
  expect(part.endsWith("word")).toBe(true);
});

it("says when a reply is longer than read aloud reads", () => {
  expect(readAloudIsCut("Short reply.")).toBe(false);
  expect(readAloudIsCut("a ".repeat(TTS_MAX_CHARS))).toBe(true);
});
