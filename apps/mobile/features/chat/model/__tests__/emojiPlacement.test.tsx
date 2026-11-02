import cases from "../../../../../../docs/fixtures/emoji_placement_cases.json";
import { placeEmoji, placeLiveEmoji } from "@/features/chat/model/emojiPlacement";

// The server's finalize pass reads the same cases (test_emoji_placement.py): what
// streams is what will be saved, so nothing changes when the reply settles. A .tsx
// test runs under the React Native Babel transform, as the app does: it once rewrote a
// u-flag emoji class into one that matched nothing, which the plain project missed.
describe("placeEmoji, the twin of the server's emoji pass", () => {
  it.each(cases.map((c) => [c.name, c] as const))("%s", (_name, c) => {
    expect(placeEmoji(c.text, c.level, c.user_wrote_emoji)).toBe(c.expected);
  });
});

describe("placeLiveEmoji", () => {
  it("drops a greeting's wave at A few while it streams", () => {
    expect(placeLiveEmoji("Hey bini 👋", "some", "hi")).toBe("Hey bini");
  });

  it("keeps it at None when the user waved first", () => {
    expect(placeLiveEmoji("Hey bini 👋", "off", "hi 👋")).toBe("Hey bini 👋");
  });

  it("leaves an empty draft alone", () => {
    expect(placeLiveEmoji(undefined, "some", null)).toBeUndefined();
    expect(placeLiveEmoji("", "some", null)).toBe("");
  });
});

describe("placeEmoji on a long line", () => {
  // Each emoji once searched the whole line kept so far for the word before it: a 16k
  // line of 1,000 emoji took about 139 ms per streaming flush (jest), now under 1 ms.
  it("reads the word before each emoji from the end", () => {
    const line = `Done ${"\u2705 Verified step ".repeat(1000)}`;
    const start = performance.now();
    const placed = placeEmoji(line, "some", false);
    expect(performance.now() - start).toBeLessThan(40);
    expect(placed).toBe(`Done.${" Verified step.".repeat(999)} Verified step`);
  });
});
