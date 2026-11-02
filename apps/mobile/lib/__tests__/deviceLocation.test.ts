import * as Location from "expo-location";

import { getDeviceLocationLabel, requestDeviceGeo } from "@/lib/deviceLocation";

jest.mock("@/lib/expoRuntime", () => ({ canUseDeviceLocation: () => true }));
jest.mock("expo-location", () => ({
  Accuracy: { Balanced: 3 },
  getForegroundPermissionsAsync: jest.fn(),
  requestForegroundPermissionsAsync: jest.fn(),
  getLastKnownPositionAsync: jest.fn(),
  getCurrentPositionAsync: jest.fn(),
  reverseGeocodeAsync: jest.fn(),
}));

const mocked = Location as unknown as Record<
  | "getForegroundPermissionsAsync"
  | "requestForegroundPermissionsAsync"
  | "getLastKnownPositionAsync"
  | "getCurrentPositionAsync"
  | "reverseGeocodeAsync",
  jest.Mock
>;
const at = (latitude: number, longitude: number, speed: number | null = null) => ({
  coords: { latitude, longitude, speed },
});
const oakland = [{ city: "Oakland", region: "CA", country: "United States" }];
const never = () => new Promise<never>(() => undefined);

describe("requestDeviceGeo", () => {
  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    mocked.getForegroundPermissionsAsync.mockResolvedValue({ status: "granted", canAskAgain: true });
    mocked.reverseGeocodeAsync.mockResolvedValue(oakland);
  });
  afterEach(() => {
    jest.useRealTimers();
  });

  it("answers a chat send from a recent fix without asking for a new one", async () => {
    mocked.getLastKnownPositionAsync.mockResolvedValue(at(37.8, -122.27));
    await expect(requestDeviceGeo({ quick: true })).resolves.toEqual({
      status: "granted",
      geo: { label: "Oakland, CA, United States", latitude: 37.8, longitude: -122.27 },
    });
    expect(mocked.getLastKnownPositionAsync).toHaveBeenCalledWith({ maxAge: 120_000, requiredAccuracy: 500 });
    expect(mocked.getCurrentPositionAsync).not.toHaveBeenCalled();
  });

  it.each([
    [1.4, false],
    [-1, false],
    [2.5, true],
    [25, true],
  ])("reuses a recent fix taken at %p m/s unless it was on the move: new fix %p", async (speed, fresh) => {
    mocked.getLastKnownPositionAsync.mockResolvedValue(at(37.8, -122.27, speed));
    mocked.getCurrentPositionAsync.mockResolvedValue(at(37.9, -122.3));
    const result = await requestDeviceGeo({ quick: true });
    expect(result).toMatchObject({ status: "granted", geo: { latitude: fresh ? 37.9 : 37.8 } });
    expect(mocked.getCurrentPositionAsync).toHaveBeenCalledTimes(fresh ? 1 : 0);
  });

  it("asks for a new fix when there is no recent one", async () => {
    mocked.getLastKnownPositionAsync.mockResolvedValue(null);
    mocked.getCurrentPositionAsync.mockResolvedValue(at(37.8, -122.27));
    const result = await requestDeviceGeo({ quick: true });
    expect(result).toMatchObject({ status: "granted", geo: { latitude: 37.8 } });
    expect(mocked.getCurrentPositionAsync).toHaveBeenCalledWith({ accuracy: 3 });
  });

  it("goes without a fix when none comes within five seconds", async () => {
    mocked.getLastKnownPositionAsync.mockRejectedValue(new Error("no provider"));
    mocked.getCurrentPositionAsync.mockReturnValue(never());
    const reading = requestDeviceGeo({ quick: true });
    await jest.advanceTimersByTimeAsync(4_999);
    let settled = false;
    void reading.then(() => { settled = true; });
    await Promise.resolve();
    expect(settled).toBe(false);
    await jest.advanceTimersByTimeAsync(1);
    await expect(reading).resolves.toEqual({ status: "no_fix" });
  });

  it("sends the coordinates alone when the place name is slow, and hands the name over when it comes", async () => {
    mocked.getLastKnownPositionAsync.mockResolvedValue(at(37.8, -122.27));
    let named!: (places: typeof oakland) => void;
    mocked.reverseGeocodeAsync.mockReturnValue(new Promise((resolve) => { named = resolve; }));
    const reading = requestDeviceGeo({ quick: true });
    await jest.advanceTimersByTimeAsync(1_500);
    const result = await reading;
    expect(result).toEqual({
      status: "granted",
      geo: { label: null, latitude: 37.8, longitude: -122.27, lateLabel: expect.any(Promise) },
    });
    named(oakland);
    await expect(result.status === "granted" ? result.geo.lateLabel : null).resolves.toBe("Oakland, CA, United States");
  });

  it("waits for a new fix and its place name for Settings", async () => {
    mocked.getCurrentPositionAsync.mockResolvedValue(at(37.8, -122.27));
    await expect(getDeviceLocationLabel()).resolves.toBe("Oakland, CA, United States");
    expect(mocked.getLastKnownPositionAsync).not.toHaveBeenCalled();
  });

  it("still reports a refused permission without reading a position", async () => {
    mocked.getForegroundPermissionsAsync.mockResolvedValue({ status: "denied", canAskAgain: false });
    await expect(requestDeviceGeo({ quick: true })).resolves.toEqual({ status: "blocked" });
    expect(mocked.getLastKnownPositionAsync).not.toHaveBeenCalled();
  });
});
