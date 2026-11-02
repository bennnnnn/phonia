import { fireEvent, render } from "@testing-library/react-native";

import { GalleryItemActionsMenu } from "@/features/attachments/components/GalleryItemActionsMenu";

jest.mock("@/lib/reduceMotion", () => ({
  useReduceMotion: () => false,
}));

describe("GalleryItemActionsMenu", () => {
  it("offers open chat, share, and delete when the item is linked", async () => {
    const onUseInChat = jest.fn();
    const onOpenChat = jest.fn();
    const onShare = jest.fn();
    const onDelete = jest.fn();
    const { getByText } = await render(
      <GalleryItemActionsMenu
        visible
        canOpenChat
        anchorPoint={{ x: 120, y: 300 }}
        onClose={jest.fn()}
        onUseInChat={onUseInChat}
        onOpenChat={onOpenChat}
        onShare={onShare}
        onDelete={onDelete}
      />,
    );

    expect(getByText("gallery.open_chat")).toBeTruthy();
    expect(getByText("gallery.use_in_chat")).toBeTruthy();
    expect(getByText("gallery.share")).toBeTruthy();
    expect(getByText("common.delete")).toBeTruthy();

    await fireEvent.press(getByText("gallery.use_in_chat"));
    expect(onUseInChat).toHaveBeenCalled();
    await fireEvent.press(getByText("gallery.open_chat"));
    expect(onOpenChat).toHaveBeenCalled();
  });

  it("hides open chat when the item has no chat", async () => {
    const { queryByText } = await render(
      <GalleryItemActionsMenu
        visible
        canOpenChat={false}
        anchorPoint={null}
        onClose={jest.fn()}
        onUseInChat={jest.fn()}
        onOpenChat={jest.fn()}
        onShare={jest.fn()}
        onDelete={jest.fn()}
      />,
    );

    expect(queryByText("gallery.open_chat")).toBeNull();
    expect(queryByText("gallery.share")).toBeTruthy();
  });
});
