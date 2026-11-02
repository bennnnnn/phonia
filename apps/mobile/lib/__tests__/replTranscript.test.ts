import { fenceReplTranscripts } from "@/lib/markdown/replTranscript";

describe("fenceReplTranscripts", () => {
  it("turns a >>> transcript into a python block", () => {
    expect(
      fenceReplTranscripts(
        "Test it:\n\n>>> two_sum([2, 7, 11, 15], 9)\n[0, 1]\n\nIt returns indexes.",
      ),
    ).toBe(
      "Test it:\n\n```python\n>>> two_sum([2, 7, 11, 15], 9)\n[0, 1]\n```\n\nIt returns indexes.",
    );
  });

  it.each([
    "```python\n>>> two_sum([2, 7], 9)\n[0, 1]\n```",
    "> A real quote.",
    "Compare a >>> b in prose.",
  ])("leaves %j alone", (text) => {
    expect(fenceReplTranscripts(text)).toBe(text);
  });
});
