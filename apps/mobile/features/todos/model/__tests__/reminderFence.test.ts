import { stripReminderFences } from "@/features/todos/model/reminderFence";
import { deriveAssistantMessageContent } from "@/lib/markdown/assistantMessageContent";

describe("stripReminderFences", () => {
  it("removes reminder JSON fences from chat text", () => {
    const input =
      "✅ Reminder set!\n\n```reminder\n" +
      '{"title":"World Cup Final","due_at":"2026-07-19T15:00:00-04:00"}\n```\n';
    const out = stripReminderFences(input);
    expect(out).toContain("Reminder set");
    expect(out).not.toContain("```reminder");
    expect(out).not.toContain("due_at");
  });
});

describe("deriveAssistantMessageContent reminder fences", () => {
  it("strips reminder fences from markdown content", () => {
    const result = deriveAssistantMessageContent({
      content:
        "Done.\n```reminder\n" +
        '{"title":"Call mom","due_at":"2026-07-11T18:00:00-07:00"}\n```',
      layoutFrozen: false,
      isUser: false,
      priorUserText: null,
      messageId: "m1",
      isGenerating: false,
    });
    expect(result.markdownContent).toContain("Done");
    expect(result.markdownContent).not.toContain("```reminder");
  });
});
