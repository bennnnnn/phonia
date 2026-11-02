import { StyleSheet } from "react-native";
import { fireEvent, render } from "@testing-library/react-native";

import { ChatHeader } from "@/features/chat/components/ChatHeader";
import { lightTheme as mockLightTheme } from "@/lib/theme";

const mockBack = jest.fn();
const mockReplace = jest.fn();
let mockReturnTo: string | undefined;

jest.mock("expo-router", () => ({
  useLocalSearchParams: () => ({ returnTo: mockReturnTo }),
  useRouter: () => ({
    back: mockBack,
    canGoBack: () => true,
    replace: mockReplace,
  }),
}));

jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

jest.mock("@/lib/haptics", () => ({
  tap: jest.fn(),
}));

jest.mock("expo-linear-gradient", () => {
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  return { LinearGradient: View };
});

const props = {
  paddingTop: 47,
  minimumHeight: 96,
  onHeightChange: jest.fn(),
  menuOverlayOpen: false,
  headerTitleLabel: "Trip",
  titleGenerating: false,
  chatTitle: "Trip",
  hasMessages: true,
  onOpenDrawer: jest.fn(),
  onNewChat: jest.fn(),
  onOpenMenu: jest.fn(),
};

describe("ChatHeader", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    mockReturnTo = undefined;
  });

  it("opens the drawer from home chat", async () => {
    const onOpenDrawer = jest.fn();
    const { getByLabelText } = await render(
      <ChatHeader {...props} onOpenDrawer={onOpenDrawer} />,
    );

    await fireEvent.press(getByLabelText("chat.open_drawer_a11y"));
    expect(onOpenDrawer).toHaveBeenCalled();
    expect(mockBack).not.toHaveBeenCalled();
  });

  it("gives the chat's title the header role", async () => {
    const { getByRole } = await render(<ChatHeader {...props} />);
    expect(getByRole("header", { name: "Trip" })).toBeOnTheScreen();
  });

  it("does not show a reminder bell", async () => {
    const { queryByLabelText } = await render(<ChatHeader {...props} />);
    expect(queryByLabelText("reminders.badge_accessibility")).toBeNull();
  });

  it("goes back to Library when pushed with returnTo=gallery", async () => {
    mockReturnTo = "gallery";
    const onOpenDrawer = jest.fn();
    const { getByLabelText, queryByLabelText } = await render(
      <ChatHeader {...props} onOpenDrawer={onOpenDrawer} />,
    );

    expect(queryByLabelText("chat.open_drawer_a11y")).toBeNull();
    await fireEvent.press(getByLabelText("common.back"));
    expect(mockBack).toHaveBeenCalled();
    expect(onOpenDrawer).not.toHaveBeenCalled();
  });

  it("uses a minimum height and reports a grown Dynamic Type layout once", async () => {
    const onHeightChange = jest.fn();
    const { getByTestId, getByText } = await render(
      <ChatHeader {...props} onHeightChange={onHeightChange} />,
    );
    const header = getByTestId("chat-header");

    expect(StyleSheet.flatten(header.props.style)).toMatchObject({
      minHeight: 96,
      paddingTop: 47,
    });
    expect(StyleSheet.flatten(getByText("Trip").props.style)).toMatchObject({
      fontSize: 17,
      fontWeight: "400",
      fontFamily: "SourceSans3-Bold",
    });

    const layout = { nativeEvent: { layout: { x: 0, y: 0, width: 390, height: 118 } } };
    await fireEvent(header, "layout", layout);
    await fireEvent(header, "layout", layout);
    expect(onHeightChange).toHaveBeenCalledTimes(1);
    expect(onHeightChange).toHaveBeenCalledWith(118);
  });
});
