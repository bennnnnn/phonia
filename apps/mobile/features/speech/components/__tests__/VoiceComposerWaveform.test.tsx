import type { SharedValue } from "react-native-reanimated";
import { StyleSheet } from "react-native";
import { render } from "@testing-library/react-native";

import { VoiceComposerWaveform } from "@/features/speech/components/VoiceComposerWaveform";
import { lightTheme } from "@/lib/theme";

jest.mock("react-native-reanimated", () => {
  const { View } = jest.requireActual("react-native");
  const linear = (t: number) => t;
  return {
    __esModule: true,
    default: { View },
    Easing: {
      linear,
      ease: linear,
      sin: linear,
      inOut: () => linear,
      out: () => linear,
      in: () => linear,
      cubic: linear,
    },
    useSharedValue: (init: number) => ({ value: init }),
    useAnimatedStyle: (fn: () => object) => fn(),
    useAnimatedReaction: () => undefined,
    withTiming: (v: number) => v,
    withRepeat: (v: number) => v,
  };
});

describe("VoiceComposerWaveform", () => {
  it("shows Transcribing… instead of a live listening wave", async () => {
    const { getByText, queryByText } = await render(
      <VoiceComposerWaveform recording={false} transcribing meterLevel={{ value: 0.2 } as SharedValue<number>} />,
    );
    expect(getByText("chat.voice_transcribing")).toBeOnTheScreen();
    expect(queryByText("chat.voice_listening")).toBeNull();
  });

  it("draws the bars in the same ink as the composer icons", async () => {
    const { getAllByTestId } = await render(
      <VoiceComposerWaveform recording meterLevel={{ value: 0.4 } as SharedValue<number>} transcribing={false} />,
    );
    const bars = getAllByTestId("voice-waveform-bar");
    expect(bars.length).toBeGreaterThan(0);
    expect(
      bars.every((node) => StyleSheet.flatten(node.props.style).backgroundColor === lightTheme.text),
    ).toBe(true);
  });
});
