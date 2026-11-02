const mockConstants: { expoConfig?: { version?: string }; platform?: Record<string, unknown> } = {};
// One object the mocks read when called, so every load sees the current test's value.
const mockState: { updates: { updateId: string | null; isEmbeddedLaunch: boolean } | null } = { updates: null };

jest.mock("expo-constants", () => ({ __esModule: true, default: mockConstants }));
jest.mock("expo-modules-core", () => ({
  requireOptionalNativeModule: (name: string) => (name === "ExpoUpdates" && mockState.updates ? {} : null),
}));
jest.mock(
  "expo-updates",
  () => ({
    get updateId() {
      return mockState.updates?.updateId ?? null;
    },
    get isEmbeddedLaunch() {
      return mockState.updates?.isEmbeddedLaunch ?? true;
    },
  }),
  { virtual: true },
);

function load() {
  let mod!: typeof import("@/lib/appVersion");
  jest.isolateModules(() => {
    mod = jest.requireActual<typeof import("@/lib/appVersion")>("@/lib/appVersion");
  });
  return mod;
}

beforeEach(() => {
  mockConstants.expoConfig = { version: "1.4.0" };
  mockConstants.platform = undefined;
  mockState.updates = null;
});

it("shows the binary's own build number next to the version", () => {
  mockConstants.platform = { ios: { buildNumber: "42" } };
  const { appVersion, versionLabel } = load();
  expect(versionLabel(appVersion())).toBe("1.4.0 (42)");
  mockConstants.platform = { android: { versionCode: 17 } };
  expect(load().appVersion().build).toBe("17");
});

it("has no build in Expo Go, and no update when the built-in bundle runs", () => {
  mockState.updates = { updateId: "ab12cd34-0000-4000-8000-000000000000", isEmbeddedLaunch: true };
  const { appVersion, versionLabel } = load();
  const app = appVersion();
  expect(versionLabel(app)).toBe("1.4.0");
  expect(app.update).toBeNull();
});

it("names the over-the-air update it runs by its id's first block", () => {
  mockState.updates = { updateId: "ab12cd34-0000-4000-8000-000000000000", isEmbeddedLaunch: false };
  expect(load().appVersion().update).toBe("ab12cd34");
});
