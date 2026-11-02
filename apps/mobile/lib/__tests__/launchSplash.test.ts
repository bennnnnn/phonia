const mockSplash = { preventAutoHideAsync: jest.fn(async () => true), hide: jest.fn() };
jest.mock("expo-splash-screen", () => mockSplash);

type LaunchSplash = typeof import("@/lib/launchSplash");

function freshSplash(): LaunchSplash {
  let loaded!: LaunchSplash;
  jest.isolateModules(() => {
    loaded = jest.requireActual<LaunchSplash>("@/lib/launchSplash");
  });
  return loaded;
}

const FRAME_MS = 16;

beforeEach(() => {
  jest.useFakeTimers();
  jest.clearAllMocks();
  // One frame after the first screen is ready.
  globalThis.requestAnimationFrame = (callback: FrameRequestCallback) =>
    setTimeout(() => callback(0), FRAME_MS) as unknown as number;
});
afterEach(() => {
  jest.useRealTimers();
});

describe("launch splash", () => {
  it("keeps the splash until the session, the fonts and the preferences are ready", () => {
    const splash = freshSplash();
    expect(mockSplash.preventAutoHideAsync).toHaveBeenCalledTimes(1);

    splash.markLaunchReady("prefs");
    splash.markLaunchReady("session");
    jest.advanceTimersByTime(100);
    expect(mockSplash.hide).not.toHaveBeenCalled();

    splash.markLaunchReady("fonts");
    expect(mockSplash.hide).not.toHaveBeenCalled();
    jest.advanceTimersByTime(FRAME_MS);
    expect(mockSplash.hide).toHaveBeenCalledTimes(1);

    // Later marks (a retried sign-in, say) leave it alone.
    splash.markLaunchReady("session");
    jest.advanceTimersByTime(5_000);
    expect(mockSplash.hide).toHaveBeenCalledTimes(1);
  });

  it("at the deadline, uncovers the screen drawn so far once its fonts gate is open", () => {
    const splash = freshSplash();
    const told = jest.fn();
    splash.subscribeLaunchDeadline(told);
    splash.markLaunchReady("fonts");
    splash.markLaunchReady("prefs");

    jest.advanceTimersByTime(splash.SPLASH_MAX_MS - 1);
    expect(splash.launchDeadlinePassed()).toBe(false);
    expect(mockSplash.hide).not.toHaveBeenCalled();

    // The session still waits on /auth/me: its own loading state shows.
    jest.advanceTimersByTime(1);
    expect(told).toHaveBeenCalledTimes(1);
    expect(splash.launchDeadlinePassed()).toBe(true);
    jest.advanceTimersByTime(FRAME_MS);
    expect(mockSplash.hide).toHaveBeenCalledTimes(1);
  });

  it("with fonts still loading at the deadline, waits for the app to draw without them", () => {
    const splash = freshSplash();
    splash.markLaunchReady("prefs");
    splash.markLaunchReady("session");

    jest.advanceTimersByTime(splash.SPLASH_MAX_MS + 100);
    // No blank frame: the root layout now draws with the system face first.
    expect(mockSplash.hide).not.toHaveBeenCalled();
    splash.markLaunchReady("fonts");
    jest.advanceTimersByTime(FRAME_MS);
    expect(mockSplash.hide).toHaveBeenCalledTimes(1);
  });

  it("goes anyway if the app never draws at all", () => {
    freshSplash();
    jest.advanceTimersByTime(1_999);
    expect(mockSplash.hide).not.toHaveBeenCalled();
    jest.advanceTimersByTime(1);
    expect(mockSplash.hide).toHaveBeenCalledTimes(1);
    jest.advanceTimersByTime(10_000);
    expect(mockSplash.hide).toHaveBeenCalledTimes(1);
  });
});
