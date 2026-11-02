import { act, fireEvent, render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import {
  ensureLocalAttachmentFile,
  saveChatAttachmentToLibrary,
  shareChatAttachment,
} from "@/features/attachments/model/downloadChatAttachment";
import { AttachmentImageViewer } from "@/features/attachments/components/AttachmentImageViewer";
import { lightTheme as mockLightTheme } from "@/lib/theme";
import { SharingUnavailableError } from "@/lib/shareUnavailable";
import { alertDialog } from "@/ui/overlay/dialogs";

// One object, as the provider keeps it: a new getter per render re-runs every effect.
const mockAccountSession = { account: "user-1:0", getToken: () => "tok" };
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => mockAccountSession,
}));
jest.mock("@/contexts/AuthContext", () => ({
  useAuthToken: () => "tok",
}));
jest.mock("@/features/attachments/model/attachmentUri", () => ({
  resolveAttachmentUri: ({ attachmentId }: { attachmentId?: string }) => `http://test.local/${attachmentId}`,
  attachmentRequestHeaders: (uri: string, token: string) => uri.startsWith("http://test.local/") ? { Authorization: `Bearer ${token}` } : {},
}));
jest.mock("@/features/attachments/model/downloadChatAttachment", () => ({
  ensureLocalAttachmentFile: jest.fn(() => new Promise(() => {})),
  getCachedAttachmentFile: () => null,
  invalidateCachedAttachmentFile: jest.fn(),
  saveChatAttachmentToLibrary: jest.fn(),
  shareChatAttachment: jest.fn(),
}));
jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, values?: Record<string, unknown>) =>
      values ? `${key}:${Object.values(values).join("|")}` : key,
  }),
}));
jest.mock("expo-status-bar", () => {
  const { Text } = jest.requireActual("react-native") as typeof import("react-native");
  return { StatusBar: ({ style }: { style: string }) => <Text testID="viewer-status-bar">{style}</Text> };
});
jest.mock("@/ui/overlay/dialogs", () => ({ alertDialog: jest.fn(), confirmDialog: jest.fn() }));
jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

let mockGeneration = 0;
const onClose = () => undefined;
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockGeneration }));

describe("AttachmentImageViewer", () => {
  beforeEach(() => {
    mockGeneration = 0;
    jest.clearAllMocks();
    jest.mocked(ensureLocalAttachmentFile).mockReset().mockImplementation(() => new Promise(() => {}));
  });
  it("shows Retry after the image fails instead of spinning forever", async () => {
    const { getByTestId, queryByTestId } = await render(
      <AttachmentImageViewer onClose={onClose} visible attachmentId="a" />,
    );
    expect(getByTestId("attachment-viewer-image")).toBeTruthy();
    await act(async () => {
      getByTestId("attachment-viewer-image").props.onError();
    });
    expect(queryByTestId("attachment-viewer-image")).toBeNull();
    expect(getByTestId("media-load-retry")).toBeTruthy();
  });

  it("draws Retry in media ink: the stage is black in light mode too", async () => {
    // It took the page's grey ink, #5C5C64 on #000000 in light mode: 3.17:1.
    const { getByTestId, getByText } = await render(
      <AttachmentImageViewer onClose={onClose} visible attachmentId="a" />,
    );
    await act(async () => {
      getByTestId("attachment-viewer-image").props.onError();
    });
    const stage = StyleSheet.flatten(getByTestId("attachment-image-viewer").props.style);
    expect(stage.backgroundColor).toBe(mockLightTheme.mediaScrim);
    expect(StyleSheet.flatten(getByText("common.retry").props.style).color).toBe(mockLightTheme.onMedia);
    expect(getByTestId("media-load-retry-icon").props.color).toBe(mockLightTheme.onMedia);
  });

  it("reloads the image when Retry is pressed", async () => {
    const { getByTestId, queryByTestId } = await render(
      <AttachmentImageViewer onClose={onClose} visible attachmentId="a" />,
    );
    const firstSource = getByTestId("attachment-viewer-image").props.source;
    await act(async () => {
      getByTestId("attachment-viewer-image").props.onError();
    });
    await fireEvent.press(getByTestId("media-load-retry"));
    expect(getByTestId("attachment-viewer-image")).toBeTruthy();
    expect(queryByTestId("media-load-retry")).toBeNull();
    expect(getByTestId("attachment-viewer-image").props.source.cacheKey).not.toBe(
      firstSource.cacheKey,
    );
  });

  it("keeps auth headers, cached loading, and decoded aspect sizing", async () => {
    const view = await render(
      <AttachmentImageViewer onClose={onClose} visible attachmentId="a" />,
    );
    const image = view.getByTestId("attachment-viewer-image");
    expect(image.props.source).toEqual({
      uri: "http://test.local/a",
      headers: { Authorization: "Bearer tok" },
      cacheKey: "attachment:0:0:http://test.local/a",
    });
    expect(image.props.contentFit).toBe("contain");
    expect(image.props.cachePolicy).toBe("memory-disk");

    await fireEvent(view.getByTestId("attachment-viewer-tap"), "layout", {
      nativeEvent: { layout: { width: 400, height: 300 } },
    });
    await fireEvent(image, "load", {
      nativeEvent: { source: { width: 800, height: 400 } },
    });
    expect(view.getByTestId("attachment-viewer-image")).toHaveStyle({
      width: 400,
      height: 200,
    });
  });
  it("never displays a previous image's cached file when the selected attachment changes", async () => {
    jest.mocked(ensureLocalAttachmentFile).mockResolvedValueOnce("file:///cache/first.jpg");
    const view = await render(<AttachmentImageViewer onClose={onClose} visible attachmentId="first" />);
    expect(view.getByTestId("attachment-viewer-image").props.source.uri).toBe("file:///cache/first.jpg");
    await view.rerender(<AttachmentImageViewer onClose={onClose} visible attachmentId="second" />);
    expect(view.getByTestId("attachment-viewer-image").props.source.uri).toBe("http://test.local/second");
  });

  it("does not attach authorization to an external preview URL", async () => {
    const view = await render(<AttachmentImageViewer onClose={onClose} visible attachmentId="first" previewUri="https://external.test/preview.jpg" />);
    expect(view.getByTestId("attachment-viewer-image").props.source).toEqual({ uri: "https://external.test/preview.jpg" });
  });

  it("detaches a cached image when the account changes", async () => {
    jest.mocked(ensureLocalAttachmentFile).mockResolvedValueOnce("file:///cache/previous-account.jpg");
    const view = await render(<AttachmentImageViewer onClose={onClose} visible attachmentId="first" />);
    mockGeneration++;
    await view.rerender(<AttachmentImageViewer onClose={onClose} visible attachmentId="first" />);
    expect(view.getByTestId("attachment-viewer-image").props.source).toEqual({
      uri: "http://test.local/first",
      headers: { Authorization: "Bearer tok" },
      cacheKey: "attachment:1:0:http://test.local/first",
    });
  });

  it("pages across photos from the same generation", async () => {
    const { getByTestId } = await render(
      <AttachmentImageViewer onClose={onClose}
        visible
        images={[
          { attachmentId: "a", path: "/attachments/a/file" },
          { attachmentId: "b", path: "/attachments/b/file" },
        ]}
        initialIndex={0}
      />,
    );
    const pager = getByTestId("attachment-viewer-pager");
    expect(pager.props.horizontal).toBe(true);
    expect(pager.props.pagingEnabled).toBe(true);
    expect(getByTestId("attachment-image-viewer")).toBeTruthy();
  });

  it("hides Open chat when the visible photo is not linked to a chat", async () => {
    const { getByLabelText, queryByLabelText } = await render(
      <AttachmentImageViewer onClose={onClose}
        visible
        images={[{ attachmentId: "a" }]}
        onOpenChat={jest.fn()}
        onDelete={jest.fn()}
      />,
    );
    await fireEvent.press(getByLabelText("preview.more_a11y"));
    expect(queryByLabelText("gallery.open_chat")).toBeNull();
    expect(getByLabelText("common.delete")).toBeTruthy();
  });

  it("opens chat for the visible Library photo from the more menu", async () => {
    const onOpenChat = jest.fn();
    const { getByLabelText, queryByLabelText } = await render(
      <AttachmentImageViewer onClose={onClose}
        visible
        images={[{ attachmentId: "a", chatId: "c1" }]}
        onOpenChat={onOpenChat}
      />,
    );
    expect(queryByLabelText("gallery.open_chat")).toBeNull();
    await fireEvent.press(getByLabelText("preview.more_a11y"));
    await fireEvent.press(getByLabelText("gallery.open_chat"));
    expect(onOpenChat).toHaveBeenCalledWith(expect.objectContaining({ attachmentId: "a", chatId: "c1" }));
  });

  it("puts More, Download and a Share pill on the right, in that order", async () => {
    const { getByLabelText, queryByLabelText, getByTestId } = await render(
      <AttachmentImageViewer onClose={onClose}
        visible
        images={[{ attachmentId: "a", chatId: "c1" }]}
        onOpenChat={jest.fn()}
        onUseInChat={jest.fn()}
        onDelete={jest.fn()}
      />,
    );
    expect(getByLabelText("preview.close")).toBeTruthy();
    const header = getByLabelText("preview.more_a11y").parent!;
    const order = header.children
      .filter((child): child is NonNullable<typeof child> & { props: { accessibilityLabel?: string } } =>
        typeof child !== "string")
      .map((child) => child.props.accessibilityLabel);
    expect(order).toEqual(["preview.more_a11y", "common.download", "preview.share"]);
    expect(queryByLabelText("gallery.use_in_chat")).toBeNull();
    expect(queryByLabelText("common.delete")).toBeNull();
    // Nothing at the bottom: no page dots.
    expect(getByTestId("attachment-image-viewer")).toBeTruthy();
  });

  it("hides More when it has nothing to offer (chat)", async () => {
    const { getByLabelText, queryByLabelText } = await render(
      <AttachmentImageViewer onClose={onClose} visible attachmentId="a" />,
    );
    expect(getByLabelText("preview.share")).toBeTruthy();
    expect(getByLabelText("common.download")).toBeTruthy();
    expect(queryByLabelText("preview.more_a11y")).toBeNull();
  });

  it("turns the status bar light while open", async () => {
    const view = await render(<AttachmentImageViewer onClose={onClose} visible attachmentId="a" />);
    expect(view.getByTestId("viewer-status-bar").props.children).toBe("light");
    await view.rerender(<AttachmentImageViewer onClose={onClose} visible={false} attachmentId="a" />);
    expect(view.queryByTestId("viewer-status-bar")).toBeNull();
  });

  it("hides chrome on a tap and brings it back on the next tap", async () => {
    const { getByTestId, getByLabelText, queryByLabelText } = await render(
      <AttachmentImageViewer onClose={onClose} visible attachmentId="a" />,
    );
    expect(getByLabelText("preview.close")).toBeTruthy();
    await fireEvent.press(getByTestId("attachment-viewer-tap"));
    expect(queryByLabelText("preview.close")).toBeNull();
    expect(queryByLabelText("preview.share")).toBeNull();
    await fireEvent.press(getByTestId("attachment-viewer-tap"));
    expect(getByLabelText("preview.close")).toBeTruthy();
    expect(getByLabelText("preview.share")).toBeTruthy();
  });

  it("lets a screen reader toggle the controls by activating the photo", async () => {
    const { getByTestId, queryByLabelText } = await render(
      <AttachmentImageViewer onClose={onClose} visible attachmentId="a" fileName="cat.png" />,
    );
    const photo = getByTestId("attachment-viewer-tap");
    expect(photo.props.accessibilityRole).toBe("image");
    expect(photo.props.accessibilityLabel).toBe("cat.png");
    await fireEvent(photo, "accessibilityAction", { nativeEvent: { actionName: "activate" } });
    expect(queryByLabelText("preview.close")).toBeNull();
  });

  it("puts round media chips on the left and a white Share pill on the right", async () => {
    const { getByLabelText } = await render(
      <AttachmentImageViewer onClose={onClose} visible attachmentId="a" />,
    );
    const close = StyleSheet.flatten(getByLabelText("preview.close").props.style);
    expect(close.backgroundColor).toBeTruthy();
    expect(close.borderRadius).toBeGreaterThan(20);
    const download = StyleSheet.flatten(getByLabelText("common.download").props.style);
    expect(download.backgroundColor).toBe(close.backgroundColor);
    const share = StyleSheet.flatten(getByLabelText("preview.share").props.style);
    expect(share.backgroundColor).toBe(mockLightTheme.onMedia);
    expect(share.minHeight).toBe(44);
  });

  it("slides the lightbox so a downward pull can dismiss it", async () => {
    const { getByTestId } = await render(
      <AttachmentImageViewer onClose={onClose} visible attachmentId="a" />,
    );
    const root = getByTestId("attachment-image-viewer");
    expect(root.props.collapsable).toBe(false);
    // Pan translateY composed with the scale-in entrance (0.94 → 1 on open).
    expect(StyleSheet.flatten(root.props.style).transform).toEqual([
      { translateY: 0 },
      { scale: 0.94 },
    ]);
  });

  it("stops paging while the photo is zoomed", async () => {
    const view = await render(
      <AttachmentImageViewer onClose={onClose} visible images={[{ attachmentId: "a" }, { attachmentId: "b" }]} />,
    );
    expect(view.getByTestId("attachment-viewer-pager").props.scrollEnabled).toBe(true);
    const [first] = view.getAllByTestId("attachment-viewer-tap");
    await act(async () => {
      await fireEvent(first, "zoomChange", true);
    });
    expect(view.getByTestId("attachment-viewer-pager").props.scrollEnabled).toBe(false);
    await act(async () => {
      await fireEvent(view.getAllByTestId("attachment-viewer-tap")[0], "zoomChange", false);
    });
    expect(view.getByTestId("attachment-viewer-pager").props.scrollEnabled).toBe(true);
  });

  describe("paging by photo, not by position", () => {
    const WIDTH = 750; // the jest window width
    const photos = (...ids: string[]) => ids.map((id) => ({ attachmentId: id, fileName: `${id}.png` }));
    const pageTo = async (view: Awaited<ReturnType<typeof render>>, index: number) => {
      await act(async () => {
        await fireEvent(view.getByTestId("attachment-viewer-pager"), "momentumScrollEnd", {
          nativeEvent: { contentOffset: { x: index * WIDTH, y: 0 } },
        });
      });
    };

    it("deletes the photo on screen and then acts on the next one", async () => {
      const onDelete = jest.fn();
      const onIndexChange = jest.fn();
      const view = await render(
        <AttachmentImageViewer onClose={onClose} visible images={photos("a", "b", "c")} initialIndex={0} onDelete={onDelete} onIndexChange={onIndexChange} />,
      );
      await pageTo(view, 1);
      expect(onIndexChange).toHaveBeenLastCalledWith(expect.objectContaining({ attachmentId: "b" }), 1);
      await fireEvent.press(view.getByLabelText("preview.more_a11y"));
      await fireEvent.press(view.getByLabelText("common.delete"));
      expect(onDelete).toHaveBeenCalledWith(expect.objectContaining({ attachmentId: "b" }));

      // The Library removes b and keeps the viewer open on its neighbour.
      await view.rerender(
        <AttachmentImageViewer onClose={onClose} visible images={photos("a", "c")} initialIndex={1} onDelete={onDelete} onIndexChange={onIndexChange} />,
      );
      expect(onIndexChange).toHaveBeenLastCalledWith(expect.objectContaining({ attachmentId: "c" }), 1);
      await fireEvent.press(view.getByLabelText("preview.share"));
      expect(shareChatAttachment).toHaveBeenCalledWith(expect.objectContaining({ uri: "http://test.local/c" }));
    });

    it("stays on the same photo when one before it is removed", async () => {
      const view = await render(
        <AttachmentImageViewer onClose={onClose} visible images={photos("a", "b", "c")} initialIndex={2} />,
      );
      await pageTo(view, 0);
      // Deleting a elsewhere shifts every index; the viewer must keep showing what it showed.
      await view.rerender(<AttachmentImageViewer onClose={onClose} visible images={photos("x", "a", "b", "c")} initialIndex={3} />);
      await fireEvent.press(view.getByLabelText("preview.share"));
      expect(shareChatAttachment).toHaveBeenLastCalledWith(expect.objectContaining({ uri: "http://test.local/a" }));
      const labels = view.getAllByTestId("attachment-viewer-tap").map((stage) => stage.props.accessibilityLabel);
      expect(labels).toContain("gallery.viewer_image_a11y:a.png|2|4");
    });

    it("loads only the photo on screen and its neighbours in a large Library", async () => {
      const ids = Array.from({ length: 40 }, (_, index) => `p${index}`);
      const view = await render(
        <AttachmentImageViewer onClose={onClose} visible images={photos(...ids)} initialIndex={20} />,
      );
      // FlatList keeps many pages mounted (10 at first, up to 21 after
      // layout). Each page with a photo downloads and decodes it at full
      // size, so a Library of hundreds must not hold more than three.
      const stages = view
        .getAllByTestId("attachment-viewer-tap")
        .map((stage) => stage.props.accessibilityLabel as string);
      expect(stages.length).toBeLessThanOrEqual(3);
      expect(stages).toContain("gallery.viewer_image_a11y:p20.png|21|40");
      expect(view.getAllByTestId("attachment-viewer-image")).toHaveLength(stages.length);
      // Pages further away keep their width so paging and offsets still line up.
      for (const page of view.getAllByTestId("attachment-viewer-page-placeholder")) {
        expect(page).toHaveStyle({ width: WIDTH });
      }

      // Paging moves the loaded window with the photo on screen.
      await pageTo(view, 25);
      const next = view
        .getAllByTestId("attachment-viewer-tap")
        .map((stage) => stage.props.accessibilityLabel as string);
      expect(next.length).toBeLessThanOrEqual(3);
      expect(next).not.toContain("gallery.viewer_image_a11y:p20.png|21|40");
    });

    it("asks for the next Library page when it nears the last loaded photo", async () => {
      const onNearEnd = jest.fn();
      const view = await render(
        <AttachmentImageViewer onClose={onClose} visible images={photos("a", "b", "c", "d", "e")} initialIndex={0} onNearEnd={onNearEnd} />,
      );
      expect(onNearEnd).not.toHaveBeenCalled();
      await pageTo(view, 2);
      expect(onNearEnd).toHaveBeenCalled();
    });
  });

  describe("feedback inside the viewer", () => {
    it("shows Saved as a toast in the viewer instead of a blocking dialog", async () => {
      jest.mocked(saveChatAttachmentToLibrary).mockResolvedValueOnce("saved");
      const view = await render(<AttachmentImageViewer onClose={onClose} visible attachmentId="a" />);
      await act(async () => {
        await fireEvent.press(view.getByLabelText("common.download"));
      });
      expect(view.getByText("common.saved_to_photos")).toBeTruthy();
      expect(alertDialog).not.toHaveBeenCalled();
    });

    it("shows a failed share as a toast in the viewer", async () => {
      jest.mocked(shareChatAttachment).mockRejectedValueOnce(new Error("boom"));
      const view = await render(<AttachmentImageViewer onClose={onClose} visible attachmentId="a" />);
      await act(async () => {
        await fireEvent.press(view.getByLabelText("preview.share"));
      });
      expect(view.getByText("common.share_image_error")).toBeTruthy();
      expect(alertDialog).not.toHaveBeenCalled();
    });

    // Android without expo-sharing (lib/shareFile.ts): Share, and Save's share-sheet fallback.
    it.each([
      ["a share", "preview.share", shareChatAttachment],
      ["a save that fell back to sharing", "common.download", saveChatAttachmentToLibrary],
    ] as const)("says to update the app when this build cannot share files: %s", async (_label, button, action) => {
      jest.mocked(action).mockRejectedValueOnce(new SharingUnavailableError());
      const view = await render(<AttachmentImageViewer onClose={onClose} visible attachmentId="a" />);
      await act(async () => {
        await fireEvent.press(view.getByLabelText(button));
      });
      expect(view.getByText("common.share_needs_update")).toBeTruthy();
    });
  });
});
