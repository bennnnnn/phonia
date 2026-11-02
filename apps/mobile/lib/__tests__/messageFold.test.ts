import {
  MESSAGE_FOLD_MAX_HEIGHT,
  shouldCollapseMessage,
} from "@/lib/markdown/messageFold";

describe("messageFold", () => {
  it("exports ~320px fold threshold", () => {
    expect(MESSAGE_FOLD_MAX_HEIGHT).toBe(320);
  });

  it("does not collapse short messages", () => {
    expect(shouldCollapseMessage("Hello")).toBe(false);
    expect(shouldCollapseMessage("a".repeat(400))).toBe(false);
  });

  it("collapses when character count exceeds threshold", () => {
    expect(shouldCollapseMessage("word ".repeat(110))).toBe(true);
  });

  it("collapses when line count exceeds threshold", () => {
    expect(shouldCollapseMessage(Array.from({ length: 14 }, (_, i) => `line ${i}`).join("\n"))).toBe(
      true,
    );
  });

  it("ignores whitespace-only content", () => {
    expect(shouldCollapseMessage("   \n  ")).toBe(false);
  });
});
