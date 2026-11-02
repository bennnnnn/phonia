import type React from "react";
import { act, renderHook } from "@testing-library/react-native";
import { useImageGeneration } from "@/features/images/hooks/useImageGeneration";
import { api, type Message } from "@/lib/api";
import { uploadChatAttachment, type PendingAttachment } from "@/features/attachments/model/attachments";
import { ApiRequestError } from "@/lib/api/client";
import { notifyWarning } from "@/lib/haptics";
import { reportRecoverableError } from "@/lib/reportRecoverableError";
import { onAppEvent } from "@/lib/appEvents";

jest.mock("@/lib/api", () => ({ api: { generateImage: jest.fn() } }));
jest.mock("@/lib/api/client", () => ({
  ApiRequestError: jest.requireActual("@/lib/api/errorBody").ApiRequestError,
}));
jest.mock("@/features/attachments/model/attachments", () => ({ uploadChatAttachment: jest.fn() }));
jest.mock("@/lib/haptics", () => ({ notifyWarning: jest.fn() }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => null }));
const attachmentAdded = jest.fn();
onAppEvent("attachmentAdded", attachmentAdded);

/** The chat screen's side, as the chat feature supplies it. */
const host = () => ({
  ensureChatId: jest.fn(async (): Promise<string | null> => "chat"),
  uploadReference: async (token: string, attachment: PendingAttachment) =>
    ({ ids: [await uploadChatAttachment(token, attachment)] }),
  describeFailure: (message: string) => ({ message, retryable: true }),
});
jest.mock("@/lib/reportRecoverableError", () => ({ reportRecoverableError: jest.fn() }));

describe("image generation queued state and cancellation", () => {
  beforeEach(() => jest.clearAllMocks());

  async function setup() {
    const updates: React.SetStateAction<Message[]>[] = [];
    const count = { current: 0 };
    const sides = host();
    const rendered = await renderHook(() => useImageGeneration({
      token: "tok", ...sides,
      editThread: (update) => { updates.push(update); },
      streaming: false, isOffline: false, onOpenUpgrade: jest.fn(), onScrollToLatest: jest.fn(),
      newMessageCountRef: count, t: (key) => key,
    }));
    const replay = () => updates.reduce<Message[]>((rows, update) => typeof update === "function" ? update(rows) : update, []);
    return { ...rendered, count, replay };
  }

  it("replaces the optimistic user even when React defers every message updater", async () => {
    const saved = { user_message: { id: "saved-user", role: "user", content: "Draw a cat" },
      assistant_message: { id: "saved-image", role: "assistant", content: "image" } };
    (api.generateImage as jest.Mock).mockResolvedValue(saved);
    const { result, count, replay } = await setup();
    await act(async () => { await result.current.submitPrompt({ prompt: "cat", userMessage: "Draw a cat" }); });
    expect(replay().map((row) => row.id)).toEqual(["saved-user", "saved-image"]);
    expect(count.current).toBe(2);
  });

  it("shows the optimistic turn while persistence gates provider generation", async () => {
    let finishPersistence!: (saved: boolean) => void;
    const persistenceReady = new Promise<boolean>((resolve) => {
      finishPersistence = resolve;
    });
    (api.generateImage as jest.Mock).mockResolvedValue({
      user_message: { id: "saved-user", role: "user", content: "Draw a cat" },
      assistant_message: { id: "saved-image", role: "assistant", content: "image" },
    });
    const { result, replay } = await setup();

    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.submitPrompt({
        prompt: "cat",
        userMessage: "Draw a cat",
        persistenceReady,
      });
      await Promise.resolve();
    });

    expect(replay().map((row) => row.id)).toEqual([
      expect.stringMatching(/^local-img-/),
      "image-gen-pending",
    ]);
    expect(api.generateImage).not.toHaveBeenCalled();

    await act(async () => {
      finishPersistence(true);
      await pending;
    });
    expect(api.generateImage).toHaveBeenCalledTimes(1);
  });

  it("aborts generation and restores the composer when persistence fails", async () => {
    const onPersistenceFailure = jest.fn();
    const { result, replay, count } = await setup();

    await act(async () => {
      await result.current.submitPrompt({
        prompt: "cat",
        userMessage: "Draw a cat",
        persistenceReady: Promise.resolve(false),
        onPersistenceFailure,
      });
    });

    expect(api.generateImage).not.toHaveBeenCalled();
    expect(replay()).toEqual([]);
    expect(count.current).toBe(0);
    expect(onPersistenceFailure).toHaveBeenCalledTimes(1);
  });

  it("cancels a running generation by aborting its request, which the server stops on", async () => {
    let signal: AbortSignal | undefined;
    (api.generateImage as jest.Mock).mockImplementation((_token: string, _body: unknown, init: RequestInit) =>
      new Promise((_resolve, reject) => {
        signal = init.signal ?? undefined;
        signal?.addEventListener("abort", () => reject(new Error("aborted")));
      }));
    const { result, replay } = await setup();
    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.submitPrompt({ prompt: "cat", userMessage: "Draw a cat" });
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(signal?.aborted).toBe(false);
    await act(async () => { result.current.cancel(); await pending; });
    expect(signal?.aborted).toBe(true);
    expect(replay().at(-1)?.image_gen_failure).toBe("canceled");
  });

  it("cancels during upload and retries with that same reference without another upload", async () => {
    let finishUpload!: (id: string) => void;
    (uploadChatAttachment as jest.Mock).mockImplementation(() => new Promise((resolve) => { finishUpload = resolve; }));
    (api.generateImage as jest.Mock).mockResolvedValue({
      user_message: { id: "saved-user", role: "user", content: "Make it blue" },
      assistant_message: { id: "saved-image", role: "assistant", content: "image" },
    });
    const { result, replay } = await setup();
    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.submitPrompt({ prompt: "Make it blue", userMessage: "Make it blue",
        referenceAttachment: { localUri: "file:///reference.png", kind: "image", contentType: "image/png", fileName: "reference.png" } satisfies PendingAttachment });
      await Promise.resolve();
    });
    await act(async () => { result.current.cancel(); finishUpload("original-reference"); await pending; });
    expect(api.generateImage).not.toHaveBeenCalled();
    expect(replay().at(-1)?.image_gen_failure).toBe("canceled");
    await act(async () => { result.current.retry(); await Promise.resolve(); await Promise.resolve(); });
    expect(uploadChatAttachment).toHaveBeenCalledTimes(1);
    expect(api.generateImage).toHaveBeenCalledWith("tok", expect.objectContaining({ reference_attachment_ids: ["original-reference"] }), expect.anything());
    expect(replay().map((row) => row.id)).toEqual(["saved-user", "saved-image"]);
  });
});

describe("image generation submit steps", () => {
  const saved = {
    user_message: { id: "saved-user", role: "user", content: "Draw a cat" },
    assistant_message: { id: "saved-image", role: "assistant", content: "image" },
  };
  beforeEach(() => {
    jest.clearAllMocks();
    (api.generateImage as jest.Mock).mockResolvedValue(saved);
  });

  async function setup(overrides: Partial<Parameters<typeof useImageGeneration>[0]> = {}) {
    const updates: React.SetStateAction<Message[]>[] = [];
    const options = {
      token: "tok" as string | null, ...host(),
      editThread: (update: React.SetStateAction<Message[]>) => { updates.push(update); },
      streaming: false, isOffline: false, onOpenUpgrade: jest.fn(), onOfflineBlocked: jest.fn(), onScrollToLatest: jest.fn(),
      newMessageCountRef: { current: 0 }, t: (key: string) => key,
      ...overrides,
    };
    const rendered = await renderHook(() => useImageGeneration(options));
    const replay = () => updates.reduce<Message[]>((rows, update) => typeof update === "function" ? update(rows) : update, []);
    const submit = async (input: Parameters<ReturnType<typeof useImageGeneration>["submitPrompt"]>[0]) => {
      await act(async () => { await rendered.result.current.submitPrompt(input); });
    };
    return { ...rendered, options, updates, replay, submit };
  }

  it.each([
    ["no session", { token: null }],
    ["an empty prompt", {}],
  ])("does nothing with %s", async (label, overrides) => {
    const { submit, updates } = await setup(overrides);
    await submit({ prompt: label === "an empty prompt" ? "  " : "cat", userMessage: "" });
    expect(updates).toEqual([]);
    expect(api.generateImage).not.toHaveBeenCalled();
  });

  it("asks the user to wait while a chat reply streams", async () => {
    const { submit, updates } = await setup({ streaming: true });
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    expect(reportRecoverableError).toHaveBeenCalledWith(null, "chat.busy");
    expect(updates).toEqual([]);
  });

  it("keeps the request offline and says so", async () => {
    const { submit, updates, options } = await setup({ isOffline: true });
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    expect(notifyWarning).toHaveBeenCalledTimes(1);
    expect(options.onOfflineBlocked).toHaveBeenCalledTimes(1);
    expect(updates).toEqual([]);
  });

  it("ignores a second request while one is generating", async () => {
    let finish!: (value: typeof saved) => void;
    (api.generateImage as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const { result } = await setup();
    let first!: Promise<void>;
    await act(async () => { first = result.current.submitPrompt({ prompt: "cat", userMessage: "Draw a cat" }); });
    await act(async () => { await result.current.submitPrompt({ prompt: "dog", userMessage: "Draw a dog" }); });
    expect(api.generateImage).toHaveBeenCalledTimes(1);
    expect(result.current.generating).toBe(true);
    await act(async () => { finish(saved); await first; });
    expect(result.current.generating).toBe(false);
  });

  it("lands the picture in the chat the screen makes for it", async () => {
    const { submit } = await setup({ ensureChatId: jest.fn(async () => "new-1") });
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    expect(api.generateImage).toHaveBeenCalledWith("tok", expect.objectContaining({ chat_id: "new-1" }), expect.anything());
  });

  it("fails the turn when no chat can be created", async () => {
    const ensureChatId = jest.fn(async (): Promise<string | null> => { throw new Error("Could not create chat"); });
    const { submit, replay } = await setup({ ensureChatId });
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    expect(api.generateImage).not.toHaveBeenCalled();
    expect(replay().at(-1)).toMatchObject({ id: "image-gen-failed", image_gen_failure: "failed", image_gen_error: "Could not create chat" });
  });

  it("words a failure the way the chat does", async () => {
    (api.generateImage as jest.Mock).mockRejectedValueOnce(new Error("raw provider text"));
    const describeFailure = jest.fn(() => ({ message: "chat.error_generic", retryable: true }));
    const { submit, replay } = await setup({ describeFailure });
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    expect(describeFailure).toHaveBeenCalledWith("raw provider text", undefined, expect.any(Error));
    expect(replay().at(-1)).toMatchObject({
      image_gen_failure: "failed", image_gen_error: "chat.error_generic", image_gen_refused: undefined,
    });
  });

  it("sends known reference ids without uploading", async () => {
    const { submit } = await setup();
    await submit({ prompt: "cat, blue", userMessage: "make it blue", aspectRatio: "1:1", referenceAttachmentIds: ["ref-1"] });
    expect(uploadChatAttachment).not.toHaveBeenCalled();
    expect(api.generateImage).toHaveBeenCalledWith("tok", {
      chat_id: "chat",
      prompt: "cat, blue",
      user_message: "make it blue",
      aspect_ratio: "1:1",
      reference_attachment_ids: ["ref-1"],
    }, { signal: expect.any(Object) });
  });

  it("uploads a reference photo once and generates from it", async () => {
    (uploadChatAttachment as jest.Mock).mockResolvedValue("uploaded-1");
    const reference = { localUri: "file:///r.png", kind: "image", contentType: "image/png", fileName: "r.png" } satisfies PendingAttachment;
    const { submit } = await setup();
    await submit({ prompt: "make it blue", userMessage: "make it blue", referenceAttachment: reference });
    expect(uploadChatAttachment).toHaveBeenCalledWith("tok", reference);
    expect(api.generateImage).toHaveBeenCalledWith("tok", expect.objectContaining({ reference_attachment_ids: ["uploaded-1"] }), expect.anything());
  });

  it("fails the turn and keeps it for retry when the upload fails", async () => {
    (uploadChatAttachment as jest.Mock).mockRejectedValueOnce(new Error("Could not read the selected file."));
    const reference = { localUri: "file:///r.png", kind: "image", contentType: "image/png", fileName: "r.png" } satisfies PendingAttachment;
    const { submit, replay, result } = await setup();
    await submit({ prompt: "make it blue", userMessage: "make it blue", referenceAttachment: reference });
    expect(api.generateImage).not.toHaveBeenCalled();
    expect(replay().at(-1)).toMatchObject({ image_gen_failure: "failed", image_gen_error: "Could not read the selected file." });
    (uploadChatAttachment as jest.Mock).mockResolvedValueOnce("uploaded-2");
    await act(async () => { result.current.retry(); await Promise.resolve(); await Promise.resolve(); });
    expect(uploadChatAttachment).toHaveBeenCalledTimes(2);
    expect(replay().map((row) => row.id)).toEqual(["saved-user", "saved-image"]);
  });

  it("settles a success: gallery refreshed, scrolled, nothing left to retry", async () => {
    const { submit, options, result } = await setup();
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    expect(attachmentAdded).toHaveBeenCalledTimes(1);
    expect(options.onScrollToLatest).toHaveBeenCalledTimes(2);
    await act(async () => { result.current.retry(); });
    expect(api.generateImage).toHaveBeenCalledTimes(1);
  });

  // 2026-11-01: a picture that finished after the user opened another chat landed in it.
  it.each([
    ["a success", null],
    ["a failure", new Error("provider down")],
  ])("names the picture's chat on every edit once it has one, on %s", async (_name, failure) => {
    if (failure) (api.generateImage as jest.Mock).mockRejectedValueOnce(failure);
    const owners: (string | null | undefined)[] = [];
    const { submit } = await setup({
      ensureChatId: jest.fn(async () => "new-1"),
      editThread: (_update, _source, chatId) => { owners.push(chatId); },
    });
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    // The painted turn goes to the chat on screen; what follows belongs to the picture's chat.
    expect(owners).toEqual([undefined, "new-1"]);
  });

  it("leaves another chat where it is when the picture waits for its own", async () => {
    const { submit, options } = await setup({
      editThread: (_update, _source, chatId) => chatId === undefined,
    });
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    // Scrolled for the painted turn only, not for a success that did not show.
    expect(options.onScrollToLatest).toHaveBeenCalledTimes(1);
  });

  it("opens the upgrade on a 403 (the server decides the plan)", async () => {
    (api.generateImage as jest.Mock).mockRejectedValueOnce(new ApiRequestError(403, "Pro only"));
    const { submit, replay, options } = await setup();
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    expect(options.onOpenUpgrade).toHaveBeenCalledTimes(1);
    expect(replay().at(-1)).toMatchObject({ id: "image-gen-failed", image_gen_failure: "failed", image_gen_error: undefined });
  });

  it("hands a refusal's code to the chat's wording when the quota runs out", async () => {
    (api.generateImage as jest.Mock).mockRejectedValueOnce(
      new ApiRequestError(429, JSON.stringify({ detail: { code: "daily_limit", message: "Image limit." } })),
    );
    const describeFailure = jest.fn(() => ({ message: "chat.quota_exceeded_free", retryable: false }));
    const { submit, replay, options } = await setup({ describeFailure });
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    expect(options.onOpenUpgrade).not.toHaveBeenCalled();
    expect(describeFailure).toHaveBeenCalledWith("Image limit.", "daily_limit", expect.any(Error));
    // A retry would meet the same cap: the card says why and offers none.
    expect(replay().at(-1)).toMatchObject({
      image_gen_failure: "failed", image_gen_error: "chat.quota_exceeded_free", image_gen_refused: true,
    });
  });

  it("retries a failed turn in place", async () => {
    (api.generateImage as jest.Mock).mockRejectedValueOnce(new Error("boom"));
    const { submit, replay, result, options } = await setup();
    await submit({ prompt: "cat", userMessage: "Draw a cat" });
    expect(replay().map((row) => row.id)).toEqual([expect.stringMatching(/^local-img-/), "image-gen-failed"]);
    await act(async () => { result.current.retry(); await Promise.resolve(); await Promise.resolve(); });
    expect(replay().map((row) => row.id)).toEqual(["saved-user", "saved-image"]);
    expect(options.newMessageCountRef.current).toBe(2);
  });

  it("keeps one retry while its caller hands new callbacks each render, so message rows are not redrawn", async () => {
    (api.generateImage as jest.Mock).mockRejectedValueOnce(new Error("boom"));
    const { options, replay } = await setup();
    // The chat screen passes an inline onOpenUpgrade: every render hands a new one.
    const { result, rerender } = await renderHook(() =>
      useImageGeneration({ ...options, onOpenUpgrade: () => undefined }));
    const first = result.current.retry;
    await rerender({});
    await rerender({});
    expect(result.current.retry).toBe(first);
    await act(async () => { await result.current.submitPrompt({ prompt: "cat", userMessage: "Draw a cat" }); });
    await act(async () => { first(); await Promise.resolve(); await Promise.resolve(); });
    expect(replay().map((row) => row.id)).toEqual(["saved-user", "saved-image"]);
  });
});

describe("image generation under the composer's painted bubble", () => {
  const painted: Message = {
    id: "local-1", role: "user", content: "draw me a cat", model: null, created_at: "now",
    local_image_uri: "file:///reference.png",
  };
  const saved = {
    user_message: { id: "saved-user", role: "user", content: "draw me a cat" },
    assistant_message: { id: "saved-image", role: "assistant", content: "image" },
  };
  beforeEach(() => {
    jest.clearAllMocks();
    (api.generateImage as jest.Mock).mockResolvedValue(saved);
  });

  /** The composer painted its bubble (and counted it) before handing the request over. */
  async function setup(overrides: Partial<Parameters<typeof useImageGeneration>[0]> = {}) {
    const updates: React.SetStateAction<Message[]>[] = [[painted]];
    const count = { current: 1 };
    const options = {
      token: "tok" as string | null, ...host(),
      editThread: (update: React.SetStateAction<Message[]>) => { updates.push(update); },
      streaming: false, isOffline: false, onOpenUpgrade: jest.fn(), onOfflineBlocked: jest.fn(), onScrollToLatest: jest.fn(),
      newMessageCountRef: count, t: (key: string) => key,
      ...overrides,
    };
    const rendered = await renderHook(() => useImageGeneration(options));
    const replay = () => updates.reduce<Message[]>((rows, update) => typeof update === "function" ? update(rows) : update, []);
    return { ...rendered, count, replay };
  }

  it("draws under that bubble instead of adding a second one", async () => {
    let finish!: (value: typeof saved) => void;
    (api.generateImage as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    const { result, replay, count } = await setup();
    let pending!: Promise<void>;
    await act(async () => {
      pending = result.current.submitPrompt({ prompt: "cat", userMessage: "draw me a cat", userMessageId: "local-1" });
    });
    expect(replay()).toEqual([
      { ...painted, content: "draw me a cat" },
      expect.objectContaining({ id: "image-gen-pending" }),
    ]);
    expect(count.current).toBe(2);
    await act(async () => { finish(saved); await pending; });
    expect(replay().map((row) => row.id)).toEqual(["saved-user", "saved-image"]);
  });

  it("is not refused by a chat reply that ended in the same tick", async () => {
    const { result, replay } = await setup({ streaming: true });
    await act(async () => {
      await result.current.submitPrompt({ prompt: "cat", userMessage: "draw me a cat", userMessageId: "local-1" });
    });
    expect(reportRecoverableError).not.toHaveBeenCalled();
    expect(replay().map((row) => row.id)).toEqual(["saved-user", "saved-image"]);
  });

  it.each([
    ["offline", { isOffline: true }],
    ["signed out", { token: null }],
  ])("takes the bubble away and gives the draft back when it cannot start (%s)", async (_label, overrides) => {
    const onPersistenceFailure = jest.fn();
    const { result, replay, count } = await setup(overrides);
    await act(async () => {
      await result.current.submitPrompt({
        prompt: "cat", userMessage: "draw me a cat", userMessageId: "local-1", onPersistenceFailure,
      });
    });
    expect(replay()).toEqual([]);
    expect(count.current).toBe(0);
    expect(onPersistenceFailure).toHaveBeenCalledTimes(1);
    expect(api.generateImage).not.toHaveBeenCalled();
  });

  it("takes the bubble and the pending picture away when the drafts fail to save", async () => {
    const onPersistenceFailure = jest.fn();
    const { result, replay, count } = await setup();
    await act(async () => {
      await result.current.submitPrompt({
        prompt: "cat", userMessage: "draw me a cat", userMessageId: "local-1",
        persistenceReady: Promise.resolve(false), onPersistenceFailure,
      });
    });
    expect(replay()).toEqual([]);
    expect(count.current).toBe(0);
    expect(onPersistenceFailure).toHaveBeenCalledTimes(1);
  });

  it("retries a failed picture under the same bubble", async () => {
    (api.generateImage as jest.Mock).mockRejectedValueOnce(new Error("boom"));
    const { result, replay } = await setup();
    await act(async () => {
      await result.current.submitPrompt({ prompt: "cat", userMessage: "draw me a cat", userMessageId: "local-1" });
    });
    expect(replay().map((row) => row.id)).toEqual(["local-1", "image-gen-failed"]);
    await act(async () => { result.current.retry(); await Promise.resolve(); await Promise.resolve(); });
    expect(replay().map((row) => row.id)).toEqual(["saved-user", "saved-image"]);
    expect(api.generateImage).toHaveBeenCalledTimes(2);
  });
});
