import { AccessibilityInfo } from "react-native";
import { fireEvent, render } from "@testing-library/react-native";

import { DrawerProvider } from "@/contexts/DrawerContext";
import { LiveTalkOverlay } from "@/features/speech/components/LiveTalkOverlay";

jest.mock("@/lib/motion", () => ({
  useReduceMotion: () => true,
  Motion: { duration: { soft: 200, snappy: 200 }, easing: { inOut: undefined, in: undefined } },
}));

jest.mock("expo-linear-gradient", () => {
  const { View } = jest.requireActual("react-native") as typeof import("react-native");
  return { LinearGradient: View };
});

describe("LiveTalkOverlay", () => {
  const base = {
    visible: true,
    recording: false,
    headerInset: 96,
    composerClearance: 88,
    onToggle: jest.fn(),
  };

  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("leaves the header strip open, and takes it while the drawer hides the header", async () => {
    const controls = { open: jest.fn(), close: jest.fn(), isOpenNow: () => false };
    const view = await render(
      <DrawerProvider controls={controls} isOpen={false}>
        <LiveTalkOverlay {...base} phase="recording" recording />
      </DrawerProvider>,
    );
    expect(view.getByTestId("live-talk-overlay")).toHaveStyle({ top: 96, bottom: 88 });

    await view.rerender(
      <DrawerProvider controls={controls} isOpen>
        <LiveTalkOverlay {...base} phase="recording" recording />
      </DrawerProvider>,
    );
    expect(view.getByTestId("live-talk-overlay")).toHaveStyle({ top: 0, bottom: 88 });
  });

  it("does not pause from the orb and has no Listening/Speaking copy", async () => {
    const onToggle = jest.fn();
    const { getByTestId, queryByText } = await render(
      <LiveTalkOverlay {...base} phase="speaking" onToggle={onToggle} />,
    );

    expect(queryByText("chat.live_talk_speaking")).toBeNull();
    expect(queryByText("chat.live_talk_listening")).toBeNull();
    await fireEvent.press(getByTestId("live-talk-orb"));
    expect(onToggle).not.toHaveBeenCalled();
  });

  it("uses a listen visual while recording and a speak visual while the assistant talks", async () => {
    const listen = await render(<LiveTalkOverlay {...base} phase="recording" recording />);
    expect(listen.getByTestId("live-talk-orb-listen")).toBeTruthy();
    expect(listen.getByTestId("live-talk-orb-eyes")).toBeTruthy();
    const speak = await render(<LiveTalkOverlay {...base} phase="speaking" />);
    expect(speak.getByTestId("live-talk-orb-speak")).toBeTruthy();
    expect(speak.getByTestId("live-talk-orb-eyes")).toBeTruthy();
  });

  it("starts below the chat header and above the composer", async () => {
    const { getByTestId } = await render(<LiveTalkOverlay {...base} phase="idle" />);
    expect(getByTestId("live-talk-overlay")).toHaveStyle({ top: 96, bottom: 88 });
  });

  // S7.13: one label served listening and speaking, and no change was announced.
  it("gives the orb a distinct screen-reader label for listening, thinking and speaking", async () => {
    const labels: (string | undefined)[] = [];
    for (const phase of ["recording", "thinking", "speaking"] as const) {
      const view = await render(<LiveTalkOverlay {...base} phase={phase} />);
      labels.push(view.getByTestId("live-talk-orb").props.accessibilityLabel);
      await view.unmount();
    }
    expect(labels).toEqual([
      "chat.live_talk_listening_a11y",
      "chat.live_talk_thinking_a11y",
      "chat.live_talk_speaking_a11y",
    ]);
  });

  it("announces each phase change to the screen reader, with no on-screen copy", async () => {
    const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility");
    const view = await render(<LiveTalkOverlay {...base} phase="recording" />);
    await view.rerender(<LiveTalkOverlay {...base} phase="thinking" />);
    await view.rerender(<LiveTalkOverlay {...base} phase="speaking" />);
    expect(announce.mock.calls.map(([text]) => text)).toEqual([
      "chat.live_talk_listening_a11y",
      "chat.live_talk_thinking_a11y",
      "chat.live_talk_speaking_a11y",
    ]);
    expect(view.queryByText("chat.live_talk_speaking_a11y")).toBeNull();
    announce.mockRestore();
  });
});
