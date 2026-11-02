import { isNetworkOffline, isNetworkPathChange } from "@/lib/networkStatus";

describe("networkStatus", () => {
  it("is offline when not connected", () => {
    expect(isNetworkOffline({ isConnected: false, isInternetReachable: false } as never)).toBe(
      true,
    );
  });

  it("is online when connected even if reachability is stuck false", () => {
    expect(isNetworkOffline({ isConnected: true, isInternetReachable: false } as never)).toBe(
      false,
    );
  });

  it("is online when connected and reachability is unknown", () => {
    expect(isNetworkOffline({ isConnected: true, isInternetReachable: null } as never)).toBe(
      false,
    );
  });

  it("is online when connected and internet is reachable", () => {
    expect(isNetworkOffline({ isConnected: true, isInternetReachable: true } as never)).toBe(
      false,
    );
  });

  it("is offline when link state unknown and reachability is false", () => {
    expect(isNetworkOffline({ isConnected: null, isInternetReachable: false } as never)).toBe(
      true,
    );
  });
});

describe("isNetworkPathChange", () => {
  const wifi = (ipAddress: string | null = "192.168.1.5") =>
    ({ type: "wifi", isConnected: true, isInternetReachable: true, details: { ipAddress } }) as never;
  const cellular = { type: "cellular", isConnected: true, isInternetReachable: true, details: {} } as never;
  const offline = { type: "none", isConnected: false, isInternetReachable: false, details: null } as never;
  const unknown = { type: "unknown", isConnected: null, isInternetReachable: null, details: null } as never;

  it.each([
    ["Wi-Fi to cellular", wifi(), cellular],
    ["cellular to Wi-Fi", cellular, wifi()],
    ["offline to online", offline, wifi()],
    ["online to offline", cellular, offline],
    ["one Wi-Fi to another", wifi("192.168.1.5"), wifi("10.0.0.7")],
  ])("is a change: %s", (_label, previous, next) => {
    expect(isNetworkPathChange(previous, next)).toBe(true);
  });

  it.each([
    ["the first report", null, wifi()],
    ["the same Wi-Fi", wifi(), wifi()],
    ["a Wi-Fi report without its address", wifi(), wifi(null)],
    ["the first link after unknown", unknown, wifi()],
  ])("is not a change: %s", (_label, previous, next) => {
    expect(isNetworkPathChange(previous, next)).toBe(false);
  });
});
