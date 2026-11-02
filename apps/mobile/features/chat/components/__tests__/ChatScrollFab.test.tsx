import { fireEvent, render } from "@testing-library/react-native";

import { ChatScrollFab } from "@/features/chat/components/ChatScrollFab";
import { tap } from "@/lib/haptics";

jest.mock("@/lib/haptics", () => ({ tap: jest.fn() }));

it("taps once and scrolls when pressed", async () => {
  const onPress = jest.fn();
  const view = await render(<ChatScrollFab visible bottomOffset={80} scrollAwayCount={3} onPress={onPress} />);
  await fireEvent.press(view.getByRole("button", { name: "chat.scroll_to_latest" }));
  expect(onPress).toHaveBeenCalledTimes(1);
  expect(tap).toHaveBeenCalledTimes(1);
});
