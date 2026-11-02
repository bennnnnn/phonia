import { conversationMarkdownBody } from "@/features/chat/model/transcript";
import type { Message } from "@/lib/api";

jest.mock("@/lib/i18n", () => ({
  __esModule: true,
  default: { t: (key: string) => key },
}));

describe("conversationMarkdownBody", () => {
  it("joins user and assistant turns and skips system messages", () => {
    const body = conversationMarkdownBody([
      { id: "s1", role: "system", content: "hidden" },
      { id: "u1", role: "user", content: "hello" },
      { id: "a1", role: "assistant", content: "hi there" },
    ] as Message[]);
    expect(body).toContain("**share.role_user:**\nhello");
    expect(body).toContain("**share.role_assistant:**\nhi there");
    expect(body).not.toContain("hidden");
  });

  it("shows what the user sent, never the server's file markers or file text", () => {
    const body = conversationMarkdownBody([
      {
        id: "u1",
        role: "user",
        content: [
          "What does this say?",
          "[File: /attachments/0b1c/file]",
          "[File (application/pdf)]",
          "SECRET EXTRACTED TEXT",
          "[Image: /attachments/9f2e/file]",
        ].join("\n"),
      },
    ] as Message[]);
    expect(body).toContain("What does this say?");
    expect(body).toContain("share.attachment_pdf");
    expect(body).toContain("share.attachment_photo");
    expect(body).not.toContain("/attachments/");
    expect(body).not.toContain("SECRET EXTRACTED TEXT");
  });

  it("leaves out a reply that is only a control card, and labels cards", () => {
    const body = conversationMarkdownBody([
      { id: "u1", role: "user", content: "remind me" },
      {
        id: "a1",
        role: "assistant",
        content: '```reminder_proposal\n{"proposal_id":"p1"}\n```',
      },
      { id: "a2", role: "assistant", content: 'Here:\n\n```graph\n{"curves":[]}\n```' },
    ] as Message[]);
    expect(body).not.toContain("proposal_id");
    expect(body.match(/share\.role_assistant/g)).toHaveLength(1);
    expect(body).toContain("share.block_graph");
    expect(body).not.toContain("curves");
  });

  it("shares a card's lines as plain lines, with no trailing spaces", () => {
    const quiz = '```quiz\n{"question":"Pick","options":["a","b"],"answer":1}\n```';
    const body = conversationMarkdownBody([{ id: "a1", role: "assistant", content: quiz }] as Message[]);
    expect(body).toContain("Pick\nA) a\nB) b");
    expect(body).not.toMatch(/ +\n/);
  });
});

