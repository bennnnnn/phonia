import { fireEvent, render } from "@testing-library/react-native";

import { ChatMessageImageStrip } from "@/features/attachments/components/ChatMessageImageStrip";

jest.mock("@/features/attachments/components/ChatMessageImage", () => {
  const { Pressable: MockPressable } = jest.requireActual("react-native");
  return {
    ChatMessageImage: ({
      attachmentId,
      onOpen,
    }: {
      attachmentId?: string | null;
      onOpen?: () => void;
    }) => (
      <MockPressable testID={`chat-message-image-${attachmentId ?? "local"}`} onPress={onOpen} />
    ),
  };
});
jest.mock("@/features/attachments/components/AttachmentImageViewer", () => {
  const { View: MockView } = jest.requireActual("react-native");
  return {
    AttachmentImageViewer: ({
      visible,
      images,
      initialIndex,
    }: {
      visible: boolean;
      images?: { attachmentId?: string | null }[];
      initialIndex?: number;
    }) =>
      visible ? (
        <MockView
          testID="strip-lightbox"
          accessibilityValue={{ text: `${images?.length ?? 0}:${initialIndex ?? 0}` }}
        />
      ) : null,
  };
});

const twoCars = [
  { attachmentId: "a", path: "/attachments/a/file" },
  { attachmentId: "b", path: "/attachments/b/file" },
];

describe("ChatMessageImageStrip", () => {
  it("does not render a scroller for a single image", async () => {
    const { queryByTestId, getByTestId } = await render(
      <ChatMessageImageStrip images={[{ attachmentId: "a", path: "/attachments/a/file" }]} />,
    );

    expect(queryByTestId("chat-image-strip")).toBeNull();
    expect(getByTestId("chat-message-image-a")).toBeOnTheScreen();
  });

  it("puts two or more images in a horizontal snap scroller", async () => {
    const { getByTestId } = await render(<ChatMessageImageStrip images={twoCars} />);

    const strip = getByTestId("chat-image-strip");
    expect(strip.props.horizontal).toBe(true);
    expect(strip.props.showsHorizontalScrollIndicator).toBe(false);
    expect(strip.props.snapToInterval).toBeGreaterThan(0);
    expect(getByTestId("chat-message-image-a")).toBeOnTheScreen();
    expect(getByTestId("chat-message-image-b")).toBeOnTheScreen();
  });

  it("opens a shared lightbox for the tapped photo in that generation", async () => {
    const { getByTestId } = await render(<ChatMessageImageStrip images={twoCars} />);
    await fireEvent.press(getByTestId("chat-message-image-b"));
    expect(getByTestId("strip-lightbox").props.accessibilityValue.text).toBe("2:1");
  });

  it("renders nothing when there are no images", async () => {
    const { toJSON } = await render(<ChatMessageImageStrip images={[]} />);
    expect(toJSON()).toBeNull();
  });
});
