import { fireEvent, render } from "@testing-library/react-native";

import { GalleryLibraryHeader } from "@/features/attachments/components/GalleryLibraryHeader";
import { selection, tap } from "@/lib/haptics";
import { lightTheme as mockLightTheme } from "@/lib/theme";

jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
  selection: jest.fn(),
}));

describe("GalleryLibraryHeader", () => {
  it("puts the layout toggle next to the Files tab", async () => {
    const onToggleLayout = jest.fn();
    const { getByTestId, getByLabelText } = await render(
      <GalleryLibraryHeader
        filter="all"
        searchQuery=""
        layout="column"
        onSearchChange={jest.fn()}
        onFilterChange={jest.fn()}
        onToggleLayout={onToggleLayout}
      />,
    );

    expect(getByLabelText("gallery.filter.files")).toBeTruthy();
    expect(getByTestId("gallery-layout-toggle")).toBeTruthy();
    await fireEvent.press(getByTestId("gallery-layout-toggle"));
    expect(onToggleLayout).toHaveBeenCalled();
  });

  it("ticks once for a filter change, like every other picker", async () => {
    const onFilterChange = jest.fn();
    const { getByLabelText } = await render(
      <GalleryLibraryHeader
        filter="all"
        searchQuery=""
        layout="grid"
        onSearchChange={jest.fn()}
        onFilterChange={onFilterChange}
        onToggleLayout={jest.fn()}
      />,
    );
    await fireEvent.press(getByLabelText("gallery.filter.files"));
    expect(onFilterChange).toHaveBeenCalledWith("files");
    expect(selection).toHaveBeenCalledTimes(1);
    expect(tap).not.toHaveBeenCalled();
  });

  it("keeps the layout toggle a 44pt kit button on the chips' line", async () => {
    const { getByTestId, getByLabelText } = await render(
      <GalleryLibraryHeader
        filter="all"
        searchQuery=""
        layout="grid"
        onSearchChange={jest.fn()}
        onFilterChange={jest.fn()}
        onToggleLayout={jest.fn()}
      />,
    );
    const toggle = getByTestId("gallery-layout-toggle");
    expect(toggle).toHaveStyle({ minWidth: 44, minHeight: 44 });
    expect(toggle.props.accessibilityLabel).toBe("gallery.layout_column_a11y");
    // The toggle and the scrolling chip row share one row that does not wrap.
    const row = toggle.parent!;
    expect(row).toHaveStyle({ flexDirection: "row" });
    expect(row).not.toHaveStyle({ flexWrap: "wrap" });
    expect(getByLabelText("gallery.filter.files")).toBeTruthy();
  });
});
