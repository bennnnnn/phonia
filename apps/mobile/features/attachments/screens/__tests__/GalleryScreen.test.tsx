import { act, fireEvent, render } from "@testing-library/react-native";

import GalleryScreen from "@/features/attachments/screens/GalleryScreen";
import type { AttachmentListItem } from "@/lib/api";

type ListProps = {
  data: AttachmentListItem[];
  renderItem: (info: { item: AttachmentListItem; index: number }) => React.ReactNode;
  contentContainerStyle?: Record<string, unknown>;
  ItemSeparatorComponent?: unknown;
  refreshControl?: React.ReactElement<{ onRefresh: () => void }>;
};
let mockListProps: ListProps | null = null;
jest.mock("@shopify/flash-list", () => {
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    FlashList: (props: ListProps) => {
      mockListProps = props;
      return (
        <View testID="gallery-list">
          {props.data.map((item, index) => (
            <View key={item.id}>{props.renderItem({ item, index })}</View>
          ))}
        </View>
      );
    },
  };
});
const mockFeedback = { error: jest.fn(), success: jest.fn(), info: jest.fn(), warning: jest.fn(), show: jest.fn(), dismiss: jest.fn() };
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => mockFeedback }));
jest.mock("@/features/attachments/components/GalleryMediaModals", () => ({ GalleryMediaModals: () => null }));
jest.mock("@/features/attachments/components/GalleryThumbnail", () => {
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  return { GalleryThumbnail: ({ size }: { size: number }) => <View testID="thumb" style={{ width: size, height: size }} /> };
});

let mockData: Record<string, unknown>;
jest.mock("@/features/attachments/hooks/useGalleryData", () => ({ useGalleryData: () => mockData }));
// The screen module re-exports its route's error view, which reads the router; this test
// renders the screen alone, without a router.
jest.mock("@/components/ScreenErrorBoundary", () => ({ ScreenErrorBoundary: () => null }));
let mockLibrary: Record<string, unknown>;
jest.mock("@/features/attachments/hooks/useGalleryLibrary", () => ({ useGalleryLibrary: () => mockLibrary }));

const generated: AttachmentListItem = {
  id: "gen",
  content_type: "image/png",
  size_bytes: 1,
  download_url: "/attachments/gen/file",
  source: "generated",
  created_at: "2026-01-01T00:00:00Z",
  original_filename: "A cat in a hat",
  chat_id: "c1",
};
const pdf: AttachmentListItem = {
  id: "doc",
  content_type: "application/pdf",
  size_bytes: 1,
  download_url: "/attachments/doc/file",
  source: "upload",
  created_at: "2026-01-01T00:00:00Z",
  original_filename: "quarterly-report.pdf",
};

function library(overrides: Record<string, unknown> = {}) {
  return {
    layout: "grid",
    toggleLayout: jest.fn(),
    viewerItem: null,
    setViewerId: jest.fn(),
    fileItem: null,
    setFileItem: jest.fn(),
    actionItem: null,
    actionPoint: null,
    setActionItem: jest.fn(),
    busyItemId: null,
    shareFile: jest.fn(),
    openChat: jest.fn(),
    attachToComposer: jest.fn(),
    confirmDelete: jest.fn(),
    openActions: jest.fn(),
    openImage: jest.fn(),
    openFile: jest.fn(),
    ...overrides,
  };
}

function data(overrides: Record<string, unknown> = {}) {
  return {
    items: [generated, pdf],
    loading: false,
    loadingMore: false,
    error: false,
    pageError: false,
    retryPage: jest.fn(),
    pullRefreshing: false,
    refresh: jest.fn(async () => true),
    loadMore: jest.fn(),
    retry: jest.fn(),
    removeItem: jest.fn(),
    ...overrides,
  };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockListProps = null;
  mockData = data();
  mockLibrary = library();
});

describe("GalleryScreen", () => {
  it("names each tile and offers its long-press actions to screen readers", async () => {
    const view = await render(<GalleryScreen />);
    const photo = view.getByRole("button", { name: "A cat in a hat" });
    expect(photo.props.accessibilityHint).toBe("chat.image_view_a11y");
    expect(photo.props.accessibilityActions.map((action: { name: string }) => action.name))
      .toEqual(["use", "open_chat", "share", "delete"]);
    const file = view.getByRole("button", { name: "quarterly-report.pdf" });
    expect(file.props.accessibilityHint).toBe("gallery.open_file_a11y");
    expect(file.props.accessibilityActions.map((action: { name: string }) => action.name))
      .toEqual(["use", "share", "delete"]);

    await fireEvent(photo, "accessibilityAction", { nativeEvent: { actionName: "share" } });
    expect(mockLibrary.shareFile).toHaveBeenCalledWith(generated);
    await fireEvent(file, "accessibilityAction", { nativeEvent: { actionName: "delete" } });
    expect(mockLibrary.confirmDelete).toHaveBeenCalledWith(pdf);
  });

  it("cuts a file tile's name in the middle so the extension shows", async () => {
    const view = await render(<GalleryScreen />);
    const label = view.getByText("quarterly-report.pdf");
    expect(label.props.numberOfLines).toBe(1);
    expect(label.props.ellipsizeMode).toBe("middle");
  });

  it("shows a spinner on the item being attached from its menu, and offers the menu to screen readers", async () => {
    mockLibrary = library({ busyItemId: "gen" });
    const view = await render(<GalleryScreen />);
    const photo = view.getByRole("button", { name: "A cat in a hat" });
    expect(photo.props.accessibilityHint).toBe("chat.image_view_a11y");
    expect(photo.props.accessibilityActions.map((a: { name: string }) => a.name)).toContain("use");
    expect(photo.props.accessibilityState).toMatchObject({ busy: true });
    expect(view.getByTestId("gallery-item-busy")).toBeTruthy();
    const pdfRow = view.getByRole("button", { name: "quarterly-report.pdf" });
    await fireEvent(pdfRow, "accessibilityAction", { nativeEvent: { actionName: "use" } });
    expect(mockLibrary.attachToComposer).toHaveBeenCalledWith(pdf);
  });

  it("spaces the grid evenly: one gap across and down, the gutter at both edges", async () => {
    const view = await render(<GalleryScreen />);
    // 750pt jest window: list inset 12 + cell padding 4 = the 16pt gutter on each side.
    expect(mockListProps?.contentContainerStyle).toMatchObject({ paddingHorizontal: 12 });
    expect(mockListProps?.ItemSeparatorComponent).toBeUndefined();
    const cell = view.getAllByTestId("thumb")[0].parent!.parent!;
    expect(cell).toHaveStyle({ padding: 4 });
    // Three tiles plus two 8pt gaps fill the width between the gutters.
    const size = view.getAllByTestId("thumb")[0].props.style.width as number;
    expect(750 - 2 * 16 - (3 * size + 2 * 8)).toBeLessThan(3);
  });

  it("draws edge-to-edge rows with separators in the column layout", async () => {
    mockLibrary = library({ layout: "column" });
    await render(<GalleryScreen />);
    expect(mockListProps?.contentContainerStyle).toMatchObject({ paddingHorizontal: 0 });
    expect(mockListProps?.ItemSeparatorComponent).toBeDefined();
  });

  it("loads with tile placeholders in the grid and row placeholders in the column layout", async () => {
    mockData = data({ items: [], loading: true });
    const grid = await render(<GalleryScreen />);
    expect(grid.getByTestId("skeleton-grid")).toBeTruthy();
    await grid.unmount();
    mockLibrary = library({ layout: "column" });
    const column = await render(<GalleryScreen />);
    expect(column.queryByTestId("skeleton-grid")).toBeNull();
  });

  it("says so when pull to refresh fails while older items stay on screen", async () => {
    mockData = data({ refresh: jest.fn(async () => false) });
    await render(<GalleryScreen />);
    await act(async () => {
      mockListProps?.refreshControl?.props.onRefresh();
    });
    expect(mockFeedback.error).toHaveBeenCalledWith("gallery.refresh_failed");
  });

  it("keeps the same renderItem when unrelated Library state changes", async () => {
    const view = await render(<GalleryScreen />);
    const first = mockListProps?.renderItem;
    mockLibrary = { ...mockLibrary, viewerItem: generated, actionPoint: { x: 1, y: 2 } };
    await view.rerender(<GalleryScreen />);
    expect(mockListProps?.renderItem).toBe(first);
  });
});
