/**
 * Expo Go path: the repo probe says no Skia, so the card animates with the
 * Skia-free cutout wave and never loads `@shopify/react-native-skia`. Its own
 * file, so no other test has required Skia into this module registry first.
 */
import { act, fireEvent, render } from "@testing-library/react-native";

import { ImageGenPlaceholder } from "@/features/images/components/ImageGenPlaceholder";

const mockSkiaRequired = jest.fn();
const mockUseReduceMotion = jest.fn(() => false);

jest.mock("@/lib/skiaAvailability", () => ({ isSkiaAvailable: () => false }));
jest.mock("@shopify/react-native-skia", () => {
  mockSkiaRequired();
  return jest.requireActual("@shopify/react-native-skia");
});
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

describe("ImageGenPlaceholder without Skia", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    mockUseReduceMotion.mockReturnValue(false);
  });

  afterEach(() => {
    jest.useRealTimers();
  });

  it("animates with the cutout wave and never requires Skia", async () => {
    const view = await render(<ImageGenPlaceholder />);
    await act(async () => {
      jest.advanceTimersByTime(6_000);
    });

    expect(view.getByTestId("image-gen-dots-cutout")).toBeOnTheScreen();
    expect(view.getByTestId("image-gen-wave-band")).toBeOnTheScreen();
    expect(view.getByTestId("image-gen-wave-holes")).toBeOnTheScreen();
    expect(view.queryByTestId("image-gen-dots-wave")).toBeNull();
    expect(view.queryByTestId("image-gen-dots-static")).toBeNull();

    // The game and the failed card do not need Skia either.
    await fireEvent.press(view.getByTestId("image-gen-play"));
    expect(view.getByTestId("image-gen-dots-play")).toBeOnTheScreen();
    await view.rerender(<ImageGenPlaceholder outcome="failed" onRetry={jest.fn()} />);
    expect(view.getByTestId("image-gen-dots-static")).toBeOnTheScreen();

    expect(mockSkiaRequired).not.toHaveBeenCalled();
  });

  it("keeps still dots under Reduce Motion", async () => {
    mockUseReduceMotion.mockReturnValue(true);
    const view = await render(<ImageGenPlaceholder />);

    expect(view.getByTestId("image-gen-dots-static")).toBeOnTheScreen();
    expect(view.queryByTestId("image-gen-dots-cutout")).toBeNull();
    expect(mockSkiaRequired).not.toHaveBeenCalled();
  });
});
