import React, { useLayoutEffect } from "react";
import { Linking, Text } from "react-native";
import { act, render } from "@testing-library/react-native";

import { useChatSend } from "@/features/chat/hooks/useChatSend";
import { AttachmentError } from "@/features/attachments/model/attachmentErrors";
import {
  NativePickerBusyError,
  NativePickerTimeoutError,
  PhotoLibraryPermissionError,
  pickDocument,
  pickFromCamera,
  pickFromPhotoLibrary,
} from "@/features/attachments/model/attachments";

// Pins the attach sheet and picker error mapping that useChatSend exposes
// (handlePickAttachment, handleAttachmentSheetSelect, mathScannerOpen).

jest.mock("@/lib/auth", () => ({ getSessionGeneration: jest.fn(() => 0) }));
const inputRef = { current: "" };
jest.mock("@/features/chat/context/ComposerDraftContext", () => ({
  useComposerDraftApi: () => ({
    setInput: jest.fn(),
    inputRef,
    switchThread: jest.fn(),
    adoptComposerThread: jest.fn(),
    stashFailedDraftForThread: jest.fn(),
    resetForNewSession: jest.fn(),
    getThreadKey: () => "chat-1",
  }),
}));
const mockFeedback = { error: jest.fn(), warning: jest.fn() };
jest.mock("@/contexts/ActionFeedbackContext", () => ({
  useActionFeedbackOptional: () => mockFeedback,
}));
jest.mock("expo-router", () => ({ useRouter: () => ({ setParams: jest.fn() }) }));
jest.mock("@/features/attachments/model/attachments", () => ({
  pickDocument: jest.fn(),
  pickFromCamera: jest.fn(),
  pickFromPhotoLibrary: jest.fn(),
  uploadChatAttachment: jest.fn(),
  messageTextForSend: jest.fn((text: string) => text),
  discardDraftAttachment: jest.fn(),
  NativePickerBusyError: class extends Error {},
  NativePickerTimeoutError: class extends Error {},
  PhotoLibraryPermissionError: class extends Error {
    readonly needsSettings: boolean;
    constructor(needsSettings: boolean) {
      super("PHOTO_LIBRARY_PERMISSION");
      this.needsSettings = needsSettings;
    }
  },
}));
jest.mock("@/lib/api", () => ({ api: { readScan: jest.fn(), imageIntent: jest.fn() } }));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn(), notifyWarning: jest.fn() }));
jest.mock("@/features/chat/model/resolveClientGeoForQuery", () => ({
  queryNeedsClientGeo: jest.fn(() => false),
  resolveClientGeoForQuery: jest.fn(async () => ({ ok: true, clientGeo: null })),
}));
jest.mock("@/features/attachments/model/pendingComposerAttachment", () => ({
  subscribeComposerAttachmentQueue: () => () => undefined,
  takeQueuedComposerAttachment: () => null,
}));

const photo = { localUri: "file://pic.jpg", contentType: "image/jpeg", fileName: "pic.jpg", kind: "image" as const };
let current: ReturnType<typeof useChatSend>;

function Probe({ streaming = false, token = "token" }: { streaming?: boolean; token?: string | null }) {
  const result = useChatSend({
    token,
    chatId: "chat-1",
    routeChatId: "chat-1",
    setChatId: jest.fn(),
    setChatTitle: jest.fn(),
    router: { setParams: jest.fn() } as never,
    draft: {
      draftChatIdRef: { current: null },
      skipLoadForChatIdRef: { current: null },
      creatingRef: { current: false },
      prepareDraftChat: jest.fn(),
      setDraftChatId: jest.fn(),
      discardEmptyChat: jest.fn(),
    } as never,
    scroll: { newMessageCountRef: { current: 0 } } as never,
    streaming,
    sendMessage: jest.fn(async () => true),
    sendStart: { beginDots: () => null, whenReplySettled: async () => undefined },
    editThread: jest.fn(),
    messages: [],
    selectedModel: "free-chat",
    updateUser: jest.fn(),
    t: (key) => key,
    isOffline: false,
  });
  useLayoutEffect(() => { current = result; });
  return <Text>send</Text>;
}

async function select(source: Parameters<typeof current.handleAttachmentSheetSelect>[0]) {
  await act(async () => { await current.handleAttachmentSheetSelect(source); });
}

beforeEach(() => {
  jest.clearAllMocks();
  inputRef.current = "";
});

it.each([
  ["camera", pickFromCamera],
  ["photo", pickFromPhotoLibrary],
  ["file", pickDocument],
] as const)("the %s source runs its picker and queues the pick", async (source, picker) => {
  (picker as jest.Mock).mockResolvedValueOnce(photo);
  await render(<Probe />);
  await select(source);
  expect(picker).toHaveBeenCalledTimes(1);
  expect(current.pendingAttachment).toEqual(photo);
  expect(current.attachSheetOpen).toBe(false);
});

it("opens the math scanner instead of a picker", async () => {
  await render(<Probe />);
  await act(async () => { current.setAttachSheetOpen(true); });
  await select("solve_math_camera");
  expect(current.mathScannerOpen).toBe(true);
  expect(current.attachSheetOpen).toBe(false);
  expect(pickFromCamera).not.toHaveBeenCalled();
});

it.each([
  ["a busy picker", new NativePickerBusyError(), "error", "chat.picker_busy"],
  ["a picker timeout", new NativePickerTimeoutError(), "error", "chat.picker_busy"],
  ["a photo permission", new PhotoLibraryPermissionError(false), "error", "chat.photos_permission"],
  ["a file too large says so", new AttachmentError("too_large"), "error", "chat.attach_too_large"],
  // Untyped failures get the generic message, never raw error text.
  ["any other error says attach failed", new Error("disk full"), "error", "chat.attach_failed"],
  ["a non-error says attach failed", "boom", "error", "chat.attach_failed"],
] as const)("%s", async (_name, failure, tone, message) => {
  (pickFromPhotoLibrary as jest.Mock).mockRejectedValueOnce(failure);
  await render(<Probe />);
  await select("photo");
  expect(mockFeedback[tone]).toHaveBeenCalledWith(message);
  expect(current.pendingAttachment).toBeNull();
});

it("a pick being prepared shows as attachPicking until it lands", async () => {
  let land: (value: typeof photo) => void = () => undefined;
  (pickFromPhotoLibrary as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { land = resolve; }));
  await render(<Probe />);
  let picking: Promise<void> = Promise.resolve();
  await act(async () => { picking = current.handleAttachmentSheetSelect("photo"); });
  // Send waits on this: a send that slipped in first went without the photo.
  expect(current.attachPicking).toBe(true);
  await act(async () => {
    land(photo);
    await picking;
  });
  expect(current.attachPicking).toBe(false);
  expect(current.pendingAttachment).toEqual(photo);
});

it("sends a denied photo permission to Settings when it needs them", async () => {
  const openSettings = jest.spyOn(Linking, "openSettings").mockResolvedValue(undefined);
  const denied = new PhotoLibraryPermissionError(true);
  (pickFromPhotoLibrary as jest.Mock).mockRejectedValueOnce(denied);
  await render(<Probe />);
  await select("photo");
  expect(openSettings).toHaveBeenCalledTimes(1);
  expect(mockFeedback.error).toHaveBeenCalledWith("chat.photos_permission");
  openSettings.mockRestore();
});

it("ignores a pick while a reply streams or signed out", async () => {
  const view = await render(<Probe streaming />);
  await select("photo");
  await view.rerender(<Probe token={null} />);
  await select("photo");
  expect(pickFromPhotoLibrary).not.toHaveBeenCalled();
});

it("opens the attach sheet on the next frame, and not while streaming", async () => {
  const frames: FrameRequestCallback[] = [];
  const raf = jest
    .spyOn(globalThis, "requestAnimationFrame")
    .mockImplementation((callback) => { frames.push(callback); return frames.length; });
  try {
    const view = await render(<Probe />);
    await act(async () => { current.handlePickAttachment(); });
    expect(current.attachSheetOpen).toBe(false);
    await act(async () => { frames.splice(0).forEach((frame) => frame(0)); });
    expect(current.attachSheetOpen).toBe(true);

    await act(async () => { current.setAttachSheetOpen(false); });
    await view.rerender(<Probe streaming />);
    await act(async () => { current.handlePickAttachment(); });
    expect(frames).toHaveLength(0);
  } finally {
    raf.mockRestore();
  }
});
