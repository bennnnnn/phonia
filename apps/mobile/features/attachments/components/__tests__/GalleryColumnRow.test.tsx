import { fireEvent, render } from "@testing-library/react-native";

import { GalleryColumnRow } from "@/features/attachments/components/GalleryColumnRow";
import type { AttachmentListItem } from "@/lib/api";
import { lightTheme as mockLightTheme } from "@/lib/theme";

jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

jest.mock("@/features/attachments/components/GalleryThumbnail", () => {
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    GalleryThumbnail: () => <View testID="gallery-column-thumb" />,
  };
});

function fileItem(): AttachmentListItem {
  return {
    id: "a",
    content_type: "application/pdf",
    size_bytes: 12,
    download_url: "/attachments/a/file",
    source: "upload",
    created_at: "2026-01-01T00:00:00.000Z",
    original_filename: "notes.pdf",
    chat_title: "Trip",
  };
}

describe("GalleryColumnRow", () => {
  it("puts the filename to the right of the thumb and shows the chat title", async () => {
    const onPress = jest.fn();
    const { getByText } = await render(
      <GalleryColumnRow
        item={fileItem()}
        title="notes.pdf"
        onPress={onPress}
        onLongPress={jest.fn()}
        onMissing={jest.fn()}
      />,
    );

    expect(getByText("notes.pdf")).toBeTruthy();
    expect(getByText("Trip")).toBeTruthy();
    await fireEvent.press(getByText("notes.pdf"));
    expect(onPress).toHaveBeenCalled();
  });

  it("is a kit list row: one line, cut in the middle so the extension shows", async () => {
    const { getByText, getByRole } = await render(
      <GalleryColumnRow
        item={fileItem()}
        title="a-very-long-quarterly-report-final.pdf"
        onPress={jest.fn()}
        onLongPress={jest.fn()}
        onMissing={jest.fn()}
        accessibilityHint="gallery.open_file_a11y"
      />,
    );
    const title = getByText("a-very-long-quarterly-report-final.pdf");
    expect(title.props.numberOfLines).toBe(1);
    expect(title.props.ellipsizeMode).toBe("middle");
    const row = getByRole("button");
    expect(row.props.accessibilityLabel).toBe("a-very-long-quarterly-report-final.pdf, Trip");
    expect(row.props.accessibilityHint).toBe("gallery.open_file_a11y");
  });

  it("passes the touch point to the long-press menu and offers its actions to screen readers", async () => {
    const onLongPress = jest.fn();
    const onAccessibilityAction = jest.fn();
    const { getByRole } = await render(
      <GalleryColumnRow
        item={fileItem()}
        title="notes.pdf"
        onPress={jest.fn()}
        onLongPress={onLongPress}
        onMissing={jest.fn()}
        accessibilityActions={[{ name: "share", label: "gallery.share" }]}
        onAccessibilityAction={onAccessibilityAction}
      />,
    );
    const row = getByRole("button");
    await fireEvent(row, "longPress", { nativeEvent: { pageX: 12, pageY: 34 } });
    expect(onLongPress).toHaveBeenCalledWith({ x: 12, y: 34 });
    expect(row.props.accessibilityActions).toEqual([{ name: "share", label: "gallery.share" }]);
    await fireEvent(row, "accessibilityAction", { nativeEvent: { actionName: "share" } });
    expect(onAccessibilityAction).toHaveBeenCalled();
  });

  it("shows a spinner and waits while the item is being shared or attached", async () => {
    const onPress = jest.fn();
    const { getByRole } = await render(
      <GalleryColumnRow
        item={fileItem()}
        title="notes.pdf"
        busy
        onPress={onPress}
        onLongPress={jest.fn()}
        onMissing={jest.fn()}
      />,
    );
    const row = getByRole("button");
    expect(row.props.accessibilityState).toMatchObject({ busy: true, disabled: true });
    await fireEvent.press(row);
    expect(onPress).not.toHaveBeenCalled();
  });
});
