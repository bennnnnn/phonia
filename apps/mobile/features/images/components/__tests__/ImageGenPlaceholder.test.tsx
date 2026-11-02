import { act, fireEvent, render } from "@testing-library/react-native";

import { ImageGenPlaceholder } from "@/features/images/components/ImageGenPlaceholder";

/** The stage line and the pill are hidden from screen readers; the card label carries them. */
const hidden = { includeHiddenElements: true };

/** The shimmer band needs the stage line's measured width. */
async function layOutStage(view: Awaited<ReturnType<typeof render>>) {
  await fireEvent(view.getByTestId("image-gen-stage", hidden), "layout", {
    nativeEvent: { layout: { x: 0, y: 0, width: 120, height: 22 } },
  });
}

const mockUseReduceMotion = jest.fn(() => false);

jest.mock("react-i18next", () => {
  const en = jest.requireActual("@/lib/i18n/en.json") as Record<string, string>;
  const t = (key: string, options?: Record<string, unknown>) => {
    const template = en[key];
    if (typeof template !== "string") return key;
    return template.replace(/\{\{(\w+)\}\}/g, (_match, name: string) =>
      String(options?.[name] ?? ""),
    );
  };
  return { useTranslation: () => ({ t }) };
});
// A build where the repo probe allows Skia: the wave is the shader canvas.
jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => true }));
jest.mock("@/features/attachments/components/ChatMessageImage", () => ({
  useThumbnailSize: () => ({ width: 148, height: 189 }),
}));
jest.mock("@/lib/motion", () => ({
  ...jest.requireActual("@/lib/motion"),
  useReduceMotion: () => mockUseReduceMotion(),
}));
jest.mock("@/lib/haptics", () => ({ tap: jest.fn(), selection: jest.fn() }));
jest.mock("expo-linear-gradient", () => {
  const { View: MockView } = jest.requireActual("react-native");
  return { LinearGradient: MockView };
});

describe("ImageGenPlaceholder", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockUseReduceMotion.mockReturnValue(false);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("shows the stage line above the card and an estimated percentage", async () => {
    const view = await render(<ImageGenPlaceholder />);

    expect(view.getByText("Sketching it out", hidden)).toBeOnTheScreen();
    expect(view.getByTestId("image-gen-progress", hidden)).toHaveTextContent("1%");
    expect(view.getByLabelText("Sketching it out, 1%")).toBeOnTheScreen();
    expect(await view.findByTestId("image-gen-dots-wave")).toBeOnTheScreen();
    expect(view.queryByTestId("image-gen-dots-cutout")).toBeNull();
    await layOutStage(view);
    expect(view.getByTestId("image-gen-stage-shimmer", hidden)).toBeOnTheScreen();

    await act(async () => {
      jest.advanceTimersByTime(4_000);
    });
    expect(view.getByText("Setting the scene", hidden)).toBeOnTheScreen();
    expect(view.getByTestId("image-gen-progress", hidden)).toHaveTextContent("27%");

    await act(async () => {
      jest.advanceTimersByTime(120_000);
    });
    expect(view.getByText("Almost there", hidden)).toBeOnTheScreen();
    expect(view.getByTestId("image-gen-progress", hidden)).toHaveTextContent("95%");
  });

  it("keeps still dots and no shimmer under Reduce Motion", async () => {
    mockUseReduceMotion.mockReturnValue(true);
    const view = await render(<ImageGenPlaceholder />);
    await layOutStage(view);

    expect(view.getByTestId("image-gen-dots-static")).toBeOnTheScreen();
    expect(view.queryByTestId("image-gen-dots-wave")).toBeNull();
    expect(view.queryByTestId("image-gen-stage-shimmer", hidden)).toBeNull();
  });

  it("shows the failure, still dots and Retry, without a percentage or game", async () => {
    const onRetry = jest.fn();
    const view = await render(
      <ImageGenPlaceholder outcome="failed" statusText="The model is busy" onRetry={onRetry} />,
    );
    await layOutStage(view);

    expect(view.getByText("The model is busy", hidden)).toBeOnTheScreen();
    expect(view.getByLabelText("The model is busy")).toBeOnTheScreen();
    expect(view.getByTestId("image-gen-dots-static")).toBeOnTheScreen();
    expect(view.queryByTestId("image-gen-progress", hidden)).toBeNull();
    expect(view.queryByTestId("image-gen-play")).toBeNull();
    expect(view.queryByTestId("image-gen-stage-shimmer", hidden)).toBeNull();

    await fireEvent.press(view.getByText("Retry"));
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it("says a stopped picture won't count toward the day, since the server stops it too", async () => {
    const view = await render(<ImageGenPlaceholder outcome="canceled" />);
    expect(view.getByText("Stopped. This picture won't count toward today's limit.", hidden)).toBeOnTheScreen();
    expect(view.queryByText("Retry")).toBeNull();
  });

  it("turns into the dot game on tap, steers on a tap, and stops on a long press", async () => {
    const view = await render(<ImageGenPlaceholder />);

    const play = view.getByTestId("image-gen-play");
    expect(play.props.accessibilityHint).toBe("Starts a small dot game while the image is made");
    await fireEvent.press(play);

    expect(view.getByTestId("image-gen-dots-play")).toBeOnTheScreen();
    expect(view.queryByTestId("image-gen-dots-wave")).toBeNull();
    expect(view.getByTestId("image-gen-progress", hidden)).toBeOnTheScreen();
    const surface = view.getByTestId("image-gen-play-surface");
    expect(surface.props.accessibilityHint).toBe(
      "Tap a spot to steer the dots. Long-press to stop.",
    );

    await fireEvent.press(surface, { nativeEvent: { locationX: 20, locationY: 20 } });
    await act(async () => {
      jest.advanceTimersByTime(140 * 6);
    });
    expect(view.getByTestId("image-gen-dots-play")).toBeOnTheScreen();

    await fireEvent(view.getByTestId("image-gen-play-surface"), "longPress");
    expect(view.queryByTestId("image-gen-dots-play")).toBeNull();
    expect(view.getByTestId("image-gen-play")).toBeOnTheScreen();
  });
});
