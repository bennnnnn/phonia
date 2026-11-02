import {
  IMAGE_GEN_FAILED_ASSISTANT_ID,
  IMAGE_GEN_PENDING_ASSISTANT_ID,
} from "@/features/images/model/imageGenMessages";
import {
  applyImageGenFailure,
  applyImageGenSuccess,
  hasImageGenFailedAssistant,
  imageGenUserBubble,
  readImageTurn,
  restoreImageGenPending,
} from "@/features/images/model/imageGenTurn";
import type { Message } from "@/lib/api";

const mockImageIntent = jest.fn();
jest.mock("@/lib/api", () => ({
  api: { imageIntent: (...args: unknown[]) => mockImageIntent(...args) },
}));

const IMAGE_ID = "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee";

function verdict(fields: Partial<{
  subject: "math" | "physics" | "chemistry" | null;
  lookup_query: string | null;
  generate_prompt: string | null;
  revision: boolean;
  reference_attachment_ids: string[];
}>) {
  return {
    subject: null,
    lookup_query: null,
    generate_prompt: null,
    revision: false,
    reference_attachment_ids: [],
    ...fields,
  };
}

function row(id: string, role: Message["role"], content: string): Message {
  return {
    id,
    role,
    content,
    model: null,
    created_at: "2026-01-01T00:00:00.000Z",
  };
}

describe("imageGenUserBubble", () => {
  it("keeps the words the user typed", () => {
    expect(imageGenUserBubble("create a cat image", "cat")).toBe("create a cat image");
  });

  it("does not rewrite to Generate image: prefix", () => {
    expect(imageGenUserBubble("create a cat image", "cat")).not.toMatch(/^Generate image:/i);
  });
});

describe("image gen failure card", () => {
  const pending = [
    row("local-img-1", "user", "create a cat image"),
    row(IMAGE_GEN_PENDING_ASSISTANT_ID, "assistant", ""),
  ];

  it("keeps the user bubble and marks the assistant canceled", () => {
    const next = applyImageGenFailure(pending, "canceled");
    expect(next[0]?.content).toBe("create a cat image");
    expect(next[1]?.id).toBe(IMAGE_GEN_FAILED_ASSISTANT_ID);
    expect(next[1]?.image_gen_failure).toBe("canceled");
    expect(hasImageGenFailedAssistant(next)).toBe(true);
  });

  it("restores the pending card for retry", () => {
    const failed = applyImageGenFailure(pending, "failed", "Couldn't create the image");
    const next = restoreImageGenPending(failed);
    expect(next[0]?.content).toBe("create a cat image");
    expect(next[1]?.id).toBe(IMAGE_GEN_PENDING_ASSISTANT_ID);
    expect(next[1]?.image_gen_failure).toBeUndefined();
  });
});

describe("image gen success", () => {
  const saved = [row("saved-user", "user", "create a cat image"), row("saved-image", "assistant", "image")];

  it("puts the saved turn where the painted one was", () => {
    const painted = [row("older", "user", "hi"), row("local-img-1", "user", "create a cat image"),
      row(IMAGE_GEN_PENDING_ASSISTANT_ID, "assistant", "")];
    expect(applyImageGenSuccess(painted, "local-img-1", saved).map((r) => r.id)).toEqual(["older", "saved-user", "saved-image"]);
  });

  // 2026-11-01: back in its chat, the page read on return already held the saved turn.
  it("keeps one copy when the chat's page already holds the saved turn", () => {
    expect(applyImageGenSuccess(saved, "local-img-1", saved).map((r) => r.id)).toEqual(["saved-user", "saved-image"]);
  });
});

describe("readImageTurn", () => {
  const send = { text: "make it blue", chatId: "chat-1", imageAttached: false };

  beforeEach(() => mockImageIntent.mockReset());

  it("asks the server about the text, the chat and an attached image", async () => {
    mockImageIntent.mockResolvedValue(verdict({}));
    await readImageTurn("token", { text: "make it blue", chatId: null, imageAttached: true });
    expect(mockImageIntent).toHaveBeenCalledWith("token", {
      text: "make it blue",
      chat_id: null,
      image_attached: true,
    });
  });

  it("draws the server's prompt from the picture an edit starts from", async () => {
    mockImageIntent.mockResolvedValue(verdict({
      generate_prompt: "dog, blue",
      revision: true,
      reference_attachment_ids: [IMAGE_ID],
    }));
    await expect(readImageTurn("token", send)).resolves.toEqual({
      kind: "generate",
      prompt: "dog, blue",
      referenceIds: [IMAGE_ID],
    });
  });

  it("draws a new picture with no reference", async () => {
    mockImageIntent.mockResolvedValue(verdict({ generate_prompt: "fox" }));
    await expect(readImageTurn("token", { ...send, text: "draw a fox" })).resolves.toEqual({
      kind: "generate",
      prompt: "fox",
      referenceIds: [],
    });
  });

  it("sends a photo lookup as chat, where the server attaches the photo", async () => {
    mockImageIntent.mockResolvedValue(verdict({ lookup_query: "ear" }));
    await expect(readImageTurn("token", { ...send, text: "show me an ear" })).resolves.toEqual({ kind: "lookup" });
  });

  it.each([
    ["a maths, physics or chemistry turn", verdict({ subject: "chemistry" })],
    ["ordinary chat", verdict({})],
  ])("sends %s as chat", async (_label, answer) => {
    mockImageIntent.mockResolvedValue(answer);
    await expect(readImageTurn("token", send)).resolves.toEqual({ kind: "send" });
  });

  it.each([
    ["offline", new TypeError("Network request failed")],
    ["a server error", Object.assign(new Error("500"), { status: 500 })],
    ["a slow answer", Object.assign(new Error("Aborted"), { name: "AbortError" })],
  ])("sends as chat when the server cannot answer (%s)", async (_label, error) => {
    mockImageIntent.mockRejectedValue(error);
    await expect(readImageTurn("token", send)).resolves.toEqual({ kind: "send" });
  });
});
