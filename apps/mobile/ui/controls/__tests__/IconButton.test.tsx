import { fireEvent, render } from "@testing-library/react-native";

import { IconButton } from "../IconButton";
import { Space } from "@/lib/space";

describe("IconButton", () => {
  it("uses a button role and a 44-point hit target", async () => {
    const onPress = jest.fn();
    const { getByRole } = await render(
      <IconButton name="copy" accessibilityLabel="Copy" onPress={onPress} />,
    );
    const button = getByRole("button");
    expect(button.props.accessibilityLabel).toBe("Copy");
    expect(button.props.style).toEqual(
      expect.arrayContaining([
        expect.objectContaining({ minWidth: Space.minTouch, minHeight: Space.minTouch }),
      ]),
    );
    fireEvent.press(button);
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
