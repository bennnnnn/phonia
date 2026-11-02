import React from "react";
import { AppState } from "react-native";
import NetInfo from "@react-native-community/netinfo";
import { act, render } from "@testing-library/react-native";

import { retryDelayMs, useNetworkStatus } from "@/hooks/useNetworkStatus";
import { reportConnectionAnswered, reportConnectionFailure } from "@/lib/api/connectionFailures";
import { resolveConnectivity } from "@/lib/networkProbe";
import { reportDisconnected, reportReconnected } from "@/lib/reconnectRefresh";

jest.mock("@react-native-community/netinfo", () => ({
  __esModule: true,
  default: {
    fetch: jest.fn(async () => ({ isConnected: false, isInternetReachable: false })),
    addEventListener: jest.fn(() => () => {}),
  },
}));
jest.mock("@/lib/networkProbe", () => ({
  configureNetInfo: jest.fn(),
  resolveConnectivity: jest.fn(),
}));
jest.mock("@/lib/reconnectRefresh", () => {
  let lostAt = 0;
  return {
    reportReconnected: jest.fn(),
    reportDisconnected: jest.fn(() => { lostAt = Date.now(); }),
    connectionLostAt: () => lostAt,
  };
});

const probe = resolveConnectivity as jest.MockedFunction<typeof resolveConnectivity>;
let status: ReturnType<typeof useNetworkStatus>["status"];
let values: ReturnType<typeof useNetworkStatus>[] = [];
function Probe() {
  const value = useNetworkStatus();
  React.useLayoutEffect(() => {
    status = value.status;
    values.push(value);
  });
  return null;
}

async function flush() {
  for (let i = 0; i < 10; i += 1) await Promise.resolve();
}

/** Let each probe settle before the next tick, as real time would. */
async function elapse(ms: number) {
  await act(async () => {
    for (let at = 0; at < ms; at += 500) {
      jest.advanceTimersByTime(500);
      await flush();
    }
  });
}

describe("useNetworkStatus offline polling", () => {
  const addListener = AppState.addEventListener as unknown as jest.Mock;
  const defaultAddListener = addListener.getMockImplementation();
  const handlers = new Set<(state: string) => void>();
  const setAppState = async (state: string) => {
    await act(async () => {
      for (const handler of [...handlers]) handler(state);
      await flush();
    });
  };

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    jest.spyOn(Math, "random").mockReturnValue(0.5); // no jitter: delays are exact
    handlers.clear();
    (NetInfo.fetch as jest.Mock).mockResolvedValue({ isConnected: false, isInternetReachable: false });
    probe.mockResolvedValue("no_internet");
    addListener.mockImplementation((event: string, handler: (state: string) => void) => {
      if (event !== "change") return { remove: jest.fn() };
      handlers.add(handler);
      return { remove: () => handlers.delete(handler) };
    });
  });
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    jest.restoreAllMocks();
    addListener.mockImplementation(defaultAddListener);
  });

  it("stops probing while the app is in the background and resumes on return", async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    expect(status).toBe("no_internet");
    const opened = probe.mock.calls.length;
    await elapse(6_000);
    expect(probe.mock.calls.length).toBe(opened + 2); // at 1.5 s and 4.5 s

    // Nobody sees the banner in the background, so the loop must not run there.
    await setAppState("background");
    const atBackground = probe.mock.calls.length;
    await elapse(60_000);
    expect(probe.mock.calls.length).toBe(atBackground);

    probe.mockResolvedValue("online");
    await setAppState("active");
    expect(probe.mock.calls.length).toBeGreaterThan(atBackground);
    expect(status).toBe("online");
  });
});

describe("useNetworkStatus degraded backoff", () => {
  const listen = NetInfo.addEventListener as unknown as jest.Mock;
  const connected = { isConnected: true, isInternetReachable: true };
  let onNetInfo: ((state: object) => void) | null = null;

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    jest.spyOn(Math, "random").mockReturnValue(0.5);
    probe.mockResolvedValue("api_unreachable");
    // NetInfo calls a new listener at once with the current state, as the library does.
    (NetInfo.fetch as jest.Mock).mockResolvedValue(connected);
    listen.mockImplementation((handler: (state: object) => void) => {
      onNetInfo = handler;
      handler(connected);
      return () => {
        onNetInfo = null;
      };
    });
  });
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    jest.restoreAllMocks();
    listen.mockImplementation(() => () => {});
  });

  it("probes once at start although NetInfo reports twice", async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    expect(probe).toHaveBeenCalledTimes(1);
  });

  it("backs off to a minute: ten minutes of an unreachable API cost at most 15 probes", async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    await elapse(10 * 60_000);
    expect(status).toBe("api_unreachable");
    // A fixed 1.5 s loop made about 400 here, each to /health and to Google.
    expect(probe.mock.calls.length).toBeLessThanOrEqual(15);
  });

  it("starts the backoff over when the link changes", async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    await elapse(5 * 60_000); // deep in the one-minute waits
    const before = probe.mock.calls.length;
    await act(async () => {
      onNetInfo?.({ ...connected, type: "cellular" });
      await flush();
    });
    await elapse(2_000);
    // The event's own probe, then the first 1.5 s retry.
    expect(probe.mock.calls.length).toBe(before + 2);
  });
});

describe("useNetworkStatus launch probe", () => {
  const addListener = AppState.addEventListener as unknown as jest.Mock;
  const defaultAddListener = addListener.getMockImplementation();
  const netInfoAdd = NetInfo.addEventListener as unknown as jest.Mock;
  const appHandlers = new Set<(state: string) => void>();
  let netInfoListener: ((state: object) => void) | null = null;
  const wifi = { type: "wifi", isConnected: true, isInternetReachable: null };

  const emit = async (state: object) => {
    await act(async () => {
      netInfoListener?.(state);
      await flush();
    });
  };

  beforeEach(() => {
    jest.clearAllMocks();
    values = [];
    appHandlers.clear();
    probe.mockResolvedValue("online");
    (NetInfo.fetch as jest.Mock).mockResolvedValue(wifi);
    // NetInfo hands every new subscriber the current report.
    netInfoAdd.mockImplementation((listener: (state: object) => void) => {
      netInfoListener = listener;
      void Promise.resolve().then(() => listener(wifi));
      return () => { netInfoListener = null; };
    });
    addListener.mockImplementation((event: string, handler: (state: string) => void) => {
      if (event !== "change") return { remove: jest.fn() };
      appHandlers.add(handler);
      return { remove: () => appHandlers.delete(handler) };
    });
  });
  afterEach(() => {
    addListener.mockImplementation(defaultAddListener);
    netInfoAdd.mockImplementation(() => () => {});
  });

  it("probes once at launch although NetInfo repeats its report", async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    expect(probe).toHaveBeenCalledTimes(1);

    // The reachability check settling, and the echo of the probe's own refresh.
    await emit({ ...wifi, isInternetReachable: true });
    await emit({ ...wifi, isInternetReachable: true });
    expect(probe).toHaveBeenCalledTimes(1);

    // A new link, or the OS saying the internet is gone, is worth a probe.
    await emit({ type: "cellular", isConnected: true, isInternetReachable: true });
    expect(probe).toHaveBeenCalledTimes(2);
    await emit({ type: "cellular", isConnected: true, isInternetReachable: false });
    expect(probe).toHaveBeenCalledTimes(3);
  });

  it("lets a probe already running answer for a return to the app", async () => {
    let answer!: (status: "online") => void;
    probe.mockImplementationOnce(() => new Promise((resolve) => { answer = resolve; }));
    await render(<Probe />);
    await act(async () => { await flush(); });
    expect(probe).toHaveBeenCalledTimes(1);

    const leaveAndReturn = async () => {
      await act(async () => {
        for (const state of ["background", "active"]) {
          for (const handler of [...appHandlers]) handler(state);
        }
        await flush();
      });
    };
    await leaveAndReturn();
    expect(probe).toHaveBeenCalledTimes(1);

    await act(async () => { answer("online"); await flush(); });
    await leaveAndReturn();
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it("does not probe for an iOS inactive blip, which never left the screen", async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    const opened = probe.mock.calls.length;
    await act(async () => {
      for (const state of ["inactive", "active"]) {
        for (const handler of [...appHandlers]) handler(state);
      }
      await flush();
    });
    expect(probe).toHaveBeenCalledTimes(opened);
  });

  it("keeps \"No internet\" on a link that is up with nothing behind it", async () => {
    // A captive portal, or Wi-Fi with its upstream down. Each probe's own
    // NetInfo.refresh() repeats the report to every subscriber.
    const wifiNoInternet = { type: "wifi", isConnected: true, isInternetReachable: false };
    (NetInfo.fetch as jest.Mock).mockResolvedValue(wifiNoInternet);
    netInfoAdd.mockImplementation((listener: (state: object) => void) => {
      netInfoListener = listener;
      void Promise.resolve().then(() => listener(wifiNoInternet));
      return () => { netInfoListener = null; };
    });
    probe.mockImplementation(async () => {
      netInfoListener?.(wifiNoInternet);
      return "no_internet";
    });
    jest.useFakeTimers();
    try {
      await render(<Probe />);
      for (let tick = 0; tick < 6; tick += 1) {
        await act(async () => {
          jest.advanceTimersByTime(1_000);
          await flush();
        });
        expect(status).toBe("no_internet");
      }
    } finally {
      jest.useRealTimers();
    }
  });

  it("drops the banner as soon as the link comes back up, before the probe answers", async () => {
    const airplane = { type: "none", isConnected: false, isInternetReachable: false };
    (NetInfo.fetch as jest.Mock).mockResolvedValue(airplane);
    netInfoAdd.mockImplementation((listener: (state: object) => void) => {
      netInfoListener = listener;
      return () => { netInfoListener = null; };
    });
    probe.mockResolvedValue("no_internet");
    await render(<Probe />);
    await act(async () => { await flush(); });
    expect(status).toBe("no_internet");

    probe.mockImplementation(() => new Promise(() => {}));
    await emit({ type: "wifi", isConnected: true, isInternetReachable: null });
    expect(status).toBe("online");
  });

  it("probes a switch straight from one Wi-Fi network to another", async () => {
    const home = { ...wifi, details: { ipAddress: "192.168.1.20", isConnectionExpensive: false } };
    (NetInfo.fetch as jest.Mock).mockResolvedValue(home);
    netInfoAdd.mockImplementation((listener: (state: object) => void) => {
      netInfoListener = listener;
      return () => { netInfoListener = null; };
    });
    await render(<Probe />);
    await act(async () => { await flush(); });
    expect(probe).toHaveBeenCalledTimes(1);

    await emit(home);
    expect(probe).toHaveBeenCalledTimes(1);
    await emit({ ...wifi, details: { ipAddress: "10.0.0.7", isConnectionExpensive: false } });
    expect(probe).toHaveBeenCalledTimes(2);
  });

  it("keeps the same value when only the app's background state changes", async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    const before = values[values.length - 1];
    await act(async () => {
      for (const handler of [...appHandlers]) handler("background");
      await flush();
    });
    expect(values[values.length - 1]).toBe(before);
    expect(before).toEqual({ isOffline: false, status: "online" });
  });
});

describe("useNetworkStatus reconnect signal", () => {
  const addListener = AppState.addEventListener as unknown as jest.Mock;
  const defaultAddListener = addListener.getMockImplementation();
  const netInfoAdd = NetInfo.addEventListener as unknown as jest.Mock;
  const appHandlers = new Set<(state: string) => void>();
  let netInfoListener: ((state: object) => void) | null = null;
  const airplane = { type: "none", isConnected: false, isInternetReachable: false };
  const setAppState = async (state: string) => {
    await act(async () => {
      for (const handler of [...appHandlers]) handler(state);
      await flush();
    });
  };

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    jest.spyOn(Math, "random").mockReturnValue(0.5);
    appHandlers.clear();
    (NetInfo.fetch as jest.Mock).mockResolvedValue(airplane);
    netInfoAdd.mockImplementation((listener: (state: object) => void) => {
      netInfoListener = listener;
      return () => { netInfoListener = null; };
    });
    addListener.mockImplementation((event: string, handler: (state: string) => void) => {
      if (event !== "change") return { remove: jest.fn() };
      appHandlers.add(handler);
      return { remove: () => appHandlers.delete(handler) };
    });
    probe.mockResolvedValue("api_unreachable");
  });
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    jest.restoreAllMocks();
    addListener.mockImplementation(defaultAddListener);
    netInfoAdd.mockImplementation(() => () => {});
  });

  it("reports the API back once, when the check passes after failing", async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    expect(status).toBe("api_unreachable");
    expect(reportDisconnected).toHaveBeenCalledTimes(1);
    expect(reportReconnected).not.toHaveBeenCalled();

    await elapse(5_000);
    probe.mockResolvedValue("online");
    await elapse(10_000);
    expect(status).toBe("online");
    expect(reportReconnected).toHaveBeenCalledTimes(1);

    // Online stays online: link reports and returns are no reconnect.
    await act(async () => {
      netInfoListener?.({ type: "wifi", isConnected: true, isInternetReachable: true });
      await flush();
    });
    await setAppState("background");
    await setAppState("active");
    await elapse(60_000);
    expect(reportReconnected).toHaveBeenCalledTimes(1);
  });

  it("reports nothing for an outage that ends while the app is in the background", async () => {
    probe.mockResolvedValue("no_internet");
    await render(<Probe />);
    await act(async () => { await flush(); });
    expect(status).toBe("no_internet");

    await setAppState("background");
    probe.mockResolvedValue("online");
    await act(async () => {
      netInfoListener?.({ type: "wifi", isConnected: true, isInternetReachable: true });
      await flush();
    });
    expect(status).toBe("online");
    await setAppState("active");
    await elapse(60_000);
    expect(reportReconnected).not.toHaveBeenCalled();
  });

  it("reports an outage the return finds over, with the app on screen", async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    await setAppState("background");
    probe.mockResolvedValue("online");
    await setAppState("active");
    expect(status).toBe("online");
    expect(reportReconnected).toHaveBeenCalledTimes(1);
  });
});

describe("useNetworkStatus failed requests", () => {
  const addListener = AppState.addEventListener as unknown as jest.Mock;
  const defaultAddListener = addListener.getMockImplementation();
  const netInfoAdd = NetInfo.addEventListener as unknown as jest.Mock;
  const appHandlers = new Set<(state: string) => void>();
  const wifi = { type: "wifi", isConnected: true, isInternetReachable: true };
  const setAppState = async (state: string) => {
    await act(async () => {
      for (const handler of [...appHandlers]) handler(state);
      await flush();
    });
  };
  /** `count` requests that found no API, together. */
  const fail = async (count = 1) => {
    await act(async () => {
      for (let i = 0; i < count; i += 1) reportConnectionFailure();
      await flush();
    });
  };
  const launch = async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
  };

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    jest.spyOn(Math, "random").mockReturnValue(0.5); // the loop's first wait is 1.5 s
    appHandlers.clear();
    (NetInfo.fetch as jest.Mock).mockResolvedValue(wifi);
    netInfoAdd.mockImplementation(() => () => {});
    addListener.mockImplementation((event: string, handler: (state: string) => void) => {
      if (event !== "change") return { remove: jest.fn() };
      appHandlers.add(handler);
      return { remove: () => appHandlers.delete(handler) };
    });
    probe.mockResolvedValue("online");
  });
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    jest.restoreAllMocks();
    addListener.mockImplementation(defaultAddListener);
    (AppState as { currentState: unknown }).currentState = "active";
  });

  it("checks once for a burst of failures, the loop's first wait later, and shows the banner", async () => {
    await launch();
    expect(probe).toHaveBeenCalledTimes(1); // the launch's check
    probe.mockResolvedValue("api_unreachable");
    await fail(25);
    await elapse(1_000);
    await fail(25);
    expect(probe).toHaveBeenCalledTimes(1);
    await elapse(500);
    expect(probe).toHaveBeenCalledTimes(2);
    expect(status).toBe("api_unreachable");

    // The banner up, the loop checks (1.5 s, then 3 s later); failures add nothing.
    for (let at = 0; at < 6_000; at += 500) {
      await fail(4);
      await elapse(500);
    }
    expect(probe).toHaveBeenCalledTimes(4);
  });

  it("holds the next check off for a minute after one finds the API answering", async () => {
    await launch();
    await fail();
    await elapse(1_500);
    expect(probe).toHaveBeenCalledTimes(2);
    expect(status).toBe("online");

    // Everything the check reads answers (one route failing on its own): its reads keep
    // failing, one check a minute.
    for (let at = 0; at < 58_000; at += 2_000) {
      await fail();
      await elapse(2_000);
    }
    expect(probe).toHaveBeenCalledTimes(2);
    await elapse(2_000);
    await fail();
    await elapse(1_500);
    expect(probe).toHaveBeenCalledTimes(3);
  });

  it("checks at once for the next outage after the banner clears", async () => {
    await launch();
    probe.mockResolvedValue("api_unreachable");
    await fail();
    await elapse(1_500);
    expect(status).toBe("api_unreachable");
    probe.mockResolvedValue("online");
    await elapse(1_500); // the loop's first retry finds the API back
    expect(status).toBe("online");
    const checks = probe.mock.calls.length;

    probe.mockResolvedValue("api_unreachable");
    await fail();
    await elapse(1_500);
    expect(probe).toHaveBeenCalledTimes(checks + 1);
    expect(status).toBe("api_unreachable");
  });

  it("starts nothing in the background, and calls off a check still waiting", async () => {
    await launch();
    await fail();
    await elapse(500);
    await setAppState("background");
    await elapse(5_000);
    await fail(10);
    await elapse(5_000);
    expect(probe).toHaveBeenCalledTimes(1);

    await setAppState("active");
    expect(probe).toHaveBeenCalledTimes(2); // the return's own check
    await fail();
    await elapse(1_500);
    expect(probe).toHaveBeenCalledTimes(3);
  });

  it("starts nothing for a launch in the background until the app comes forward", async () => {
    (AppState as { currentState: unknown }).currentState = "background";
    await launch();
    const launched = probe.mock.calls.length;
    await fail(10);
    await elapse(5_000);
    expect(probe).toHaveBeenCalledTimes(launched);

    await setAppState("active");
    await fail();
    await elapse(1_500);
    expect(probe).toHaveBeenCalledTimes(launched + 2); // the return's check, then the failure's
  });
});

describe("useNetworkStatus answered requests", () => {
  const wifi = { type: "wifi", isConnected: true, isInternetReachable: true };
  const addListener = AppState.addEventListener as unknown as jest.Mock;
  const defaultAddListener = addListener.getMockImplementation();
  const appHandlers = new Set<(state: string) => void>();
  const setAppState = async (state: string) => {
    await act(async () => {
      for (const handler of [...appHandlers]) handler(state);
      await flush();
    });
  };
  /** Our API answered `count` requests sent at `sentAt`. */
  const answer = async (sentAt: number, count = 1) => {
    await act(async () => {
      for (let i = 0; i < count; i += 1) reportConnectionAnswered(sentAt);
      await flush();
    });
  };
  /** Launch with the API out: the banner shows. */
  const launchIntoOutage = async () => {
    await render(<Probe />);
    await act(async () => { await flush(); });
    expect(status).toBe("api_unreachable");
  };

  beforeEach(() => {
    jest.useFakeTimers();
    jest.clearAllMocks();
    jest.spyOn(Math, "random").mockReturnValue(0.5);
    appHandlers.clear();
    (NetInfo.fetch as jest.Mock).mockResolvedValue(wifi);
    addListener.mockImplementation((event: string, handler: (state: string) => void) => {
      if (event !== "change") return { remove: jest.fn() };
      appHandlers.add(handler);
      return { remove: () => appHandlers.delete(handler) };
    });
    probe.mockResolvedValue("api_unreachable");
  });
  afterEach(() => {
    jest.clearAllTimers();
    jest.useRealTimers();
    jest.restoreAllMocks();
    addListener.mockImplementation(defaultAddListener);
    (AppState as { currentState: unknown }).currentState = "active";
  });

  it("clears the banner at the first answer to a request sent since, with one reconnect", async () => {
    await launchIntoOutage();
    await elapse(1_000);
    const checks = probe.mock.calls.length;
    await answer(Date.now(), 30);
    expect(status).toBe("online");
    expect(reportReconnected).toHaveBeenCalledTimes(1);
    // Nothing more is checked: the loop stopped with the banner.
    await elapse(60_000);
    expect(probe).toHaveBeenCalledTimes(checks);
    expect(reportReconnected).toHaveBeenCalledTimes(1);
  });

  it("keeps the banner for an answer to a request sent before the outage was seen", async () => {
    probe.mockResolvedValue("online");
    await render(<Probe />);
    await act(async () => { await flush(); });
    const sentBefore = Date.now();
    await elapse(500);
    probe.mockResolvedValue("api_unreachable");
    await act(async () => {
      reportConnectionFailure();
      await flush();
    });
    await elapse(1_500);
    expect(status).toBe("api_unreachable");
    await answer(sentBefore);
    expect(status).toBe("api_unreachable");
    expect(reportReconnected).not.toHaveBeenCalled();
  });

  it("lets no check already on its way bring the banner back", async () => {
    await launchIntoOutage();
    let settle: (next: "api_unreachable") => void = () => {};
    probe.mockImplementation(() => new Promise((resolve) => { settle = resolve; }));
    await elapse(1_500); // the loop's check goes out, and waits
    await answer(Date.now());
    expect(status).toBe("online");

    // A failure soon after gets a check of its own, not the answer of the one still out.
    probe.mockResolvedValue("online");
    await act(async () => {
      reportConnectionFailure();
      await flush();
    });
    await elapse(1_500);
    await act(async () => {
      settle("api_unreachable");
      await flush();
    });
    expect(status).toBe("online");
  });

  it("clears nothing in the background; the return checks as before", async () => {
    await launchIntoOutage();
    await setAppState("background");
    await answer(Date.now());
    expect(status).toBe("api_unreachable");
    probe.mockResolvedValue("online");
    await setAppState("active");
    expect(status).toBe("online");
    expect(reportReconnected).toHaveBeenCalledTimes(1);
  });
});

describe("retryDelayMs", () => {
  it("doubles from 1.5 s to a one-minute cap", () => {
    const exact = () => 0.5;
    expect([0, 1, 2, 3, 4, 5, 6, 10].map((n) => retryDelayMs(n, exact))).toEqual([
      1_500, 3_000, 6_000, 12_000, 24_000, 48_000, 60_000, 60_000,
    ]);
  });

  it("spreads each wait by a fifth either way", () => {
    expect(retryDelayMs(6, () => 0)).toBe(48_000);
    expect(retryDelayMs(6, () => 1)).toBe(72_000);
  });
});
