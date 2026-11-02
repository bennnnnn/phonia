import { parseTeaching, teachingSpeech } from "@/lib/math/teachingBlock";

describe("parseTeaching", () => {
  it("accepts a server-owned picture and ignores a column trace", () => {
    const picture = JSON.stringify({
      type: "number_bond",
      whole: 7,
      left: 3,
      right: 4,
      answer: "7",
      speech: "7 is 3 plus 4.",
    });

    expect(parseTeaching(picture)?.type).toBe("number_bond");
    expect(teachingSpeech(picture)).toBe("7 is 3 plus 4.");
    expect(parseTeaching(JSON.stringify({ type: "arithmetic", answer: "12", speech: "no" }))).toBe(
      null,
    );
    expect(parseTeaching('{"type":"ten_frame"}')).toBeNull();
  });
});
