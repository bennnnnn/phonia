import React from "react";
import { useFonts } from "expo-font";
import { act, render } from "@testing-library/react-native";

import { useLaunchFonts } from "@/hooks/useLaunchFonts";
import { launchDeadlinePassed, markLaunchReady, subscribeLaunchDeadline } from "@/lib/launchSplash";

jest.mock("expo-font", () => ({ useFonts: jest.fn() }));
jest.mock("@/lib/appFonts", () => ({ APP_FONT_FACES: {} }));
const mockDeadline = new Set<() => void>();
jest.mock("@/lib/launchSplash", () => ({
  launchDeadlinePassed: jest.fn(() => false),
  markLaunchReady: jest.fn(),
  subscribeLaunchDeadline: jest.fn((listener: () => void) => {
    mockDeadline.add(listener);
    return () => mockDeadline.delete(listener);
  }),
}));

const fonts = useFonts as jest.Mock;
let renders = 0;
let ready = false;
function Probe() {
  const value = useLaunchFonts();
  // Counts commits: a re-render of the app would commit again.
  React.useLayoutEffect(() => {
    ready = value;
    renders += 1;
  });
  return null;
}

beforeEach(() => {
  jest.clearAllMocks();
  mockDeadline.clear();
  renders = 0;
  (launchDeadlinePassed as jest.Mock).mockReturnValue(false);
});

describe("useLaunchFonts", () => {
  it("draws at once when every face is registered, and never re-renders for the deadline", async () => {
    fonts.mockReturnValue([true, null]);
    await render(<Probe />);
    expect(ready).toBe(true);
    expect(markLaunchReady).toHaveBeenCalledWith("fonts");
    expect(subscribeLaunchDeadline).not.toHaveBeenCalled();
    const before = renders;
    await act(async () => { for (const listener of [...mockDeadline]) listener(); });
    expect(renders).toBe(before);
  });

  it("waits for the faces, then draws with what is in once the launch deadline passes", async () => {
    fonts.mockReturnValue([false, null]);
    await render(<Probe />);
    expect(ready).toBe(false);
    expect(markLaunchReady).not.toHaveBeenCalled();
    await act(async () => { for (const listener of [...mockDeadline]) listener(); });
    expect(ready).toBe(true);
    expect(markLaunchReady).toHaveBeenCalledWith("fonts");
    expect(mockDeadline.size).toBe(0);
  });

  it("stops listening once the faces are in, and draws for a failed load too", async () => {
    fonts.mockReturnValue([false, null]);
    const view = await render(<Probe />);
    expect(mockDeadline.size).toBe(1);
    fonts.mockReturnValue([false, new Error("font file missing")]);
    await view.rerender(<Probe />);
    expect(ready).toBe(true);
    expect(mockDeadline.size).toBe(0);
  });

  it("counts a deadline that passed before it started listening", async () => {
    fonts.mockReturnValue([false, null]);
    (launchDeadlinePassed as jest.Mock).mockReturnValueOnce(false).mockReturnValue(true);
    await render(<Probe />);
    expect(ready).toBe(true);
  });
});
