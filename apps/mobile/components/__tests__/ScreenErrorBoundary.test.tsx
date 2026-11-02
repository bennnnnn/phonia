// A screen that throws while it renders shows the shared error view in its
// place, under the real Expo Router: the chat under it stays mounted, Try
// again draws the screen afresh, and the crash is reported once. The root
// layout's boundary is the same view, standing in for the whole app.
import "./support/expoGlobal";

import { StyleSheet, Text } from "react-native";
import { Stack, router } from "expo-router";
import { act, fireEvent, renderRouter, screen } from "expo-router/testing-library";

import { ScreenErrorBoundary } from "@/components/ScreenErrorBoundary";
import { ACCENT_OPTIONS } from "@/lib/accent";
import { setAccentSnapshot } from "@/lib/accentRuntime";
import { resetAppearanceRuntime, setAppearancePreferenceSnapshot } from "@/lib/appearanceRuntime";
import { reportBoundaryError } from "@/lib/sentry";
import { themeFor } from "@/lib/theme";

jest.mock("@/lib/sentry", () => ({ reportBoundaryError: jest.fn() }));
// What the router reads from `expo`: no splash screen and no native views here.
jest.mock("expo", () => ({
  requireOptionalNativeModule: () => null,
  requireNativeView: () => () => null,
  registerRootComponent: jest.fn(),
}));
// An ES module the router imports for one constructor; Jest here loads CommonJS.
jest.mock("standard-navigation", () => ({
  createStandardNavigator: (NavigatorContent: unknown) => ({
    type: "standard",
    version: 1,
    NavigatorContent,
  }),
}));

/** While true, the page throws each time it renders. */
let failing = false;
/** While true, the chat throws each time it renders. */
let chatFailing = false;

function ProfilePage() {
  if (failing) throw new Error("profile render failed");
  return <Text>profile page</Text>;
}

function ChatScreen() {
  if (chatFailing) throw new Error("chat render failed");
  return <Text>chat screen</Text>;
}

/** The app's root stack (app/_layout.tsx): only To-do and the Library take its header. */
function AppStack() {
  return (
    <Stack screenOptions={{ headerShown: false }}>
      <Stack.Screen name="todos" options={{ headerShown: true }} />
    </Stack>
  );
}

const ROOT_LAYOUT = { default: AppStack, ErrorBoundary: ScreenErrorBoundary };

/** The app's shape: the root layout and the section layouts export the shared view. */
function routes(pageBoundary: typeof ScreenErrorBoundary | undefined) {
  return {
    _layout: ROOT_LAYOUT,
    index: ChatScreen,
    "settings/_layout": () => <Stack />,
    "settings/profile": pageBoundary
      ? { default: ProfilePage, ErrorBoundary: pageBoundary }
      : ProfilePage,
    "memory/[key]": { default: ProfilePage, ErrorBoundary: ScreenErrorBoundary },
  };
}

async function openProfileThatThrows(pageBoundary?: typeof ScreenErrorBoundary) {
  await renderRouter(routes(pageBoundary), { initialUrl: "/" });
  expect(screen.getByText("chat screen")).toBeTruthy();
  failing = true;
  await act(async () => router.push("/settings/profile"));
}

/** The chat draws, then throws on its next render. */
async function crashTheChat() {
  await renderRouter(routes(undefined), { initialUrl: "/" });
  expect(screen.getByText("chat screen")).toBeTruthy();
  chatFailing = true;
  await act(async () => router.setParams({ draft: "a private draft" }));
}

// Each case starts with nothing failing and nothing reported.
const consoleError = jest.spyOn(console, "error").mockImplementation(() => undefined);
const consoleWarn = jest.spyOn(console, "warn").mockImplementation(() => undefined);
beforeEach(() => {
  jest.clearAllMocks();
  failing = false;
  chatFailing = false;
});
afterAll(() => {
  consoleError.mockRestore();
  consoleWarn.mockRestore();
});

describe("a screen that throws while it renders", () => {
  it("shows the screen's error view while the chat under it stays", async () => {
    await openProfileThatThrows(ScreenErrorBoundary);

    expect(screen.getByText("common.screen_error_title")).toBeTruthy();
    expect(screen.getByText("common.screen_error_body")).toBeTruthy();
    expect(screen.getByText("chat screen", { includeHiddenElements: true })).toBeTruthy();
    expect(screen.queryByText("profile page")).toBeNull();
  });

  it("draws the screen again on Try again", async () => {
    await openProfileThatThrows(ScreenErrorBoundary);
    failing = false;

    await fireEvent.press(screen.getByRole("button", { name: "common.try_again" }));

    expect(screen.getByText("profile page")).toBeTruthy();
    expect(screen.queryByText("common.screen_error_title")).toBeNull();
  });

  it("reports the crash once, with the route and never its values", async () => {
    await renderRouter(routes(ScreenErrorBoundary), { initialUrl: "/" });
    failing = true;
    await act(async () => router.push("/memory/area:private-topic"));
    await act(async () => router.setParams({ key: "area:private-topic" }));
    // Another screen opens over it (a notification's link): still the one report.
    await act(async () => router.push("/"));

    expect(screen.getByText("common.screen_error_title", { includeHiddenElements: true })).toBeTruthy();
    expect(reportBoundaryError).toHaveBeenCalledTimes(1);
    expect(reportBoundaryError).toHaveBeenCalledWith(
      "screen",
      expect.objectContaining({ message: "profile render failed" }),
      null,
      "memory/[key]",
    );
    expect(JSON.stringify(jest.mocked(reportBoundaryError).mock.calls)).not.toContain("private");
  });

  it("on a section's stack layout, catches a crash on any of its pages, not the root", async () => {
    // Settings and Memory: their routes stay one line, so the boundary is the layout's.
    await renderRouter(
      {
        _layout: ROOT_LAYOUT,
        index: ChatScreen,
        "settings/_layout": { default: () => <Stack />, ErrorBoundary: ScreenErrorBoundary },
        "settings/profile": ProfilePage,
      },
      { initialUrl: "/" },
    );
    failing = true;
    await act(async () => router.push("/settings/profile"));

    expect(screen.getByText("common.screen_error_title")).toBeTruthy();
    // The root's would have replaced the chat too.
    expect(screen.getByText("chat screen", { includeHiddenElements: true })).toBeTruthy();
    expect(reportBoundaryError).toHaveBeenCalledTimes(1);

    failing = false;
    await fireEvent.press(screen.getByRole("button", { name: "common.try_again" }));
    expect(screen.getByText("profile page")).toBeTruthy();
  });

  it("without its own boundary, falls to the root's, which stands in for the whole app", async () => {
    await openProfileThatThrows();

    expect(screen.queryByText("chat screen", { includeHiddenElements: true })).toBeNull();
    expect(screen.getByText("common.screen_error_title")).toBeTruthy();
    expect(reportBoundaryError).toHaveBeenCalledTimes(1);
  });
});

describe("a crash only the root's boundary catches (the chat, the sign-in flow)", () => {
  const resetLook = () => {
    resetAppearanceRuntime();
    setAccentSnapshot("indigo");
  };
  beforeEach(resetLook);
  afterAll(resetLook);

  it("shows the translated view, never the router's English one or the error's text", async () => {
    await crashTheChat();

    expect(screen.getByText("common.screen_error_title")).toBeTruthy();
    expect(screen.getByText("common.screen_error_body")).toBeTruthy();
    expect(screen.queryByText("Something went wrong")).toBeNull();
    expect(screen.queryByText(/chat render failed/)).toBeNull();
  });

  it("reports it once, as the chat's file, without the route's values", async () => {
    await crashTheChat();
    await act(async () => router.setParams({ draft: "another private draft" }));

    expect(reportBoundaryError).toHaveBeenCalledTimes(1);
    expect(reportBoundaryError).toHaveBeenCalledWith(
      "screen",
      expect.objectContaining({ message: "chat render failed" }),
      null,
      "index",
    );
    expect(JSON.stringify(jest.mocked(reportBoundaryError).mock.calls)).not.toContain("private");
  });

  it("draws the whole app again on Try again", async () => {
    await crashTheChat();
    chatFailing = false;

    await fireEvent.press(screen.getByRole("button", { name: "common.try_again" }));

    expect(screen.getByText("chat screen")).toBeTruthy();
    expect(screen.queryByText("common.screen_error_title")).toBeNull();
  });

  it.each(
    (["light", "dark"] as const).flatMap((scheme) => ACCENT_OPTIONS.map((accent) => [scheme, accent] as const)),
  )("paints the page itself in %s mode, %s accent: no stack is left behind it", async (scheme, accent) => {
    setAppearancePreferenceSnapshot(scheme);
    setAccentSnapshot(accent);
    const theme = themeFor(scheme, accent);
    await crashTheChat();

    expect(StyleSheet.flatten(screen.getByTestId("screen-error").props.style).backgroundColor).toBe(theme.bg);
    const title = screen.getByText("common.screen_error_title");
    expect(StyleSheet.flatten(title.props.style).color).toBe(theme.text);
  });
});

describe("the way back from a screen's error view", () => {
  function SettingsHome() {
    if (failing) throw new Error("settings render failed");
    return <Text>settings home</Text>;
  }

  /** app/settings/_layout.tsx: its home draws no header; its pages take the stack's. */
  const SECTION = {
    "settings/_layout": {
      default: () => (
        <Stack>
          <Stack.Screen name="index" options={{ headerShown: false }} />
        </Stack>
      ),
      ErrorBoundary: ScreenErrorBoundary,
    },
    "settings/index": SettingsHome,
    "settings/profile": ProfilePage,
  };

  const back = () => screen.queryByRole("button", { name: "common.back" });

  async function crashOn(path: string, app: object = { _layout: ROOT_LAYOUT, index: ChatScreen, ...SECTION }) {
    await renderRouter(app as Parameters<typeof renderRouter>[0], { initialUrl: "/" });
    await act(async () => router.push(path));
    failing = true;
    await act(async () => router.setParams({ x: "1" }));
    expect(screen.getByText("common.screen_error_title")).toBeTruthy();
  }

  it.each(["/settings", "/settings/profile"])(
    "with no header (%s: the section's stack went with it), has a Back to the chat",
    async (path) => {
      await crashOn(path);

      await fireEvent.press(back()!);

      expect(screen.getByText("chat screen")).toBeTruthy();
      expect(screen.queryByText("common.screen_error_title", { includeHiddenElements: true })).toBeNull();
    },
  );

  it("under its own header (To-do), adds none: the header has one", async () => {
    await crashOn("/todos", {
      _layout: ROOT_LAYOUT,
      index: ChatScreen,
      todos: { default: ProfilePage, ErrorBoundary: ScreenErrorBoundary },
    });

    expect(back()).toBeNull();
  });

  it("at the root, has none: no screen is left under it", async () => {
    // A Settings page without the section's boundary: the chat was under it.
    await crashOn("/settings/profile", {
      _layout: ROOT_LAYOUT,
      index: ChatScreen,
      "settings/_layout": () => <Stack />,
      "settings/profile": ProfilePage,
    });

    expect(screen.queryByText("chat screen", { includeHiddenElements: true })).toBeNull();
    expect(back()).toBeNull();
    expect(screen.getByRole("button", { name: "common.try_again" })).toBeTruthy();
  });

  /** app/memory/_layout.tsx: a crash takes the page's header with the stack. */
  const MEMORY = {
    "memory/_layout": { default: () => <Stack />, ErrorBoundary: ScreenErrorBoundary },
    "memory/[key]": ProfilePage,
  };

  it.each(["/settings", "/settings/profile", "/memory/notes"])(
    "opened with nothing under it (%s from a link at launch), has a Back to the chat",
    async (path) => {
      await renderRouter({ _layout: ROOT_LAYOUT, index: ChatScreen, ...SECTION, ...MEMORY }, { initialUrl: path });
      failing = true;
      await act(async () => router.setParams({ x: "1" }));
      expect(screen.getByText("common.screen_error_title")).toBeTruthy();
      expect(screen.queryByText("chat screen", { includeHiddenElements: true })).toBeNull();
      expect(back()).toBeTruthy();

      await fireEvent.press(back()!);

      expect(screen.getByText("chat screen")).toBeTruthy();
      expect(screen.queryByText("common.screen_error_title", { includeHiddenElements: true })).toBeNull();
    },
  );
});
