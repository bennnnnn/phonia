// The factory re-runs after jest.resetModules(), so steer it through a
// mutable flag instead of a captured jest.fn.
let mockExpoGo = false;
jest.mock("@/lib/expoRuntime", () => ({ isExpoGo: () => mockExpoGo }));

function loadFresh(skiaImpl: () => unknown) {
  jest.resetModules();
  jest.doMock("@shopify/react-native-skia", skiaImpl);
  return require("@/lib/skiaAvailability") as typeof import("@/lib/skiaAvailability");
}

describe("isSkiaAvailable", () => {
  it("is always false in Expo Go without probing the native module", () => {
    mockExpoGo = true;
    const make = jest.fn();
    const mod = loadFresh(() => ({ Skia: { Path: { Make: make } } }));
    expect(mod.isSkiaAvailable()).toBe(false);
    expect(make).not.toHaveBeenCalled();
  });

  it("probes the native module on dev builds and caches the result", () => {
    mockExpoGo = false;
    const make = jest.fn(() => ({}));
    const mod = loadFresh(() => ({ Skia: { Path: { Make: make } } }));
    expect(mod.isSkiaAvailable()).toBe(true);
    expect(mod.isSkiaAvailable()).toBe(true);
    expect(make).toHaveBeenCalledTimes(1);
  });

  it("is false when the native module is missing (stale dev client)", () => {
    mockExpoGo = false;
    const mod = loadFresh(() => ({
      Skia: {
        Path: {
          Make: () => {
            throw new Error("Skia native module not linked");
          },
        },
      },
    }));
    expect(mod.isSkiaAvailable()).toBe(false);
  });
});
