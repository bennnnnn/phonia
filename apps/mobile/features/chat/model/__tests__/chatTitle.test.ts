import {
  chatNeedsGeneratedTitle,
  displayChatTitle,
  provisionalAttachmentTitle,
  provisionalChatTitle,
  sanitizeManualChatTitle,
} from "@/features/chat/model/title";

const t = (key: string) =>
  ({
    "common.untitled": "Untitled",
    "chat.title_generating": "Generating title…",
  })[key] ?? key;

describe("chatTitle", () => {
  it("displayChatTitle prefers stored title", () => {
    expect(displayChatTitle("Python tips", {}, t)).toBe("Python tips");
  });

  it("displayChatTitle shows generating placeholder", () => {
    expect(displayChatTitle(null, { generating: true }, t)).toBe("Generating title…");
  });

  it("displayChatTitle falls back to untitled", () => {
    expect(displayChatTitle(null, {}, t)).toBe("Untitled");
  });

  it("chatNeedsGeneratedTitle treats placeholders as missing", () => {
    expect(chatNeedsGeneratedTitle(null)).toBe(true);
    expect(chatNeedsGeneratedTitle("Untitled")).toBe(true);
    expect(chatNeedsGeneratedTitle("Homework")).toBe(false);
  });

  it("provisionalChatTitle uses the first line and truncates", () => {
    expect(provisionalChatTitle("What's still open for me to finish tonight?")).toBe(
      "What's still open for me to finish tonight",
    );
    expect(provisionalChatTitle("  Hello\nsecond line")).toBe("Hello");
    expect(provisionalChatTitle("   ")).toBeNull();
    expect(provisionalChatTitle("x".repeat(60))).toBe(`${"x".repeat(47)}…`);
    expect(
      provisionalChatTitle(
        "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]",
      ),
    ).toBe("Image");
    expect(provisionalChatTitle("[File: notes.pdf]")).toBe("File");
    expect(provisionalChatTitle("What's in this image?\n\n[Image: local]")).toBe(
      "Image",
    );
  });

  it("provisionalAttachmentTitle is Image/File only", () => {
    expect(provisionalAttachmentTitle("hi")).toBeNull();
    expect(provisionalAttachmentTitle("good morning")).toBeNull();
    expect(
      provisionalAttachmentTitle(
        "[Image: /attachments/aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee/file]",
      ),
    ).toBe("Image");
    expect(provisionalAttachmentTitle("[File: notes.pdf]")).toBe("File");
  });

  it("sanitizeManualChatTitle strips quotes and enforces length", () => {
    expect(sanitizeManualChatTitle('  "My chat"  ')).toBe("My chat");
    expect(sanitizeManualChatTitle('"My Trip Plan".')).toBe("My Trip Plan");
    expect(sanitizeManualChatTitle("New chat")).toBe("New chat");
    expect(sanitizeManualChatTitle("   ")).toBeNull();
    expect(sanitizeManualChatTitle("x".repeat(81))).toBeNull();
  });

  it("displayChatTitle unwraps dirty stored titles", () => {
    expect(displayChatTitle('"My Trip Plan".', {}, t)).toBe("My Trip Plan");
  });
});
