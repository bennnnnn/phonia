import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";
import { useGalleryLibrary } from "@/features/attachments/hooks/useGalleryLibrary";
import type { AttachmentListItem } from "@/lib/api";
import { pendingFromLibraryItem } from "@/features/attachments/model/pendingFromLibraryItem";
import { queueComposerAttachment } from "@/features/attachments/model/pendingComposerAttachment";
import { notifyDestructive, selection, tap } from "@/lib/haptics";
import { ApiRequestError } from "@/lib/api/errorBody";
import fixture from "../../../../../../docs/fixtures/error_codes.json";

let mockSession = 0;
const mockBack = jest.fn();
const mockReplace = jest.fn();
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/contexts/AuthContext", () => ({ useAuthToken: () => "token" }));
const mockFeedback = { error: jest.fn(), success: jest.fn(), info: jest.fn(), warning: jest.fn(), show: jest.fn(), dismiss: jest.fn() };
let mockFeedbackEnabled = false;
jest.mock("@/contexts/actionFeedbackCore", () => ({
  useActionFeedbackOptional: () => (mockFeedbackEnabled ? mockFeedback : null),
}));
jest.mock("@/ui/overlay/dialogs", () => ({
  confirmDialog: jest.fn(async () => true),
  alertDialog: jest.fn(async () => undefined),
}));
jest.mock("expo-router", () => {
  const { useEffect } = jest.requireActual<typeof import("react")>("react");
  return {
    useRouter: () => ({ canGoBack: () => true, back: mockBack, replace: mockReplace }),
    useLocalSearchParams: () => ({ composerThread: "origin" }),
    useFocusEffect: (callback: () => void) => useEffect(callback, [callback]),
  };
});
jest.mock("@/lib/api", () => ({ api: { deleteAttachment: jest.fn() } }));
jest.mock("@/features/attachments/model/pendingFromLibraryItem", () => ({ pendingFromLibraryItem: jest.fn() }));
jest.mock("@/features/attachments/model/pendingComposerAttachment", () => ({ queueComposerAttachment: jest.fn() }));
jest.mock("@/features/attachments/model/galleryLayout", () => ({ getGalleryLayout: async () => "grid", peekGalleryLayout: () => "grid", setGalleryLayout: jest.fn() }));
jest.mock("@/features/chat/model/messageCache", () => ({ clearCachedChatMessages: jest.fn() }));
jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({ shareChatAttachment: jest.fn() }));
let mockUri: string | null = "file://attachment";
jest.mock("@/features/attachments/model/attachmentUri", () => ({ resolveAttachmentUri: () => mockUri }));
jest.mock("@/lib/haptics", () => ({ selection: jest.fn(), tap: jest.fn(), notifyDestructive: jest.fn() }));
const item = { id: "one", content_type: "image/png" } as AttachmentListItem;
const pending = { localUri: "file://image.png", fileName: "image.png", kind: "image", contentType: "image/png" };
let current: ReturnType<typeof useGalleryLibrary>;
function Probe() {
  const result = useGalleryLibrary([item], jest.fn());
  React.useLayoutEffect(() => { current = result; }, [result]);
  return <Text>Library</Text>;
}
beforeEach(() => { jest.clearAllMocks(); mockSession = 0; mockFeedbackEnabled = false; mockUri = "file://attachment"; });

it("does not navigate or queue a Library attachment after leaving", async () => {
  let finish!: (value: unknown) => void;
  (pendingFromLibraryItem as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const view = await render(<Probe />);
  let selecting!: Promise<void>;
  await act(async () => { selecting = current.attachToComposer(item); });
  await view.unmount();
  await act(async () => { finish(pending); await selecting; });
  expect(queueComposerAttachment).not.toHaveBeenCalled();
  expect(mockBack).not.toHaveBeenCalled();
  expect(mockReplace).not.toHaveBeenCalled();
});

it("does not deliver a previous account's pending Library attachment", async () => {
  let finish!: (value: unknown) => void;
  (pendingFromLibraryItem as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
  const view = await render(<Probe />);
  let selecting!: Promise<void>;
  await act(async () => { selecting = current.attachToComposer(item); });
  mockSession++;
  await view.rerender(<Probe />);
  await act(async () => { finish(pending); await selecting; });
  expect(queueComposerAttachment).not.toHaveBeenCalled();
  expect(mockBack).not.toHaveBeenCalled();
});

it("delivers a successful Library pick to its originating composer", async () => {
  (pendingFromLibraryItem as jest.Mock).mockResolvedValueOnce(pending);
  await render(<Probe />);
  await act(async () => { await current.attachToComposer(item); });
  expect(queueComposerAttachment).toHaveBeenCalledWith(pending, "origin");
  expect(mockBack).toHaveBeenCalledTimes(1);
});

it("opens a PDF for reading instead of the action sheet", async () => {
  const pdf = { id: "doc", content_type: "application/pdf" } as AttachmentListItem;
  function FileProbe() {
    const result = useGalleryLibrary([pdf], jest.fn());
    React.useLayoutEffect(() => { current = result; }, [result]);
    return <Text>Library</Text>;
  }
  await render(<FileProbe />);
  await act(async () => { current.openFile(pdf); });
  expect(current.fileItem?.id).toBe("doc");
  expect(current.actionItem).toBeNull();
});

it("shares a spreadsheet on tap because it cannot be previewed in-app", async () => {
  const { shareChatAttachment } = jest.requireMock("@/features/attachments/model/downloadChatAttachment") as {
    shareChatAttachment: jest.Mock;
  };
  const sheet = {
    id: "xlsx",
    content_type: "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    download_url: "/attachments/xlsx/file",
  } as AttachmentListItem;
  function FileProbe() {
    const result = useGalleryLibrary([sheet], jest.fn());
    React.useLayoutEffect(() => { current = result; }, [result]);
    return <Text>Library</Text>;
  }
  await render(<FileProbe />);
  await act(async () => { await current.openFile(sheet); });
  expect(shareChatAttachment).toHaveBeenCalled();
  expect(current.fileItem).toBeNull();
});

describe("the photo viewer follows the photo on screen", () => {
  const photo = (id: string) => ({ id, content_type: "image/png", download_url: `/attachments/${id}/file` }) as AttachmentListItem;
  const photos = [photo("a"), photo("b"), photo("c")];
  function ViewerProbe({ items = photos, removeItem = jest.fn() }: { items?: AttachmentListItem[]; removeItem?: (id: string) => void }) {
    const result = useGalleryLibrary(items, removeItem);
    React.useLayoutEffect(() => { current = result; }, [result]);
    return <Text>Library</Text>;
  }

  it("stays open on the next photo after deleting one the user swiped to", async () => {
    const { api } = jest.requireMock("@/lib/api") as { api: { deleteAttachment: jest.Mock } };
    api.deleteAttachment.mockResolvedValueOnce(undefined);
    const removeItem = jest.fn();
    await render(<ViewerProbe removeItem={removeItem} />);
    await act(async () => { current.openImage(photos[0]); });
    // The viewer reports the photo the user paged to.
    await act(async () => { current.setViewerId("b"); });
    await act(async () => { current.confirmDelete(photos[1]); });
    await act(async () => { await Promise.resolve(); });
    expect(api.deleteAttachment).toHaveBeenCalledWith("token", "b");
    expect(removeItem).toHaveBeenCalledWith("b");
    expect(current.viewerItem?.id).toBe("c");
  });

  it("plays one destructive haptic once a delete lands, as a chat or a to-do does, and none when it fails", async () => {
    const { api } = jest.requireMock("@/lib/api") as { api: { deleteAttachment: jest.Mock } };
    api.deleteAttachment.mockResolvedValueOnce(undefined).mockRejectedValueOnce(new Error("offline"));
    await render(<ViewerProbe />);
    await act(async () => { current.confirmDelete(photos[0]); });
    await act(async () => { await Promise.resolve(); });
    expect(notifyDestructive).toHaveBeenCalledTimes(1);
    await act(async () => { current.confirmDelete(photos[1]); });
    await act(async () => { await Promise.resolve(); });
    expect(api.deleteAttachment).toHaveBeenCalledTimes(2);
    expect(notifyDestructive).toHaveBeenCalledTimes(1);
  });

  // The server's English showed: "Too many requests. Please slow down.", the outage body's.
  it.each([
    ["rate_limited", "chat.rate_limited"],
    ["refresh_rate_limited", "chat.rate_limited"],
    ["service_unavailable", "common.service_unavailable"],
    ["not_found", "gallery.delete_failed"],
  ] as const)("words a delete refused by %s in the phone's language", async (name, line) => {
    const { api } = jest.requireMock("@/lib/api") as { api: { deleteAttachment: jest.Mock } };
    const refusal = name === "not_found"
      ? { status: 404, detail: { code: "not_found", message: "Not found" } }
      : fixture[name];
    api.deleteAttachment.mockRejectedValueOnce(new ApiRequestError(refusal.status, JSON.stringify({ detail: refusal.detail })));
    mockFeedbackEnabled = true;
    await render(<ViewerProbe />);
    await act(async () => { current.confirmDelete(photos[0]); });
    await act(async () => { await Promise.resolve(); });
    expect(mockFeedback.error).toHaveBeenCalledWith(line);
  });

  it("closes after deleting the only photo", async () => {
    const { api } = jest.requireMock("@/lib/api") as { api: { deleteAttachment: jest.Mock } };
    api.deleteAttachment.mockResolvedValueOnce(undefined);
    const only = [photo("solo")];
    await render(<ViewerProbe items={only} />);
    await act(async () => { current.openImage(only[0]); });
    await act(async () => { current.confirmDelete(only[0]); });
    await act(async () => { await Promise.resolve(); });
    expect(current.viewerItem).toBeNull();
  });

  it("keeps the viewer on its photo when another item is deleted", async () => {
    const { api } = jest.requireMock("@/lib/api") as { api: { deleteAttachment: jest.Mock } };
    api.deleteAttachment.mockResolvedValueOnce(undefined);
    await render(<ViewerProbe />);
    await act(async () => { current.openImage(photos[2]); });
    await act(async () => { current.confirmDelete(photos[0]); });
    await act(async () => { await Promise.resolve(); });
    expect(current.viewerItem?.id).toBe("c");
  });
});

describe("visible feedback instead of silent no-ops", () => {
  it("says so when an item has no address to share", async () => {
    mockFeedbackEnabled = true;
    mockUri = null;
    const { shareChatAttachment } = jest.requireMock("@/features/attachments/model/downloadChatAttachment") as {
      shareChatAttachment: jest.Mock;
    };
    await render(<Probe />);
    await act(async () => { await current.shareFile(item); });
    expect(shareChatAttachment).not.toHaveBeenCalled();
    expect(mockFeedback.error).toHaveBeenCalledWith("common.share_failed");
  });

  it("marks the item busy while it is shared, and shares one at a time", async () => {
    const { shareChatAttachment } = jest.requireMock("@/features/attachments/model/downloadChatAttachment") as {
      shareChatAttachment: jest.Mock;
    };
    let finish!: () => void;
    shareChatAttachment.mockReturnValueOnce(new Promise<void>((resolve) => { finish = resolve; }));
    await render(<Probe />);
    let sharing!: Promise<void>;
    await act(async () => { sharing = current.shareFile(item); });
    expect(current.busyItemId).toBe("one");
    await act(async () => { await current.shareFile(item); });
    expect(shareChatAttachment).toHaveBeenCalledTimes(1);
    expect(shareChatAttachment).toHaveBeenCalledWith(expect.objectContaining({ contentType: "image/png" }));
    await act(async () => { finish(); await sharing; });
    expect(current.busyItemId).toBeNull();
  });

  it("marks the item busy while a pick is attached", async () => {
    let finish!: (value: unknown) => void;
    (pendingFromLibraryItem as jest.Mock).mockReturnValueOnce(new Promise((resolve) => { finish = resolve; }));
    await render(<Probe />);
    let selecting!: Promise<void>;
    await act(async () => { selecting = current.attachToComposer(item); });
    expect(current.busyItemId).toBe("one");
    await act(async () => { finish(pending); await selecting; });
    expect(current.busyItemId).toBeNull();
  });
});

it("opens an item's actions on long-press with the tap every long-press menu uses", async () => {
  await render(<Probe />);
  await act(async () => { current.openActions(item, { x: 10, y: 20 }); });
  expect(current.actionItem?.id).toBe("one");
  expect(tap).toHaveBeenCalledTimes(1);
  expect(selection).not.toHaveBeenCalled();
});
