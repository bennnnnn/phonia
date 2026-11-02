import { act, fireEvent, render } from "@testing-library/react-native";
import { type ImageProps, StyleSheet } from "react-native";
import * as Reanimated from "react-native-reanimated";

import { ChatMessageImage } from "@/features/attachments/components/ChatMessageImage";
import { ComposerAttachmentPreview } from "@/features/attachments/components/ComposerAttachmentPreview";
import { fitAttachmentImage } from "@/features/attachments/model/attachmentImageSize";
import { resolveAttachmentUri } from "@/features/attachments/model/attachmentUri";
import type { PendingAttachment } from "@/features/attachments/model/attachments";
import { ensureLocalAttachmentFile } from "@/features/attachments/model/downloadChatAttachment";

jest.mock("@/ui/icons/Icon", () => ({ Icon: "Icon" }));
jest.mock("@/features/attachments/components/AttachmentImageViewer", () => {
  const { View: MockView } = jest.requireActual("react-native");
  return { AttachmentImageViewer: ({ visible }: { visible: boolean }) => visible ? <MockView testID="image-viewer" /> : null };
});
jest.mock("@/contexts/AuthContext", () => ({ useAuthToken: () => "test-token" }));
jest.mock("@/features/attachments/model/attachmentUri", () => ({
  resolveAttachmentUri: jest.fn(({ localUri, path, attachmentId }: { localUri?: string; path?: string; attachmentId?: string }) => localUri || path || (attachmentId ? `https://api.test/attachments/${attachmentId}/file` : null)),
  attachmentRequestHeaders: (uri: string) => uri.startsWith("https://api.test/") ? { Authorization: "Bearer test-token" } : {},
}));
jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({ ensureLocalAttachmentFile: jest.fn().mockResolvedValue("file:///cached.jpg") }));
jest.mock("@/lib/motion", () => ({ motionMs: (value: number) => value, useReduceMotion: () => false }));
jest.mock("react-native-reanimated", () => {
  const { Image: MockImage } = jest.requireActual("react-native");
  return {
    __esModule: true,
    default: { createAnimatedComponent: () => (props: ImageProps) => <MockImage testID="animated-image" {...props} /> },
    Easing: { out: (value: unknown) => value, ease: "ease" },
    useAnimatedStyle: (fn: () => unknown) => fn(),
    useSharedValue: (value: number) => ({ value }),
    withTiming: jest.fn((value: number) => value),
  };
});

const load = (width: number, height: number) => ({ nativeEvent: { source: { width, height, uri: "decoded" } } });
const photo = (localUri: string): PendingAttachment => ({ kind: "image", localUri, fileName: "scan.jpg", contentType: "image/jpeg" });

describe("decoded attachment frame proportions", () => {
  it.each([
    [1200, 300, 148, 37],
    [300, 1200, 47.25, 189],
    [800, 800, 148, 148],
  ])("fits %s by %s inside both chat limits", async (width, height, expectedWidth, expectedHeight) => {
    const view = await render(<ChatMessageImage localUri="file:///scan.jpg" previewFit="contain" width={148} height={189} />);
    await fireEvent(view.getByTestId("chat-image-preview"), "load", load(width, height));
    expect(view.getByTestId("chat-image-frame")).toHaveStyle({ width: expectedWidth, height: expectedHeight });
    expect(view.getByTestId("chat-image-preview").props.resizeMode).toBe("contain");
  });

  it("leaves display to the image cache and downloads nothing for a chat thumbnail", async () => {
    jest.mocked(ensureLocalAttachmentFile).mockClear();
    await render(<ChatMessageImage attachmentId="a" animatedReveal={false} />);
    expect(ensureLocalAttachmentFile).not.toHaveBeenCalled();
  });

  it("uses authenticated remote onLoad dimensions and requests a 2x-width server thumb", async () => {
    const view = await render(<ChatMessageImage attachmentId="a" animatedReveal={false} previewFit="contain" width={148} height={189} />);
    expect(resolveAttachmentUri).toHaveBeenLastCalledWith({ attachmentId: "a", localUri: undefined, path: undefined, width: 296 });
    expect(view.getByTestId("chat-image-preview").props.source).toEqual({ uri: "https://api.test/attachments/a/file", headers: { Authorization: "Bearer test-token" } });
    await fireEvent(view.getByTestId("chat-image-preview"), "load", load(1600, 900));
    expect(view.getByTestId("chat-image-frame")).toHaveStyle({ width: 148, height: 83.25 });
  });

  it("resets when a local image is replaced and ignores the old image's late events", async () => {
    const view = await render(<ChatMessageImage localUri="file:///old.jpg" previewFit="contain" width={148} height={189} />);
    const staleLoad = view.getByTestId("chat-image-preview").props.onLoad;
    const staleError = view.getByTestId("chat-image-preview").props.onError;
    await fireEvent(view.getByTestId("chat-image-preview"), "load", load(1200, 300));
    await view.rerender(<ChatMessageImage attachmentId="new" animatedReveal={false} previewFit="contain" width={148} height={189} />);
    expect(view.getByTestId("chat-image-frame")).toHaveStyle({ width: 148, height: 189 });
    await act(() => { staleLoad(load(300, 1200)); staleError(); });
    expect(view.getByTestId("chat-image-frame")).toHaveStyle({ width: 148, height: 189 });
    expect(view.getByTestId("chat-image-preview")).toBeOnTheScreen();
    await fireEvent(view.getByTestId("chat-image-preview"), "load", load(900, 900));
    expect(view.getByTestId("chat-image-frame")).toHaveStyle({ width: 148, height: 148 });
  });

  it.each([[0, 1], [-1, 1], [1, 0], [NaN, 10], [Infinity, 10]])("declines invalid decoded size %s by %s", async (width, height) => {
    const view = await render(<ChatMessageImage localUri="file:///scan.jpg" previewFit="contain" width={148} height={189} />);
    await fireEvent(view.getByTestId("chat-image-preview"), "load", load(width, height));
    expect(view.getByTestId("chat-image-frame")).toHaveStyle({ width: 148, height: 189 });
    expect(fitAttachmentImage({ width, height }, { width: 148, height: 189 })).toBeNull();
  });

  it("retains a usable failed-image frame and opens the existing viewer", async () => {
    const view = await render(<ChatMessageImage localUri="file:///scan.jpg" previewFit="contain" width={148} height={189} />);
    await fireEvent(view.getByTestId("chat-image-preview"), "error");
    expect(view.queryByTestId("chat-image-preview")).toBeNull();
    expect(view.getByTestId("chat-image-frame")).toHaveStyle({ width: 148, height: 189 });
    await fireEvent.press(view.getByLabelText("chat.image_unavailable_a11y"));
    expect(view.getByTestId("image-viewer")).toBeOnTheScreen();
  });

  it("offers Retry to VoiceOver as the frame's action", async () => {
    const view = await render(<ChatMessageImage attachmentId="a" animatedReveal={false} width={148} height={189} />);
    expect(view.getByLabelText("chat.image_view_a11y").props.accessibilityActions).toBeUndefined();
    await fireEvent(view.getByTestId("chat-image-preview"), "error");
    const frame = view.getByLabelText("chat.image_unavailable_a11y");
    expect(frame.props.accessibilityActions).toEqual([{ name: "retry", label: "common.retry" }]);
    await fireEvent(frame, "accessibilityAction", { nativeEvent: { actionName: "retry" } });
    expect(view.getByTestId("chat-image-preview")).toBeOnTheScreen();
    expect(view.queryByTestId("image-viewer")).toBeNull();
  });

  it("loads a failed photo again on Retry, without opening the viewer", async () => {
    const view = await render(<ChatMessageImage attachmentId="a" animatedReveal={false} width={148} height={189} />);
    const first = view.getByTestId("chat-image-preview");
    await fireEvent(first, "error");
    await fireEvent.press(view.getByTestId("media-load-retry"));
    const second = view.getByTestId("chat-image-preview");
    expect(second).toBeOnTheScreen();
    // A new image element: the failed load is not reused.
    expect(second).not.toBe(first);
    expect(view.queryByTestId("image-viewer")).toBeNull();
  });

  it("leaves generated image dimensions and cover behavior unchanged after load", async () => {
    const view = await render(<ChatMessageImage path="https://images.test/generated.jpg" width={148} height={189} />);
    const layers = view.getAllByTestId("animated-image");
    expect(layers).toHaveLength(2);
    expect(layers.every((layer) => layer.props.contentFit === "cover")).toBe(true);
    await fireEvent(layers[1], "load", load(1200, 300));
    expect(view.getByTestId("chat-image-frame")).toHaveStyle({ width: 148, height: 189 });
  });

  it("starts the reveal when the blurred layer loads, and only once", async () => {
    const withTiming = Reanimated.withTiming as jest.Mock;
    withTiming.mockClear();
    const view = await render(<ChatMessageImage path="https://images.test/generated.jpg" width={148} height={189} />);
    const layers = view.getAllByTestId("animated-image");
    const blur = layers.find((layer) => layer.props.blurRadius === 16);
    const sharp = layers.find((layer) => layer.props.blurRadius == null);
    expect(blur).toBeTruthy();
    await fireEvent(blur!, "load", load(1200, 300));
    expect(withTiming).toHaveBeenCalledTimes(1);
    expect(withTiming).toHaveBeenCalledWith(1, expect.objectContaining({ duration: 280 }));
    await fireEvent(sharp!, "load", load(1200, 300));
    expect(withTiming).toHaveBeenCalledTimes(1);
  });

  it("re-fits a loaded image if its available bounds change", async () => {
    const view = await render(<ChatMessageImage localUri="file:///scan.jpg" previewFit="contain" width={148} height={189} />);
    await fireEvent(view.getByTestId("chat-image-preview"), "load", load(1200, 300));
    await view.rerender(<ChatMessageImage localUri="file:///scan.jpg" previewFit="contain" width={100} height={120} />);
    expect(view.getByTestId("chat-image-frame")).toHaveStyle({ width: 100, height: 25 });
  });

  it.each([[1200, 300, 88, 22], [300, 1200, 28, 112]])("fits composer %s by %s without clipping the remove action", async (width, height, expectedWidth, expectedHeight) => {
    const onRemove = jest.fn();
    const view = await render(<ComposerAttachmentPreview attachment={photo("file:///scan.jpg")} onRemove={onRemove} />);
    await fireEvent(view.getByTestId("composer-image-preview"), "load", load(width, height));
    expect(view.getByTestId("composer-image-frame")).toHaveStyle({ width: expectedWidth, height: expectedHeight, overflow: "hidden" });
    const host = StyleSheet.flatten(view.getByTestId("composer-image-controls").props.style);
    expect(host.width).toBeGreaterThanOrEqual(44);
    expect(host.height).toBeGreaterThanOrEqual(44);
    expect(host.backgroundColor).toBeUndefined();
    expect(host.overflow).toBeUndefined();
    await fireEvent.press(view.getByRole("button"));
    expect(onRemove).toHaveBeenCalledTimes(1);
  });

  it("resets composer sizing on URI change and keeps upload removal disabled", async () => {
    const onRemove = jest.fn();
    const view = await render(<ComposerAttachmentPreview attachment={photo("file:///old.jpg")} onRemove={onRemove} />);
    const staleLoad = view.getByTestId("composer-image-preview").props.onLoad;
    await fireEvent(view.getByTestId("composer-image-preview"), "load", load(1200, 300));
    await view.rerender(<ComposerAttachmentPreview attachment={photo("file:///new.jpg")} onRemove={onRemove} uploading />);
    await act(() => staleLoad(load(300, 1200)));
    expect(view.getByTestId("composer-image-frame")).toHaveStyle({ width: 88, height: 112 });
    expect(view.getByTestId("composer-image-controls").props.accessibilityState.busy).toBe(true);
    await fireEvent.press(view.getByRole("button"));
    expect(onRemove).not.toHaveBeenCalled();
    await fireEvent(view.getByTestId("composer-image-preview"), "load", load(1200, 300));
    expect(view.getByTestId("composer-image-frame")).toHaveStyle({ width: 88, height: 22 });
  });
});
