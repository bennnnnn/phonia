import { act, render } from "@testing-library/react-native";

import ActionShimmerMotion from "../ActionShimmerMotion";

const mockUseReduceMotion = jest.fn(() => false);

jest.mock("@/lib/motion", () => ({
  Motion: {
    easing: { inOut: undefined },
  },
  useReduceMotion: () => mockUseReduceMotion(),
}));
jest.mock("react-native-reanimated", () => {
  const { View: RNView } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    __esModule: true,
    default: { View: RNView },
    cancelAnimation: jest.fn(),
    useAnimatedStyle: (factory: () => object) => factory(),
    useSharedValue: (value: number) => ({ value }),
    withRepeat: (value: number) => value,
    withTiming: (value: number) => value,
  };
});
jest.mock("expo-linear-gradient", () => {
  const { View: RNView } = jest.requireActual("react-native") as typeof import("react-native");
  return {
    LinearGradient: (props: React.ComponentProps<typeof RNView>) => <RNView {...props} />,
  };
});

describe("ActionShimmer", () => {
  beforeEach(() => {
    mockUseReduceMotion.mockReturnValue(false);
  });

  it("delays the shimmer band while keeping the status label visible", async () => {
    jest.useFakeTimers();
    try {
      const { getByText, queryByTestId } = await render(
        <ActionShimmerMotion label="Sending…" testID="sending" delayMs={220} />,
      );

      expect(getByText("Sending…")).toBeOnTheScreen();
      expect(queryByTestId("sending-band")).toBeNull();

      await act(async () => {
        jest.advanceTimersByTime(220);
      });

      expect(queryByTestId("sending-band")).toBeOnTheScreen();
    } finally {
      jest.useRealTimers();
    }
  });

  it("uses a static marker when Reduce Motion is enabled", async () => {
    mockUseReduceMotion.mockReturnValue(true);
    const { getByTestId, queryByTestId } = await render(
      <ActionShimmerMotion label="Saving…" testID="saving" delayMs={0} />,
    );

    expect(getByTestId("saving-static")).toBeOnTheScreen();
    expect(queryByTestId("saving-band")).toBeNull();
  });
});
