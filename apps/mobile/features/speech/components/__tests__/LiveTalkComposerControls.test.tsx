import { fireEvent, render } from "@testing-library/react-native";

import { LiveTalkComposerControls } from "@/features/speech/components/LiveTalkComposerControls";

describe("LiveTalkComposerControls", () => {
  it("puts mute next to close and turns red when muted", async () => {
    const onMutePress = jest.fn();
    const onClose = jest.fn();
    const { getByLabelText, getByTestId, rerender } = await render(
      <LiveTalkComposerControls muted={false} onMutePress={onMutePress} onClose={onClose} />,
    );

    await fireEvent.press(getByLabelText("chat.live_talk_mute_a11y"));
    expect(onMutePress).toHaveBeenCalled();
    await rerender(
      <LiveTalkComposerControls muted onMutePress={onMutePress} onClose={onClose} />,
    );
    expect(getByLabelText("chat.live_talk_unmute_a11y")).toBeTruthy();
    await fireEvent.press(getByTestId("live-talk-close"));
    expect(onClose).toHaveBeenCalled();
  });
});
