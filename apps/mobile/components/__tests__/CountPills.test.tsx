import { StyleSheet } from "react-native";
import { render } from "@testing-library/react-native";

import { ReminderBadge } from "@/features/chat/components/ReminderBadge";
import { ChatScrollFab } from "@/features/chat/components/ChatScrollFab";
import { lightTheme as mockLightTheme } from "@/lib/theme";

jest.mock("@/lib/theme", () => ({
  ...jest.requireActual("@/lib/theme"),
  useTheme: () => mockLightTheme,
}));

describe("count pills", () => {
  it("lets reminder counts grow vertically with Dynamic Type", async () => {
    const { getByText } = await render(<ReminderBadge count={7} />);
    const badgeStyle = StyleSheet.flatten(getByText("7").parent?.props.style);

    expect(badgeStyle).toMatchObject({ minWidth: 18, minHeight: 18 });
    expect(badgeStyle.height).toBeUndefined();
  });

  it("lets scroll-away counts grow vertically with Dynamic Type", async () => {
    const { getByText } = await render(
      <ChatScrollFab
        visible
        bottomOffset={80}
        scrollAwayCount={3}
        onPress={jest.fn()}
      />,
    );
    const badgeStyle = StyleSheet.flatten(getByText("3").parent?.props.style);

    expect(badgeStyle).toMatchObject({ minWidth: 18, minHeight: 18 });
    expect(badgeStyle.height).toBeUndefined();
  });
});
