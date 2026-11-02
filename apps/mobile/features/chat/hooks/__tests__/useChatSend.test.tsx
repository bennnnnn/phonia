import { ApiRequestError } from "@/lib/api/client";
import type { Message } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import React, { useLayoutEffect } from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";

import { useChatSend } from "@/features/chat/hooks/useChatSend";
import type { DotsTicket } from "@/features/chat/hooks/useTurnStart";
import {
  pickDocument,
  pickFromCamera,
  pickFromPhotoLibrary,
  uploadChatAttachment,
} from "@/features/attachments/model/attachments";
import { AttachmentError } from "@/features/attachments/model/attachmentErrors";
import { registerEmailDraftFlusher } from "@/features/drafts/model/emailDraftFlush";
import { notifyWarning, tap } from "@/lib/haptics";
import * as latency from "@/features/chat/model/latency";
jest.mock("@/lib/auth", () => ({ getSessionGeneration: jest.fn(() => 0) }));
beforeEach(() => {
  (getSessionGeneration as jest.Mock).mockReturnValue(0);
  dotsUp = true;
});

/** Draft flushers registered by a test, removed after it. */
const holds: (() => void)[] = [];
afterEach(() => holds.splice(0).forEach((unregister) => unregister()));

/** Holds a painted send at its draft flush until the test releases it (false: refused). */
function holdAtDraftFlush(): { release: (ok: boolean) => void } {
  let release: (ok: boolean) => void = () => undefined;
  holds.push(registerEmailDraftFlusher(() => new Promise((resolve) => { release = resolve; })));
  return { release: (ok) => release(ok) };
}
const uploadAttachment = uploadChatAttachment as jest.Mock;

const inputRef = { current: "hello" };
const mockSetInput = jest.fn();
const mockSetParams = jest.fn();
const mockSetChatId = jest.fn();
const mockSetChatTitle = jest.fn();
const mockFeedbackError = jest.fn();
const mockSwitchThread = jest.fn();
const mockAdoptComposerThread = jest.fn();
const mockStashFailedDraftForThread = jest.fn();
let mockThreadKey = "new";
const mockResetForNewSession = jest.fn();
jest.mock("@/features/chat/context/ComposerDraftContext", () => ({
  useComposerDraftApi: () => ({
    setInput: mockSetInput,
    inputRef,
    switchThread: mockSwitchThread,
    adoptComposerThread: mockAdoptComposerThread,
    stashFailedDraftForThread: mockStashFailedDraftForThread,
    resetForNewSession: mockResetForNewSession,
    getThreadKey: () => mockThreadKey,
  }),
}));
jest.mock("@/contexts/ActionFeedbackContext", () => ({
  useActionFeedbackOptional: () => ({ error: mockFeedbackError }),
}));
jest.mock("expo-router", () => ({
  useRouter: () => ({ setParams: jest.fn() }),
}));
jest.mock("@/features/attachments/model/attachments", () => ({
  pickDocument: jest.fn(),
  pickFromCamera: jest.fn(),
  pickFromPhotoLibrary: jest.fn(),
  uploadChatAttachment: jest.fn(),
  messageTextForSend: jest.fn((text: string) => text),
  discardDraftAttachment: (...args: unknown[]) => mockDiscardDraftAttachment(...args),
  NativePickerBusyError: class extends Error {},
  NativePickerTimeoutError: class extends Error {},
  PhotoLibraryPermissionError: class extends Error {
    needsSettings = false;
  },
}));
const mockDiscardDraftAttachment = jest.fn();
const mockReadScan = jest.fn();
jest.mock("@/lib/api", () => ({
  api: {
    readScan: (...args: unknown[]) => mockReadScan(...args),
  },
}));
jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
  notifyWarning: jest.fn(),
}));
const mockTap = tap as jest.Mock;
const mockNotifyWarning = notifyWarning as jest.Mock;
jest.mock("@/lib/scheduleIdle", () => ({
  scheduleIdlePromise: () => Promise.resolve(),
}));
jest.mock("@/features/attachments/model/pendingComposerAttachment", () => ({
  subscribeComposerAttachmentQueue: () => () => undefined,
  takeQueuedComposerAttachment: () => null,
}));

let current: ReturnType<typeof useChatSend>;
const onOfflineBlocked = jest.fn();
/** Typing dots under the painted bubble; current while they are still this send's. */
let dotsUp = true;
const cancelDots = jest.fn();
const beginDots = jest.fn((): DotsTicket | null => ({ current: () => dotsUp, cancel: cancelDots }));
const whenReplySettled = jest.fn((_waitingId?: string) => Promise.resolve());
const sendStart = { beginDots, whenReplySettled };
/** The chat's dispatch: true once it took the send. */
const sent = () => jest.fn(async () => true);

function Probe({
  offline = false,
  chatLoading = false,
  chatId = null,
  routeChatId,
  token = "token",
  sendMessage = sent(),
  prepareDraftChat = jest.fn(),
  setMessages = jest.fn(),
  streaming = false,
  onStreamBusy,
  draft,
  beforeSend,
}: {
  offline?: boolean;
  chatLoading?: boolean;
  chatId?: string | null;
  routeChatId?: string;
  token?: string | null;
  sendMessage?: jest.Mock;
  prepareDraftChat?: jest.Mock;
  setMessages?: jest.Mock;
  streaming?: boolean;
  onStreamBusy?: jest.Mock;
  draft?: Record<string, unknown>;
  beforeSend?: () => Promise<void>;
}) {
  const result = useChatSend({
    token,
    chatId,
    chatLoading,
    routeChatId,
    setChatId: mockSetChatId,
    setChatTitle: mockSetChatTitle,
    router: { setParams: mockSetParams } as never,
    draft: (draft ?? {
      draftChatIdRef: { current: null },
      skipLoadForChatIdRef: { current: null },
      creatingRef: { current: false },
      prepareDraftChat,
      setDraftChatId: jest.fn(),
      discardEmptyChat: jest.fn(),
    }) as never,
    scroll: { newMessageCountRef: { current: 0 } } as never,
    streaming,
    sendMessage,
    sendStart,
    editThread: setMessages,
    t: (key) => key,
    onStreamBusy,
    isOffline: offline,
    onOfflineBlocked,
    beforeSend,
  });
  useLayoutEffect(() => { current = result; });
  return <Text>send</Text>;
}

describe("useChatSend", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    inputRef.current = "hello";
    mockThreadKey = "new";
  });

  it("keeps the draft and surfaces the offline callback", async () => {
    await act(async () => {
      render(<Probe offline />);
    });
    await act(async () => {
      await current.handleSend();
    });
    expect(onOfflineBlocked).toHaveBeenCalledTimes(1);
  });

  // A clarify card's button stays live when its picks did not go out.
  it("says whether the send went out: not offline, yes once its bubble painted", async () => {
    await act(async () => {
      render(<Probe offline />);
    });
    let went: boolean | undefined;
    await act(async () => {
      went = await current.handleSend("Main priority: Safety.");
    });
    expect(went).toBe(false);
    await act(async () => {
      render(<Probe chatId="chat-1" />);
    });
    await act(async () => {
      went = await current.handleSend("Main priority: Safety.");
    });
    expect(went).toBe(true);
  });

  it("claims the double-send guard in the tap's own tick for a plain send", async () => {
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    let first!: Promise<boolean>;
    await act(async () => {
      first = current.handleSend();
      // A second tap before the first one yields to anything.
      await current.handleSend();
      await first;
    });
    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it("blocks duplicate sends while preparation is in flight", async () => {
    const sendMessage = sent();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    });

    await act(async () => {
      await Promise.all([current.handleSend(), current.handleSend()]);
    });

    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it("wipes composer drafts when the account session changes", async () => {
    const view = await act(async () => render(<Probe />));
    expect(mockResetForNewSession).not.toHaveBeenCalled();
    (getSessionGeneration as jest.Mock).mockReturnValue(1);
    await act(async () => {
      view.rerender(<Probe />);
    });
    expect(mockResetForNewSession).toHaveBeenCalledTimes(1);
    expect(mockSwitchThread).toHaveBeenCalledWith("new");
  });

  it("surfaces new-chat creation failures and restores the draft", async () => {
    const prepareDraftChat = jest.fn().mockRejectedValue(new Error("failed"));
    await act(async () => {
      render(<Probe prepareDraftChat={prepareDraftChat} />);
    });

    await act(async () => {
      await current.handleSend();
    });

    expect(mockSetInput).toHaveBeenCalledWith("hello");
    expect(mockFeedbackError).toHaveBeenCalledWith("chat.error_generic");
    expect(current.sendPhase).toBe("idle");
  });

  it("paints the user bubble before the drafts save, and sends once they have", async () => {
    inputRef.current = "coffee near me";
    const held = holdAtDraftFlush();
    const setMessages = jest.fn();
    const sendMessage = sent();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} setMessages={setMessages} />);
    });

    let sendPromise: Promise<boolean> = Promise.resolve(true);
    await act(async () => {
      sendPromise = current.handleSend();
      await Promise.resolve();
    });

    // The bubble, an empty composer and the dots go up at the tap; the turn
    // itself waits for the drafts to save.
    expect(setMessages).toHaveBeenCalledTimes(1);
    expect(mockSetInput).toHaveBeenCalledWith("");
    expect(beginDots).toHaveBeenCalledTimes(1);
    expect(sendMessage).not.toHaveBeenCalled();
    expect(current.sendPhase).toBe("preparing");

    await act(async () => {
      held.release(true);
      await sendPromise;
    });

    const appended = setMessages.mock.calls[0][0]([{ id: "prior", role: "assistant" }]);
    expect(appended.at(-1)).toMatchObject({ role: "user", content: "coffee near me" });
    expect(sendMessage).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ skipUserBubble: true }),
    );
    expect(current.pendingOutboundId).toBeNull();
    expect(current.sendPhase).toBe("idle");
  });

  it("sends from a window only after the newest page is back, and once (NET-18)", async () => {
    inputRef.current = "and then?";
    let back: () => void = () => undefined;
    const beforeSend = jest.fn(() => new Promise<void>((resolve) => { back = resolve; }));
    const setMessages = jest.fn();
    const sendMessage = jest.fn(async () => true);
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} setMessages={setMessages} beforeSend={beforeSend} />);
    });
    let sendPromise: Promise<boolean> = Promise.resolve(true);
    await act(async () => {
      sendPromise = current.handleSend();
      await Promise.resolve();
    });
    expect(beforeSend).toHaveBeenCalledTimes(1);
    expect(setMessages).not.toHaveBeenCalled();
    // A second tap while the newest page loads sends nothing.
    await act(async () => { await current.handleSend(); });
    expect(beforeSend).toHaveBeenCalledTimes(1);

    await act(async () => {
      back();
      await sendPromise;
    });
    expect(setMessages).toHaveBeenCalledTimes(1);
    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it("clears the composer attachment before upload finishes", async () => {
    let finishUpload: (id: string) => void = () => undefined;
    uploadAttachment.mockReturnValue(
      new Promise((resolve) => {
        finishUpload = resolve;
      }),
    );
    inputRef.current = "";
    const sendMessage = sent();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    });
    await act(async () => {
      current.setPendingAttachment({
        localUri: "file://pic.jpg",
        contentType: "image/jpeg",
        fileName: "pic.jpg",
        kind: "image",
      });
    });

    let sendPromise: Promise<boolean> = Promise.resolve(true);
    await act(async () => {
      sendPromise = current.handleSend();
      await Promise.resolve();
    });

    expect(current.pendingAttachment).toBeNull();
    expect(current.sendPhase).toBe("uploading");
    expect(current.attachPicking).toBe(false);
    expect(sendMessage).not.toHaveBeenCalled();

    await act(async () => {
      finishUpload("att-1");
      await sendPromise;
    });
    expect(sendMessage).toHaveBeenCalled();
    expect(current.sendPhase).toBe("idle");
  });

  it("keeps each thread's attachment with its draft when switching threads", async () => {
    const photo = { localUri: "file://pic.jpg", contentType: "image/jpeg", fileName: "pic.jpg", kind: "image" as const };
    mockThreadKey = "chat-1";
    const view = await act(async () =>
      render(<Probe chatId="chat-1" routeChatId="chat-1" />),
    );
    await act(async () => { current.setPendingAttachment(photo); });

    await act(async () => {
      await view.rerender(<Probe chatId="chat-1" routeChatId="chat-2" />);
    });
    expect(current.pendingAttachment).toBeNull();
    expect(mockSwitchThread).toHaveBeenCalledWith("chat-2");

    mockThreadKey = "chat-2";
    await act(async () => {
      await view.rerender(<Probe chatId="chat-1" routeChatId="chat-1" />);
    });
    expect(current.pendingAttachment).toBe(photo);
    expect(mockDiscardDraftAttachment).not.toHaveBeenCalled();
  });

  it("keeps an attachment uploaded for a chat the user left, so the next send reuses it", async () => {
    let finishUpload!: (id: string) => void;
    uploadAttachment.mockReturnValueOnce(new Promise((resolve) => { finishUpload = resolve; }));
    const report = { localUri: "file://report.pdf", contentType: "application/pdf", fileName: "report.pdf", kind: "file" as const };
    mockThreadKey = "chat-1";
    const view = await render(<Probe chatId="chat-1" routeChatId="chat-1" />);
    await act(async () => { current.setPendingAttachment(report); });
    let sending!: Promise<boolean>;
    await act(async () => { sending = current.handleSend(); });

    await view.rerender(<Probe chatId="chat-1" routeChatId="chat-2" />);
    mockThreadKey = "chat-2";
    await act(async () => { finishUpload("uploaded-id"); await sending; });
    expect(mockStashFailedDraftForThread).toHaveBeenCalledWith("chat-1", "hello");

    await act(async () => { await view.rerender(<Probe chatId="chat-1" routeChatId="chat-1" />); });
    expect(current.pendingAttachment).toEqual({ ...report, existingAttachmentId: "uploaded-id", uploadedForDraft: true });
    // Kept, not cancelled: the upload is what the stashed draft sends next.
    expect(mockDiscardDraftAttachment).not.toHaveBeenCalled();
  });

  it("discards an attachment the user removes or replaces, and nothing a send took", async () => {
    const first = { localUri: "file://a.jpg", contentType: "image/jpeg", fileName: "a.jpg", kind: "image" as const };
    const second = { ...first, localUri: "file://b.jpg", fileName: "b.jpg" };
    (pickFromPhotoLibrary as jest.Mock).mockResolvedValueOnce(second);
    await render(<Probe chatId="chat-1" routeChatId="chat-1" />);
    await act(async () => { current.setPendingAttachment(first); });
    await act(async () => { await current.handleAttachmentSheetSelect("photo"); });
    expect(current.pendingAttachment).toBe(second);
    expect(mockDiscardDraftAttachment).toHaveBeenCalledWith("token", first);

    await act(async () => { current.removePendingAttachment(); });
    expect(current.pendingAttachment).toBeNull();
    expect(mockDiscardDraftAttachment).toHaveBeenLastCalledWith("token", second);
  });

  it("refuses Send while a picked photo is still being prepared", async () => {
    let finishPick!: (value: unknown) => void;
    (pickFromCamera as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finishPick = resolve; }));
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" routeChatId="chat-1" sendMessage={sendMessage} />);
    let picking!: Promise<void>;
    await act(async () => { picking = current.handleAttachmentSheetSelect("camera"); });
    expect(current.attachPicking).toBe(true);

    await act(async () => { await current.handleSend(); });
    expect(sendMessage).not.toHaveBeenCalled();
    expect(mockSetInput).not.toHaveBeenCalledWith("");

    const photo = { localUri: "file://shot.jpg", contentType: "image/jpeg", fileName: "shot.jpg", kind: "image" };
    await act(async () => { finishPick(photo); await picking; });
    expect(current.attachPicking).toBe(false);
    expect(current.pendingAttachment).toBe(photo);
  });

  it.each([
    [new AttachmentError("too_large"), "chat.attach_too_large"],
    [new AttachmentError("camera_permission"), "chat.camera_permission"],
    [new Error("Camera permission is required to take photos."), "chat.attach_failed"],
  ])("reports a refused pick (%p) by its message key", async (error, key) => {
    (pickFromCamera as jest.Mock).mockRejectedValueOnce(error);
    await render(<Probe chatId="chat-1" routeChatId="chat-1" />);
    await act(async () => { await current.handleAttachmentSheetSelect("camera"); });
    expect(mockFeedbackError).toHaveBeenCalledWith(key);
    expect(current.pendingAttachment).toBeNull();
    expect(current.attachPicking).toBe(false);
  });

  it("stashes a failed send on the originating thread after a switch", async () => {
    mockThreadKey = "chat-1";
    const held = holdAtDraftFlush();
    const view = await act(async () =>
      render(<Probe chatId="chat-1" routeChatId="chat-1" />),
    );

    let sendPromise: Promise<boolean> = Promise.resolve(true);
    await act(async () => {
      sendPromise = current.handleSend();
      await Promise.resolve();
    });

    mockThreadKey = "chat-2";
    await act(async () => {
      await view.rerender(<Probe chatId="chat-1" routeChatId="chat-2" />);
    });

    await act(async () => {
      held.release(false);
      await sendPromise;
    });

    // The composer was cleared at the tap, so chat-1 gets its text back.
    expect(mockStashFailedDraftForThread).toHaveBeenCalledWith("chat-1", "hello");
    expect(mockSetInput).not.toHaveBeenCalledWith("hello");
    expect(current.sendPhase).toBe("idle");
  });

  it("does not replace a newer draft when the failed send restores", async () => {
    const held = holdAtDraftFlush();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sent()} />);
    });

    let sendPromise: Promise<boolean> = Promise.resolve(true);
    await act(async () => {
      sendPromise = current.handleSend();
      await Promise.resolve();
    });
    inputRef.current = "follow-up";

    await act(async () => {
      held.release(false);
      await sendPromise;
    });

    expect(mockSetInput).not.toHaveBeenCalledWith("hello");
    expect(current.sendPhase).toBe("idle");
  });

  it("adopts the composer onto a newly created chat id", async () => {
    const prepareDraftChat = jest.fn().mockResolvedValue("created-1");
    await act(async () => {
      render(<Probe prepareDraftChat={prepareDraftChat} />);
    });
    await act(async () => {
      await current.handleSend();
    });
    expect(mockAdoptComposerThread).toHaveBeenCalledWith("created-1");
  });

  it("keeps the draft while the requested chat is still loading", async () => {
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" routeChatId="chat-2" sendMessage={sendMessage} />);
    await act(async () => { await current.handleSend(); });
    expect(sendMessage).not.toHaveBeenCalled();
    expect(mockSetInput).not.toHaveBeenCalled();
  });

  it("keeps the draft until history loading finishes", async () => {
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" routeChatId="chat-1" chatLoading sendMessage={sendMessage} />);
    await act(async () => { await current.handleSend(); });
    expect(sendMessage).not.toHaveBeenCalled();
    expect(mockSetInput).not.toHaveBeenCalled();
  });

  it("does not dispatch a prepared send after switching chats", async () => {
    mockThreadKey = "chat-1";
    const held = holdAtDraftFlush();
    const sendMessage = sent();
    const view = await render(<Probe chatId="chat-1" routeChatId="chat-1" sendMessage={sendMessage} />);
    let sending!: Promise<boolean>;
    await act(async () => {
      sending = current.handleSend();
      await Promise.resolve();
    });
    mockThreadKey = "chat-2";
    await view.rerender(<Probe chatId="chat-2" routeChatId="chat-2" sendMessage={sendMessage} />);
    await act(async () => {
      held.release(true);
      await sending;
    });
    expect(sendMessage).not.toHaveBeenCalled();
    expect(mockStashFailedDraftForThread).toHaveBeenCalledWith("chat-1", "hello");
    expect(current.sendPhase).toBe("idle");
  });

  it("does not reopen a new chat when creation finishes after navigation", async () => {
    let finishCreate!: (id: string) => void;
    const prepareDraftChat = jest.fn(() => new Promise((resolve) => { finishCreate = resolve; }));
    const view = await render(<Probe prepareDraftChat={prepareDraftChat} />);
    let sending!: Promise<boolean>;
    await act(async () => {
      sending = current.handleSend();
      await Promise.resolve();
      await Promise.resolve();
    });
    mockThreadKey = "chat-2";
    await view.rerender(<Probe chatId="chat-2" routeChatId="chat-2" />);
    await act(async () => {
      finishCreate("created-1");
      await sending;
    });
    expect(mockSetParams).not.toHaveBeenCalled();
    expect(mockAdoptComposerThread).not.toHaveBeenCalled();
    expect(mockSetChatId).not.toHaveBeenCalled();
    expect(current.sendPhase).toBe("idle");
  });


  it("dispatches a new chat's pending send once its own id is loaded", async () => {
    const prepareDraftChat = jest.fn().mockResolvedValue("created-1");
    const sendMessage = sent();
    const view = await render(<Probe prepareDraftChat={prepareDraftChat} sendMessage={sendMessage} />);
    await act(async () => { await current.handleSend(); });
    expect(sendMessage).not.toHaveBeenCalled();
    mockThreadKey = "created-1";
    await view.rerender(<Probe chatId="created-1" routeChatId="created-1" sendMessage={sendMessage} />);
    expect(sendMessage).toHaveBeenCalledTimes(1);
    expect(sendMessage).toHaveBeenCalledWith("hello", expect.objectContaining({ skipUserBubble: true }));
    expect(current.sendPhase).toBe("idle");
  });

  it("gives a new chat's draft back when the chat refuses its send", async () => {
    const prepareDraftChat = jest.fn().mockResolvedValue("created-1");
    const sendMessage = jest.fn(async () => false);
    const setMessages = jest.fn();
    const view = await render(
      <Probe prepareDraftChat={prepareDraftChat} sendMessage={sendMessage} setMessages={setMessages} />,
    );
    await act(async () => { await current.handleSend(); });
    mockThreadKey = "created-1";
    await act(async () => {
      await view.rerender(
        <Probe chatId="created-1" routeChatId="created-1" sendMessage={sendMessage} setMessages={setMessages} />,
      );
    });
    expect(sendMessage).toHaveBeenCalledTimes(1);
    const rows = setMessages.mock.calls.reduce(
      (prev: Message[], [update]) => (typeof update === "function" ? update(prev) : update),
      [],
    );
    expect(rows).toEqual([]);
    expect(mockSetInput).toHaveBeenLastCalledWith("hello");
    expect(current.sendPhase).toBe("idle");
  });

});


it("does not move a late picker result into another chat", async () => {
  let finish!: (value: unknown) => void;
  (pickDocument as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const view = await render(<Probe chatId="chat-1" routeChatId="chat-1" />);
  let picking!: Promise<void>;
  await act(async () => { picking = current.handleAttachmentSheetSelect("file"); });
  await view.rerender(<Probe chatId="chat-2" routeChatId="chat-2" />);
  await act(async () => {
    finish({ localUri: "file://report.pdf", contentType: "application/pdf", fileName: "report.pdf", kind: "file" });
    await picking;
  });
  expect(current.pendingAttachment).toBeNull();
  expect(mockDiscardDraftAttachment).toHaveBeenCalledWith(null, expect.objectContaining({ localUri: "file://report.pdf" }));
});

it("retains the uploaded id when the draft flush fails after the upload", async () => {
  uploadAttachment.mockResolvedValueOnce("uploaded-id");
  const unregisterFlush = registerEmailDraftFlusher(() => Promise.resolve(false));
  try {
    await render(<Probe chatId="chat-1" routeChatId="chat-1" />);
    await act(async () => {
      current.setPendingAttachment({ localUri: "file://report.pdf", contentType: "application/pdf", fileName: "report.pdf", kind: "file" });
    });
    inputRef.current = "hello";
    await act(async () => { await current.handleSend(); });
    expect(current.pendingAttachment?.existingAttachmentId).toBe("uploaded-id");
  } finally {
    unregisterFlush();
  }
});

it("continues an attachment send through an access-token refresh in the same session", async () => {
  let finish!: (id: string) => void;
  uploadAttachment.mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const sendMessage = sent();
  const view = await render(<Probe chatId="chat-1" routeChatId="chat-1" sendMessage={sendMessage} />);
  await act(async () => {
    current.setPendingAttachment({ localUri: "file://report.pdf", contentType: "application/pdf", fileName: "report.pdf", kind: "file" });
  });
  let sending!: Promise<boolean>;
  await act(async () => { sending = current.handleSend(); });
  await view.rerender(<Probe chatId="chat-1" routeChatId="chat-1" token="refreshed" sendMessage={sendMessage} />);
  await act(async () => { finish("uploaded-id"); await sending; });
  expect(sendMessage).toHaveBeenCalledTimes(1);
  expect(sendMessage).toHaveBeenCalledWith(expect.any(String), expect.objectContaining({ attachmentIds: ["uploaded-id"] }));
});


describe("rejected attachment composer recovery", () => {
  const attachment = { kind: "file" as const, localUri: "file:///original.pdf", fileName: "original.pdf", contentType: "application/pdf" };
  beforeEach(() => { jest.clearAllMocks(); inputRef.current = ""; mockThreadKey = "a"; });

  it("restores the exact empty-caption file draft without sending", async () => {
    const sendMessage = sent();
    await render(<Probe chatId="a" routeChatId="a" sendMessage={sendMessage} />);
    await act(async () => { expect(current.restoreComposerDraft({ text: "  ", attachment })).toBe(true); });
    expect(mockSetInput).toHaveBeenCalledWith("  ");
    expect(current.pendingAttachment).toEqual(attachment);
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it.each(["text", "file"])("preserves a newer %s draft and reports why recovery waits", async (newer) => {
    await render(<Probe chatId="a" routeChatId="a" />);
    const replacement = { ...attachment, fileName: "new.pdf", localUri: "file:///new.pdf" };
    if (newer === "text") inputRef.current = "new question";
    else await act(async () => { current.setPendingAttachment(replacement); });
    await act(async () => { expect(current.restoreComposerDraft({ text: "old question", attachment })).toBe(false); });
    expect(mockSetInput).not.toHaveBeenCalled();
    expect(current.pendingAttachment).toEqual(newer === "file" ? replacement : null);
    expect(mockFeedbackError).toHaveBeenCalledWith("chat.restore_draft_blocked");
  });

  it("refuses a restore callback captured before navigation or signout", async () => {
    const view = await render(<Probe chatId="a" routeChatId="a" />);
    const oldRestore = current.restoreComposerDraft;
    await view.rerender(<Probe chatId="b" routeChatId="b" />);
    await act(async () => { expect(oldRestore({ text: "a", attachment })).toBe(false); });
    const beforeSignout = current.restoreComposerDraft;
    (getSessionGeneration as jest.Mock).mockReturnValue(1);
    await act(async () => { expect(beforeSignout({ text: "b", attachment })).toBe(false); });
    expect(mockSetInput).not.toHaveBeenCalled();
  });

  it("retains untrimmed composer text alongside its uploaded attachment for recovery", async () => {
    inputRef.current = "  exact question\n";
    uploadAttachment.mockResolvedValue("uploaded-id");
    const sendMessage = sent();
    await render(<Probe chatId="a" routeChatId="a" sendMessage={sendMessage} />);
    await act(async () => { current.setPendingAttachment(attachment); });
    await act(async () => { await current.handleSend(); });
    expect(sendMessage).toHaveBeenCalledWith("exact question", expect.objectContaining({ composerDraft: {
      text: "  exact question\n", attachment: { ...attachment, existingAttachmentId: "uploaded-id", uploadedForDraft: true },
    } }));
  });
});

describe("useChatSend math scans", () => {
  const scan = {
    localUri: "file:///crop.jpg",
    contentType: "image/jpeg",
    fileName: "math-scan.jpg",
    kind: "image" as const,
  };

  beforeEach(() => {
    jest.clearAllMocks();
    inputRef.current = "";
  });

  async function settle() {
    await new Promise((resolve) => setTimeout(resolve, 0));
  }

  it("solves a confirmed reading as typed text, with no photo", async () => {
    const sendMessage = sent();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    });
    await act(async () => {
      current.handleMathScanSolve("x + y = 5\nx - y = 1");
      await settle();
    });
    expect(sendMessage).toHaveBeenCalledWith("Show steps: x + y = 5, x - y = 1", expect.anything());
    expect(uploadAttachment).not.toHaveBeenCalled();
    expect(current.mathScannerOpen).toBe(false);
  });

  it.each([
    ["chemistry", "Find the molar mass of H2O"],
    ["physics", "A ball is dropped from 80 m. Find its speed just before it hits the ground."],
  ] as const)("solves a confirmed %s reading as the text alone", async (subject, reading) => {
    const sendMessage = sent();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    });
    await act(async () => {
      current.handleMathScanSolve(reading, subject);
      await settle();
    });
    expect(sendMessage).toHaveBeenCalledWith(reading, expect.anything());
    expect(uploadAttachment).not.toHaveBeenCalled();
  });

  it("keeps a typed draft after the scan's text", async () => {
    inputRef.current = "please explain";
    const sendMessage = sent();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    });
    await act(async () => {
      current.handleMathScanSolve("2x = 4");
      await settle();
    });
    expect(sendMessage).toHaveBeenCalledWith("Show steps: 2x = 4\n\nplease explain", expect.anything());
  });

  it("sends the photo with the reading the student checked", async () => {
    uploadAttachment.mockResolvedValue("att-1");
    const sendMessage = sent();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    });
    await act(async () => {
      current.handleMathScanCaptured(scan, "math", "2x = 4");
      await settle();
    });
    expect(uploadAttachment).toHaveBeenCalled();
    expect(sendMessage).toHaveBeenCalledWith(
      "Solve the math problem in this image step by step.\n\nI read this as: 2x = 4",
      expect.anything(),
    );
  });

  it("sends a physics photo with its checked reading under the physics line", async () => {
    uploadAttachment.mockResolvedValue("att-1");
    const sendMessage = sent();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    });
    await act(async () => {
      current.handleMathScanCaptured(scan, "physics", "A ball is dropped from 20 m.");
      await settle();
    });
    expect(sendMessage).toHaveBeenCalledWith(
      "Solve the physics problem in this image step by step.\n\nI read this as: A ball is dropped from 20 m.",
      expect.anything(),
    );
  });

  it("sends a chemistry photo with the reading the student checked", async () => {
    uploadAttachment.mockResolvedValue("att-1");
    const sendMessage = sent();
    await act(async () => {
      render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    });
    await act(async () => {
      current.handleMathScanCaptured(scan, "chemistry", "Find the molar mass of H2O");
      await settle();
    });
    expect(uploadAttachment).toHaveBeenCalled();
    expect(sendMessage).toHaveBeenCalledWith(
      "Solve the chemistry problem in this image step by step.\n\nI read this as: Find the molar mass of H2O",
      expect.anything(),
    );
  });

  it("reads a scan through the API and turns a failure into null", async () => {
    await act(async () => {
      render(<Probe chatId="chat-1" />);
    });
    const controller = new AbortController();
    mockReadScan.mockResolvedValueOnce({ reading: "2x = 4", uncertain: false, source: "mathpix" });
    await expect(current.readScan(scan, "math", controller.signal)).resolves.toEqual({
      reading: "2x = 4",
      uncertain: false,
      source: "mathpix",
    });
    expect(mockReadScan).toHaveBeenCalledWith("token", "math", scan, controller.signal);
    await current.readScan(scan, "physics", controller.signal);
    expect(mockReadScan).toHaveBeenLastCalledWith("token", "physics", scan, controller.signal);
    mockReadScan.mockRejectedValueOnce(new Error("offline"));
    await expect(current.readScan(scan, "math", controller.signal)).resolves.toBeNull();
    mockReadScan.mockRejectedValueOnce(
      new ApiRequestError(429, JSON.stringify({ detail: { code: "scan_rate_limited", message: "Too many scans." } })),
    );
    await expect(current.readScan(scan, "math", controller.signal)).resolves.toEqual({
      error: "chat.scan_rate_limit",
    });
    mockReadScan.mockRejectedValueOnce(
      new ApiRequestError(413, JSON.stringify({ detail: { code: "image_too_large", message: "Image too large" } })),
    );
    await expect(current.readScan(scan, "math", controller.signal)).resolves.toEqual({
      error: "chat.scan_too_large",
    });
    // Every subject names the same refusals: an oversized chemistry or physics photo too.
    mockReadScan.mockRejectedValueOnce(
      new ApiRequestError(413, JSON.stringify({ detail: { code: "image_too_large", message: "Image too large" } })),
    );
    await expect(current.readScan(scan, "chemistry", controller.signal)).resolves.toEqual({
      error: "chat.scan_too_large",
    });
    mockReadScan.mockRejectedValueOnce(
      new ApiRequestError(404, JSON.stringify({ detail: { code: "not_available", message: "Not available" } })),
    );
    await expect(current.readScan(scan, "physics", controller.signal)).resolves.toEqual({
      error: "chat.scan_unavailable",
    });
    mockReadScan.mockRejectedValueOnce(
      new ApiRequestError(429, JSON.stringify({ detail: { code: "scan_rate_limited", message: "Too many scans." } })),
    );
    await expect(current.readScan(scan, "chemistry", controller.signal)).resolves.toEqual({
      error: "chat.scan_rate_limit",
    });
    mockReadScan.mockRejectedValueOnce(
      new ApiRequestError(404, JSON.stringify({ detail: { code: "not_available", message: "Not available" } })),
    );
    await expect(current.readScan(scan, "chemistry", controller.signal)).resolves.toEqual({
      error: "chat.scan_unavailable",
    });
    mockReadScan.mockRejectedValueOnce(new Error("offline"));
    await expect(current.readScan(scan, "chemistry", controller.signal)).resolves.toBeNull();
    mockReadScan.mockRejectedValueOnce(
      new ApiRequestError(500, JSON.stringify({ detail: "vision failed" })),
    );
    await expect(current.readScan(scan, "chemistry", controller.signal)).resolves.toBeNull();
  });
});


describe("useChatSend send steps", () => {
  const file = { localUri: "file://report.pdf", contentType: "application/pdf", fileName: "report.pdf", kind: "file" as const };

  beforeEach(() => {
    jest.clearAllMocks();
    inputRef.current = "hello";
    mockThreadKey = "chat-1";
  });

  async function send() {
    await act(async () => { await current.handleSend(); });
  }

  it("asks the user to wait while a reply streams, and keeps the draft", async () => {
    const onStreamBusy = jest.fn();
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" streaming onStreamBusy={onStreamBusy} sendMessage={sendMessage} />);
    await send();
    expect(onStreamBusy).toHaveBeenCalledTimes(1);
    expect(mockTap).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
    expect(mockSetInput).not.toHaveBeenCalled();
  });

  it("ignores an empty tap while a reply streams", async () => {
    const onStreamBusy = jest.fn();
    inputRef.current = "   ";
    await render(<Probe chatId="chat-1" streaming onStreamBusy={onStreamBusy} />);
    await send();
    expect(onStreamBusy).not.toHaveBeenCalled();
    expect(mockTap).not.toHaveBeenCalled();
  });

  it("reports offline before the stream-busy guard", async () => {
    const onStreamBusy = jest.fn();
    await render(<Probe chatId="chat-1" offline streaming onStreamBusy={onStreamBusy} />);
    await send();
    expect(mockNotifyWarning).toHaveBeenCalledTimes(1);
    expect(onOfflineBlocked).toHaveBeenCalledTimes(1);
    expect(onStreamBusy).not.toHaveBeenCalled();
    expect(mockTap).not.toHaveBeenCalled();
  });

  it.each([
    ["an empty composer", "  ", "token"],
    ["no session", "hello", null],
  ])("sends nothing with %s", async (_label, text, token) => {
    inputRef.current = text;
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" token={token} sendMessage={sendMessage} />);
    await send();
    expect(mockTap).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("does not send while a new chat is being created", async () => {
    const sendMessage = sent();
    const draft = {
      draftChatIdRef: { current: null }, skipLoadForChatIdRef: { current: null }, creatingRef: { current: true },
      prepareDraftChat: jest.fn(), setDraftChatId: jest.fn(), discardEmptyChat: jest.fn(),
    };
    await render(<Probe chatId="chat-1" draft={draft} sendMessage={sendMessage} />);
    await send();
    expect(mockTap).not.toHaveBeenCalled();
    expect(sendMessage).not.toHaveBeenCalled();
  });

  it("sends a tapped line without the composer's half-typed draft or file", async () => {
    // Regression: a follow-up row or a clarify card's answer cleared the draft and sent the file with it.
    inputRef.current = "half typed";
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    await act(async () => { current.setPendingAttachment(file); });
    mockSetInput.mockClear();
    await act(async () => { await current.sendTappedLine("Tell me more"); });
    expect(sendMessage).toHaveBeenCalledWith("Tell me more", expect.objectContaining({
      attachmentIds: undefined, localFileUri: null, composerDraft: { text: "Tell me more", attachment: null },
    }));
    expect(uploadAttachment).not.toHaveBeenCalled();
    expect(mockSetInput).not.toHaveBeenCalled();
    expect(current.pendingAttachment).toEqual(file);
  });

  it("takes back a refused tapped line without touching the composer", async () => {
    inputRef.current = "half typed";
    const setMessages = jest.fn();
    await render(<Probe chatId="chat-1" setMessages={setMessages} sendMessage={jest.fn(async () => false)} />);
    await act(async () => { current.setPendingAttachment(file); });
    mockSetInput.mockClear();
    await act(async () => { await current.handleSend("Tell me more", { leaveComposer: true }); });
    const [bubble] = setMessages.mock.calls[0][0]([]);
    expect(setMessages.mock.calls.at(-1)?.[0]([bubble])).toEqual([]);
    expect(mockSetInput).not.toHaveBeenCalled();
    expect(mockFeedbackError).not.toHaveBeenCalled();
    expect(current.pendingAttachment).toEqual(file);
    expect(current.sendPhase).toBe("idle");
  });

  it("restores a plain send when the email draft flush fails", async () => {
    const setMessages = jest.fn();
    const sendMessage = sent();
    const unregisterFlush = registerEmailDraftFlusher(() => Promise.resolve(false));
    try {
      await render(<Probe chatId="chat-1" setMessages={setMessages} sendMessage={sendMessage} />);
      await send();
    } finally {
      unregisterFlush();
    }
    const rows = setMessages.mock.calls.reduce(
      (prev: Message[], [update]) => (typeof update === "function" ? update(prev) : update),
      [],
    );
    expect(rows).toEqual([]);
    expect(setMessages).toHaveBeenCalledTimes(2);
    expect(mockSetInput).toHaveBeenNthCalledWith(1, "");
    expect(mockSetInput).toHaveBeenLastCalledWith("hello");
    expect(sendMessage).not.toHaveBeenCalled();
    expect(current.pendingOutboundId).toBeNull();
    expect(current.sendPhase).toBe("idle");
  });

  it.each([
    [new AttachmentError("too_large"), "chat.attach_too_large"],
    [new AttachmentError("upload_failed"), "chat.attach_upload_failed"],
    // Raw error text (a network message, a JSON body) never reaches the toast.
    [new Error("{\"detail\":\"Unsupported content type\"}"), "chat.attach_failed"],
    ["not an error", "chat.attach_failed"],
  ])("restores the draft and reports a failed upload (%p)", async (error, message) => {
    uploadAttachment.mockRejectedValueOnce(error);
    const setMessages = jest.fn();
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" setMessages={setMessages} sendMessage={sendMessage} />);
    await act(async () => { current.setPendingAttachment(file); });
    await send();
    expect(uploadAttachment).toHaveBeenCalledWith("token", file);
    expect(mockFeedbackError).toHaveBeenCalledWith(message);
    expect(mockSetInput).toHaveBeenLastCalledWith("hello");
    expect(current.pendingAttachment).toEqual(file);
    expect(setMessages).toHaveBeenCalledTimes(2);
    expect(sendMessage).not.toHaveBeenCalled();
    expect(current.sendPhase).toBe("idle");
  });

  it("restores the draft when the server makes no new chat", async () => {
    const prepareDraftChat = jest.fn().mockResolvedValue(null);
    await render(<Probe prepareDraftChat={prepareDraftChat} />);
    await send();
    expect(prepareDraftChat).toHaveBeenCalledWith();
    expect(mockFeedbackError).toHaveBeenCalledWith("chat.error_generic");
    expect(mockSetInput).toHaveBeenLastCalledWith("hello");
    expect(mockSetChatId).not.toHaveBeenCalled();
    expect(current.sendPhase).toBe("idle");
  });

  it("makes a new draft chat the open one, then routes to it", async () => {
    const draft = {
      draftChatIdRef: { current: "created-1" as string | null }, skipLoadForChatIdRef: { current: null as string | null },
      creatingRef: { current: false }, prepareDraftChat: jest.fn(), setDraftChatId: jest.fn(), discardEmptyChat: jest.fn(),
    };
    let creatingDuringPrepare: boolean | null = null;
    draft.prepareDraftChat.mockImplementation(async () => {
      creatingDuringPrepare = draft.creatingRef.current;
      return "created-1";
    });
    mockThreadKey = "new";
    await render(<Probe draft={draft} />);
    await send();
    expect(creatingDuringPrepare).toBe(true);
    expect(draft.creatingRef.current).toBe(false);
    expect(draft.skipLoadForChatIdRef.current).toBe("created-1");
    expect(draft.draftChatIdRef.current).toBeNull();
    const order = [mockSetChatTitle, mockSetChatId, draft.setDraftChatId, mockAdoptComposerThread, mockSetParams]
      .map((fn) => fn.mock.invocationCallOrder[0]);
    expect(order).toEqual([...order].sort((a, b) => a - b));
    expect(mockSetChatTitle).toHaveBeenCalledWith(null);
    expect(mockSetChatId).toHaveBeenCalledWith("created-1");
    expect(draft.setDraftChatId).toHaveBeenCalledWith(null);
    expect(mockSetParams).toHaveBeenCalledWith({ chatId: "created-1" });
    expect(current.sendPhase).toBe("creating");
    expect(current.pendingOutboundId).toMatch(/^local-/);
  });

  it("discards a draft chat created for a view the user left", async () => {
    let finishCreate!: (id: string) => void;
    const draft = {
      draftChatIdRef: { current: null as string | null }, skipLoadForChatIdRef: { current: null },
      creatingRef: { current: false }, setDraftChatId: jest.fn(), discardEmptyChat: jest.fn(),
      prepareDraftChat: jest.fn(() => new Promise<string>((resolve) => { finishCreate = resolve; })),
    };
    mockThreadKey = "new";
    const view = await render(<Probe draft={draft} />);
    let sending!: Promise<boolean>;
    await act(async () => {
      sending = current.handleSend();
      await Promise.resolve();
      await Promise.resolve();
    });
    draft.draftChatIdRef.current = "created-1";
    mockThreadKey = "chat-2";
    await view.rerender(<Probe chatId="chat-2" routeChatId="chat-2" draft={draft} />);
    await act(async () => { finishCreate("created-1"); await sending; });
    expect(draft.draftChatIdRef.current).toBeNull();
    expect(draft.setDraftChatId).toHaveBeenCalledWith(null);
    expect(draft.discardEmptyChat).toHaveBeenCalledWith("created-1");
    expect(mockStashFailedDraftForThread).toHaveBeenCalledWith("new", "hello");
    expect(draft.creatingRef.current).toBe(false);
  });

  it("dispatches the turn with everything the transport needs", async () => {
    const setMessages = jest.fn();
    const sendMessage = sent();
    inputRef.current = "  coffee near me ";
    await render(<Probe chatId="chat-1" setMessages={setMessages} sendMessage={sendMessage} />);
    await send();
    const [bubble] = setMessages.mock.calls[0][0]([]);
    expect(bubble).toMatchObject({ id: expect.stringMatching(/^local-/), role: "user", content: "coffee near me" });
    expect(sendMessage).toHaveBeenCalledWith("coffee near me", {
      text: "coffee near me",
      composerDraft: { text: "  coffee near me ", attachment: null },
      skipUserBubble: true,
      trackSendingMessageId: bubble.id,
      attachmentIds: undefined,
      localImageUri: null,
      localFileUri: null,
      localFileName: null,
      localFileContentType: null,
    });
    expect(mockSetInput).toHaveBeenCalledWith("");
    expect(current.pendingOutboundId).toBeNull();
    expect(current.sendPhase).toBe("idle");
  });

  it("paints the bubble, empties the composer and raises the dots before the send goes out", async () => {
    inputRef.current = "draw ethanol";
    const hold = holdAtDraftFlush();
    const setMessages = jest.fn();
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" setMessages={setMessages} sendMessage={sendMessage} />);
    let sending!: Promise<boolean>;
    await act(async () => { sending = current.handleSend(); });

    expect(setMessages).toHaveBeenCalledTimes(1);
    expect(mockSetInput).toHaveBeenCalledWith("");
    expect(beginDots).toHaveBeenCalledTimes(1);
    const [bubble] = setMessages.mock.calls[0][0]([]);
    expect(bubble).toMatchObject({ role: "user", content: "draw ethanol" });
    // Painted in the tap's own tick, before the send waits on anything.
    expect(mockTap.mock.invocationCallOrder[0]).toBeLessThan(setMessages.mock.invocationCallOrder[0]);
    expect(sendMessage).not.toHaveBeenCalled();

    await act(async () => { hold.release(true); await sending; });
    expect(sendMessage).toHaveBeenCalledWith("draw ethanol", expect.objectContaining({ trackSendingMessageId: bubble.id }));
    // The dots stay up for the turn they announced.
    expect(cancelDots).not.toHaveBeenCalled();
    expect(setMessages).toHaveBeenCalledTimes(1);
  });

  it("gives the draft back when Stop took the dots down before the turn went out", async () => {
    inputRef.current = "draw ethanol";
    const hold = holdAtDraftFlush();
    const setMessages = jest.fn();
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" setMessages={setMessages} sendMessage={sendMessage} />);
    let sending!: Promise<boolean>;
    await act(async () => { sending = current.handleSend(); });
    dotsUp = false;
    await act(async () => { hold.release(true); await sending; });
    expect(sendMessage).not.toHaveBeenCalled();
    const rows = setMessages.mock.calls.reduce(
      (prev: Message[], [update]) => (typeof update === "function" ? update(prev) : update),
      [],
    );
    expect(rows).toEqual([]);
    expect(mockSetInput).toHaveBeenLastCalledWith("draw ethanol");
    expect(current.sendPhase).toBe("idle");
  });

  it("still sends when no dots could go up with the bubble", async () => {
    beginDots.mockReturnValueOnce(null);
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    await send();
    expect(sendMessage).toHaveBeenCalledWith("hello", expect.objectContaining({ skipUserBubble: true }));
    expect(current.sendPhase).toBe("idle");
  });

  it("sends a turn made while the last reply saves once that reply's done is in", async () => {
    beginDots.mockReturnValueOnce(null);
    let replySaved!: () => void;
    whenReplySettled.mockReturnValueOnce(new Promise<void>((resolve) => { replySaved = resolve; }));
    const setMessages = jest.fn();
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" setMessages={setMessages} sendMessage={sendMessage} />);
    let sending!: Promise<boolean>;
    await act(async () => { sending = current.handleSend(); });
    // The bubble is up and the composer free; the turn waits, its bubble saying so.
    const [bubble] = setMessages.mock.calls[0][0]([]);
    expect(mockSetInput).toHaveBeenCalledWith("");
    expect(whenReplySettled).toHaveBeenCalledWith(bubble.id);
    expect(sendMessage).not.toHaveBeenCalled();
    expect(current.sendPhase).toBe("preparing");
    await act(async () => { replySaved(); await sending; });
    expect(sendMessage).toHaveBeenCalledWith("hello", expect.objectContaining({ trackSendingMessageId: bubble.id }));
    expect(current.sendPhase).toBe("idle");
  });

  it("does not wait for any reply when the dots went up with the bubble", async () => {
    const sendMessage = sent();
    await render(<Probe chatId="chat-1" sendMessage={sendMessage} />);
    await send();
    expect(whenReplySettled).not.toHaveBeenCalled();
    expect(sendMessage).toHaveBeenCalledTimes(1);
  });

  it("starts the time-to-first-token sample at the tap and marks the bubble's frame", async () => {
    const start = jest.spyOn(latency, "markChatTtftStart");
    const painted = jest.spyOn(latency, "markChatBubblePainted");
    const setMessages = jest.fn();
    await render(<Probe chatId="chat-1" setMessages={setMessages} />);
    const before = Date.now();
    await send();
    const [bubble] = setMessages.mock.calls[0][0]([]);
    const tappedAt = start.mock.calls[0][1];
    expect(start).toHaveBeenCalledWith(bubble.id, tappedAt, false);
    expect(tappedAt).toBeGreaterThanOrEqual(before);
    expect(bubble.id).toBe(`local-${tappedAt}`);
    expect(start.mock.invocationCallOrder[0]).toBeLessThan(setMessages.mock.invocationCallOrder[0]);
    await act(async () => { await new Promise((resolve) => setTimeout(resolve, 50)); });
    expect(painted).toHaveBeenCalledWith(bubble.id);
    start.mockRestore();
    painted.mockRestore();
  });

  it("gives the draft back as typed when the chat refuses the send (a regenerate began first)", async () => {
    inputRef.current = "  hello there\n";
    const setMessages = jest.fn();
    const sendMessage = jest.fn(async () => false);
    await render(<Probe chatId="chat-1" setMessages={setMessages} sendMessage={sendMessage} />);
    await send();
    expect(sendMessage).toHaveBeenCalledWith("hello there", expect.anything());
    const rows = setMessages.mock.calls.reduce(
      (prev: Message[], [update]) => (typeof update === "function" ? update(prev) : update),
      [],
    );
    expect(rows).toEqual([]);
    expect(cancelDots).toHaveBeenCalledTimes(1);
    expect(mockSetInput).toHaveBeenLastCalledWith("  hello there\n");
    expect(current.sendPhase).toBe("idle");
    expect(current.pendingOutboundId).toBeNull();
  });

  it("gives the draft back when Stop takes back a send still waiting to go out (its chat's page)", async () => {
    inputRef.current = "  next question\n";
    let stop!: (sent: boolean) => void;
    const sendMessage = jest.fn(() => new Promise<boolean>((resolve) => { stop = resolve; }));
    const setMessages = jest.fn();
    await render(<Probe chatId="chat-1" setMessages={setMessages} sendMessage={sendMessage} />);
    let sending!: Promise<boolean>;
    await act(async () => { sending = current.handleSend(); });
    // Handed over and waiting: Send is idle again, so Stop shows.
    expect(sendMessage).toHaveBeenCalledWith("next question", expect.anything());
    expect(current.sendPhase).toBe("idle");
    expect(mockSetInput).toHaveBeenLastCalledWith("");
    // Stop: the chat takes the turn back and says so.
    await act(async () => { stop(false); await sending; });
    const rows = setMessages.mock.calls.reduce(
      (prev: Message[], [update]) => (typeof update === "function" ? update(prev) : update),
      [],
    );
    expect(rows).toEqual([]);
    expect(mockSetInput).toHaveBeenLastCalledWith("  next question\n");
    expect(current.pendingOutboundId).toBeNull();
  });

  it("says why a given-back draft stays out of a composer that has newer text", async () => {
    const held = holdAtDraftFlush();
    inputRef.current = "coffee near me";
    await render(<Probe chatId="chat-1" />);
    let sending!: Promise<boolean>;
    await act(async () => { sending = current.handleSend(); });
    inputRef.current = "follow-up";
    await act(async () => { held.release(false); await sending; });
    expect(mockSetInput).not.toHaveBeenCalledWith("coffee near me");
    expect(mockFeedbackError).toHaveBeenCalledWith("chat.restore_draft_blocked");
    expect(current.sendPhase).toBe("idle");
  });

});
