import { renderHook } from "@testing-library/react-native";
import { AccessibilityInfo, Platform } from "react-native";

import { useLiveAnnouncement } from "../useLiveAnnouncement";

describe("useLiveAnnouncement", () => {
  afterEach(() => {
    jest.restoreAllMocks();
  });

  it("speaks text on iOS when it appears or changes, and nothing while it is null", async () => {
    const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);
    announce.mockClear();
    const hook = await renderHook(({ text }: { text: string | null }) => useLiveAnnouncement(text), {
      initialProps: { text: null as string | null },
    });
    expect(announce).not.toHaveBeenCalled();
    await hook.rerender({ text: "Couldn't share" });
    await hook.rerender({ text: "Couldn't share" });
    await hook.rerender({ text: "Name is required" });
    expect(announce.mock.calls).toEqual([["Couldn't share"], ["Name is required"]]);
  });

  it("leaves Android to the element's live region", async () => {
    jest.replaceProperty(Platform, "OS", "android");
    const announce = jest.spyOn(AccessibilityInfo, "announceForAccessibility").mockImplementation(() => undefined);
    announce.mockClear();
    await renderHook(() => useLiveAnnouncement("Saved"));
    expect(announce).not.toHaveBeenCalled();
  });
});
