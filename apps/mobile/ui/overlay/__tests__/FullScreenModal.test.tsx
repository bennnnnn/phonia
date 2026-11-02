import { fireEvent, render } from "@testing-library/react-native";
import { Text } from "react-native";

import { FullScreenModal } from "../FullScreenModal";

describe("FullScreenModal", () => {
  it("closes on VoiceOver's escape scrub, as on Android back", async () => {
    const onClose = jest.fn();
    const { getByTestId, getByText } = await render(
      <FullScreenModal visible onRequestClose={onClose}>
        <Text>page</Text>
      </FullScreenModal>,
    );

    expect(getByText("page")).toBeOnTheScreen();
    await fireEvent(getByTestId("full-screen-modal-page"), "accessibilityEscape");
    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
