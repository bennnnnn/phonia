import { act, render } from "@testing-library/react-native";
import { AccessibilityInfo, Platform } from "react-native";

import { ActionBanner } from "../ActionBanner";
import { Layer } from "@/lib/layer";

jest.mock("react-native-safe-area-context", () => ({
  useSafeAreaInsets: () => ({ top: 0, bottom: 34, left: 0, right: 0 }),
}));

jest.mock("@/lib/colorScheme", () => ({
  useResolvedColorScheme: () => "light",
}));

jest.mock("@/lib/motion", () => {
  const actual = jest.requireActual("@/lib/motion") as typeof import("@/lib/motion");
  return {
    ...actual,
    useReduceMotion: () => true,
  };
});

describe("ActionBanner", () => {
  beforeEach(() => {
    jest.useFakeTimers();
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("is spoken by VoiceOver when it appears, since iOS has no live regions", async () => {
    const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);
    announce.mockClear();
    const view = await render(<ActionBanner message="Archived 3 conversations" onDismiss={jest.fn()} />);
    expect(announce).toHaveBeenCalledTimes(1);
    expect(announce).toHaveBeenCalledWith("Archived 3 conversations");
    await view.rerender(<ActionBanner message="Archived 3 conversations" onDismiss={jest.fn()} />);
    expect(announce).toHaveBeenCalledTimes(1);
    announce.mockRestore();
  });

  it("leaves TalkBack to its live region", async () => {
    jest.replaceProperty(Platform, "OS", "android");
    const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);
    announce.mockClear();
    const { getByLabelText } = await render(<ActionBanner message="Saved" onDismiss={jest.fn()} />);
    expect(getByLabelText("Saved").props.accessibilityLiveRegion).toBe("polite");
    expect(announce).not.toHaveBeenCalled();
    announce.mockRestore();
    jest.restoreAllMocks();
  });

  it("renders an in-tree host instead of a native Modal", async () => {
    const { getByTestId, getByLabelText } = await render(
      <ActionBanner message="Saved" onDismiss={jest.fn()} />,
    );

    expect(getByTestId("action-banner-host")).toBeOnTheScreen();
    expect(getByTestId("action-banner-host")).toHaveStyle({
      position: "absolute",
      zIndex: Layer.toast,
    });
    expect(getByLabelText("Saved")).toBeOnTheScreen();
  });

  it("rides a lift above its offset, and moves nothing without one", async () => {
    const lifted = await render(
      <ActionBanner message="Saved" onDismiss={jest.fn()} lift={{ value: 120 } as never} />,
    );
    expect(lifted.getByTestId("action-banner-host")).toHaveStyle({
      transform: [{ translateY: -120 }],
    });

    const resting = await render(<ActionBanner message="Saved" onDismiss={jest.fn()} />);
    expect(resting.getByTestId("action-banner-host").props.style).not.toEqual(
      expect.arrayContaining([expect.objectContaining({ transform: expect.anything() })]),
    );
  });

  it("dismisses a success after two seconds", async () => {
    const onDismiss = jest.fn();
    await render(<ActionBanner message="Saved" tone="success" onDismiss={onDismiss} />);
    await act(async () => {
      jest.advanceTimersByTime(1999);
    });
    expect(onDismiss).not.toHaveBeenCalled();
    await act(async () => {
      jest.advanceTimersByTime(1);
    });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("keeps an error up for five seconds", async () => {
    const onDismiss = jest.fn();
    await render(
      <ActionBanner message="Could not save" tone="error" onDismiss={onDismiss} />,
    );
    await act(async () => {
      jest.advanceTimersByTime(4999);
    });
    expect(onDismiss).not.toHaveBeenCalled();
    await act(async () => {
      jest.advanceTimersByTime(1);
    });
    expect(onDismiss).toHaveBeenCalledTimes(1);
  });

  it("uses an assertive live region for errors", async () => {
    const { getByLabelText } = await render(
      <ActionBanner message="Could not save" tone="error" onDismiss={jest.fn()} />,
    );

    expect(getByLabelText("Could not save").props.accessibilityLiveRegion).toBe(
      "assertive",
    );
  });

  it("is a white pill with black ink over a photo viewer", async () => {
    const { lightTheme } = jest.requireActual("@/lib/theme") as typeof import("@/lib/theme");
    const { getByLabelText, getByText } = await render(
      <ActionBanner message="Saved" appearance="media" onDismiss={jest.fn()} />,
    );
    expect(getByLabelText("Saved")).toHaveStyle({ backgroundColor: lightTheme.onMedia });
    expect(getByText("Saved")).toHaveStyle({ color: lightTheme.mediaScrim });
  });
});
