import { fireEvent, render } from "@testing-library/react-native";

import { HEADER_BUTTON_SIZE, HeaderButton, HeaderButtonGroup } from "../HeaderButton";

describe("HeaderButton", () => {
  it("is a 44 round button with its icon", async () => {
    const onPress = jest.fn();
    const view = await render(
      <HeaderButton icon="arrow-left" onPress={onPress} accessibilityLabel="Back" testID="back" />,
    );
    const button = view.getByRole("button", { name: "Back" });
    expect(button).toHaveStyle({
      width: HEADER_BUTTON_SIZE,
      height: HEADER_BUTTON_SIZE,
      borderRadius: HEADER_BUTTON_SIZE / 2,
    });
    expect(view.getByTestId("back-icon").props.name).toBe("arrow-left");
    await fireEvent.press(button);
    expect(onPress).toHaveBeenCalledTimes(1);
  });

  it("shows a spinner and ignores presses while busy", async () => {
    const onPress = jest.fn();
    const view = await render(
      <HeaderButton icon="share" variant="media" busy onPress={onPress} accessibilityLabel="Share" testID="share" />,
    );
    const button = view.getByRole("button", { name: "Share" });
    expect(button.props.accessibilityState).toEqual({ disabled: true, busy: true });
    expect(view.getByTestId("share-busy")).toBeTruthy();
    expect(view.queryByTestId("share-icon")).toBeNull();
    await fireEvent.press(button);
    expect(onPress).not.toHaveBeenCalled();
  });

  it("groups plain buttons in one pill", async () => {
    const view = await render(
      <HeaderButtonGroup testID="group">
        <HeaderButton variant="plain" icon="edit" onPress={jest.fn()} accessibilityLabel="New chat" />
        <HeaderButton variant="plain" icon="more-vertical" onPress={jest.fn()} accessibilityLabel="More" />
      </HeaderButtonGroup>,
    );
    expect(view.getByTestId("group")).toHaveStyle({ borderRadius: HEADER_BUTTON_SIZE / 2 });
    expect(view.getAllByRole("button")).toHaveLength(2);
  });
});
