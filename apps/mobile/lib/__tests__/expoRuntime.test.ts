import Constants, { ExecutionEnvironment } from "expo-constants";

import { requireOptionalNativeModule } from "expo-modules-core";

import { canUseDeviceLocation, isExpoGo, isPhysicalDevice } from "@/lib/expoRuntime";

jest.mock("expo-constants", () => ({
  __esModule: true,
  default: {
    executionEnvironment: "storeClient",
    appOwnership: "expo",
    expoGoConfig: {},
  },
  ExecutionEnvironment: {
    Bare: "bare",
    Standalone: "standalone",
    StoreClient: "storeClient",
  },
}));

jest.mock("expo-modules-core", () => ({ requireOptionalNativeModule: jest.fn() }));

describe("expoRuntime", () => {
  it("exports location guard helpers", () => {
    expect(typeof isExpoGo).toBe("function");
    expect(typeof canUseDeviceLocation).toBe("function");
  });

  it("detects Expo Go", () => {
    (Constants as { executionEnvironment: string }).executionEnvironment =
      ExecutionEnvironment.StoreClient;
    (Constants as { appOwnership: string | null }).appOwnership = "expo";
    expect(isExpoGo()).toBe(true);
    expect(canUseDeviceLocation()).toBe(false);
  });

  it("does not treat bare dev builds as Expo Go even when expoGoConfig is set", () => {
    (Constants as { executionEnvironment: string }).executionEnvironment =
      ExecutionEnvironment.Bare;
    (Constants as { appOwnership: string | null }).appOwnership = null;
    expect(isExpoGo()).toBe(false);
    expect(canUseDeviceLocation()).toBe(true);
  });

  it("does not treat standalone builds as Expo Go", () => {
    (Constants as { executionEnvironment: string }).executionEnvironment =
      ExecutionEnvironment.Standalone;
    (Constants as { appOwnership: string | null }).appOwnership = null;
    expect(isExpoGo()).toBe(false);
  });

  it.each([
    ["a phone", { isDevice: true }, true],
    ["a simulator", { isDevice: false }, false],
    ["a binary built before expo-device", null, null],
  ])("tells %s apart", (_kind, device, expected) => {
    jest.mocked(requireOptionalNativeModule).mockReturnValue(device);
    expect(isPhysicalDevice()).toBe(expected);
  });
});
