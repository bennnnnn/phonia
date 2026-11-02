import { act, fireEvent, render } from "@testing-library/react-native";
import { StyleSheet } from "react-native";

import { ACCENTS } from "@/lib/accent";
import { setAccentSnapshot } from "@/lib/accentRuntime";

import { LiveTalkButton } from "../LiveTalkButton";

describe("LiveTalkButton", () => {
  afterEach(async () => {
    await act(async () => setAccentSnapshot("indigo"));
  });

  it("sits in a circle of the user's bubble tint that follows their accent", async () => {
    const view = await render(<LiveTalkButton size={40} onPress={() => undefined} />);
    const circle = () => StyleSheet.flatten(view.getByTestId("live-talk-circle").props.style);
    expect(circle()).toMatchObject({
      width: 40,
      height: 40,
      borderRadius: 20,
      backgroundColor: ACCENTS.indigo.light.userBubble,
    });
    await act(async () => setAccentSnapshot("berry"));
    expect(circle().backgroundColor).toBe(ACCENTS.berry.light.userBubble);
  });

  it("starts live talk when tapped", async () => {
    const onPress = jest.fn();
    const view = await render(<LiveTalkButton size={40} onPress={onPress} />);
    fireEvent.press(view.getByTestId("live-talk-button"));
    expect(onPress).toHaveBeenCalledTimes(1);
  });
});
