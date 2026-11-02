import React from "react";
import { Text } from "react-native";
import { act, render } from "@testing-library/react-native";

import { ActionFeedbackContext, type ActionFeedbackApi } from "@/contexts/actionFeedbackCore";
import { useBootstrapSync } from "@/hooks/useBootstrapSync";
import { api, type User } from "@/lib/api";
import { registerPlanChangeListener } from "@/features/billing/model/purchases";
import { attachPushForegroundSync } from "@/features/notifications/model/pushNotifications";
import { onAppEvent } from "@/lib/appEvents";
import { ApiRequestError } from "@/lib/api/errorBody";

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 0 }));
jest.mock("@/lib/api", () => ({ api: { updateMe: jest.fn(), syncSubscription: jest.fn() } }));
let mockDeviceZone = "America/Los_Angeles";
jest.mock("@/lib/deviceTimezone", () => ({ getDeviceTimezone: () => mockDeviceZone }));
// The OS's clock-change event (expo-localization) and the app's returns to the foreground.
const mockClockListeners = new Set<() => void>();
jest.mock("@/lib/datetime/phoneClock", () => ({
  onPhoneClockChange: (listener: () => void) => {
    mockClockListeners.add(listener);
    return () => { mockClockListeners.delete(listener); };
  },
}));
const mockAppStateListeners = new Set<(state: string, returned: boolean) => void>();
jest.mock("@/lib/foregroundRefresh", () => ({
  onAppStateChange: (listener: (state: string, returned: boolean) => void) => {
    mockAppStateListeners.add(listener);
    return () => { mockAppStateListeners.delete(listener); };
  },
}));
jest.mock("@/features/notifications/model/pushNotifications", () => ({ attachPushForegroundSync: jest.fn() }));
jest.mock("@/features/billing/model/purchases", () => ({
  configurePurchases: jest.fn(), isPurchasesConfigured: () => true,
  registerPlanChangeListener: jest.fn(),
}));

const userA = { id: "a", timezone: "UTC" } as User;
const userB = { id: "b", timezone: "America/Los_Angeles" } as User;
const setUser = jest.fn();

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((yes) => { resolve = yes; });
  return { promise, resolve };
}

function Probe({ user, token }: { user: User | null; token: string | null }) {
  useBootstrapSync({ user, token, setUser });
  return <Text>{user?.id ?? "out"}</Text>;
}

beforeEach(() => {
  jest.clearAllMocks();
  mockDeviceZone = "America/Los_Angeles";
  (api.updateMe as jest.Mock).mockResolvedValue(userA);
  (registerPlanChangeListener as jest.Mock).mockResolvedValue(jest.fn());
});

it("does not restore a user when timezone sync returns after signout", async () => {
  const update = deferred<User>();
  (api.updateMe as jest.Mock).mockReturnValue(update.promise);
  const rendered = await render(<Probe user={userA} token="a" />);
  await rendered.rerender(<Probe user={null} token={null} />);
  await act(async () => { update.resolve({ ...userA, timezone: "America/Los_Angeles" }); });
  expect(setUser).not.toHaveBeenCalled();
});

it("ignores the old account's subscription response and detached listener", async () => {
  const subscription = deferred<User>();
  (api.syncSubscription as jest.Mock).mockReturnValue(subscription.promise);
  const rendered = await render(<Probe user={{ ...userA, timezone: userB.timezone }} token="a" />);
  const previousListener = (registerPlanChangeListener as jest.Mock).mock.calls[0][0];
  await act(async () => { previousListener(true); });
  await rendered.rerender(<Probe user={userB} token="b" />);
  await act(async () => { subscription.resolve({ ...userA, plan: "pro" }); previousListener(false); });
  expect(setUser).not.toHaveBeenCalled();
  expect(api.syncSubscription).toHaveBeenCalledTimes(1);
});

it("a store plan change brings the plan's features with it", async () => {
  (api.syncSubscription as jest.Mock).mockResolvedValue({ ...userA, plan: "pro", features: ["live_talk"] });
  await render(<Probe user={{ ...userA, timezone: userB.timezone }} token="a" />);
  const listener = (registerPlanChangeListener as jest.Mock).mock.calls[0][0];
  await act(async () => { listener(true); });
  const applyUpdate = setUser.mock.calls[0][0];
  expect(applyUpdate({ ...userA, name: "Kept", features: [] })).toEqual({
    ...userA, name: "Kept", plan: "pro", features: ["live_talk"],
  });
});

it("announces the synced time zone, which moves every reminder's quiet hours", async () => {
  const announced = jest.fn();
  const stop = onAppEvent("userUpdated", announced);
  (api.updateMe as jest.Mock).mockResolvedValue({ ...userA, timezone: userB.timezone });
  await render(<Probe user={userA} token="a" />);
  expect(announced).toHaveBeenCalledWith({ fields: ["timezone"] });
  announced.mockClear();
  await render(<Probe user={userB} token="b" />);
  expect(announced).not.toHaveBeenCalled();
  stop();
});

it("merges only the synced timezone into the current account", async () => {
  (api.updateMe as jest.Mock).mockResolvedValue({ ...userA, name: "Old name", timezone: userB.timezone });
  await render(<Probe user={userA} token="a" />);
  const applyUpdate = setUser.mock.calls[0][0];
  expect(applyUpdate({ ...userA, name: "New name" })).toEqual({ ...userA, name: "New name", timezone: userB.timezone });
  expect(applyUpdate(userB)).toEqual(userB);
  expect(applyUpdate(null)).toBeNull();
});

it("keeps one RevenueCat setup across an access-token refresh", async () => {
  const { configurePurchases } = jest.requireMock("@/features/billing/model/purchases") as { configurePurchases: jest.Mock };
  const rendered = await render(<Probe user={{ ...userA, timezone: userB.timezone }} token="a" />);
  await act(async () => {});
  await rendered.rerender(<Probe user={{ ...userA, timezone: userB.timezone }} token="a-refreshed" />);
  await act(async () => {});
  expect(configurePurchases).toHaveBeenCalledTimes(1);
  expect(registerPlanChangeListener).toHaveBeenCalledTimes(1);
});

it("hands the push sync the app's toasts, so a push token failure is not silent", async () => {
  const feedback: ActionFeedbackApi = {
    show: jest.fn(), success: jest.fn(), info: jest.fn(), warning: jest.fn(), error: jest.fn(), dismiss: jest.fn(),
  };
  await render(
    <ActionFeedbackContext.Provider value={feedback}>
      <Probe user={{ ...userA, push_notifications_enabled: true }} token="a" />
    </ActionFeedbackContext.Provider>,
  );
  await act(async () => {});
  expect(attachPushForegroundSync).toHaveBeenCalledWith("a", true, expect.any(Function), "a", feedback);
});

describe("zone report", () => {
  const atHome = { ...userA, timezone: "America/Los_Angeles" } as User;
  const zonePatches = () => (api.updateMe as jest.Mock).mock.calls.filter(([, body]) => "timezone" in body);
  const clockChanged = () => act(async () => { for (const listener of [...mockClockListeners]) listener(); });
  const returnToForeground = (returned = true) =>
    act(async () => { for (const listener of [...mockAppStateListeners]) listener("active", returned); });
  const answer = (zone: string) => ({ ...atHome, timezone: zone });

  it("sends a new zone the moment the OS reports it, once", async () => {
    const announced = jest.fn();
    const stop = onAppEvent("userUpdated", announced);
    (api.updateMe as jest.Mock).mockResolvedValue(answer("Asia/Kathmandu"));
    await render(<Probe user={atHome} token="a" />);
    await clockChanged();
    expect(zonePatches()).toEqual([]);

    mockDeviceZone = "Asia/Kathmandu";
    await clockChanged();
    await clockChanged();
    expect(zonePatches()).toEqual([["a", { timezone: "Asia/Kathmandu" }]]);
    expect(announced.mock.calls).toEqual([[{ fields: ["timezone"] }]]);
    stop();
  });

  it("a return to the foreground sends nothing when the zone is the server's, one after a flight", async () => {
    (api.updateMe as jest.Mock).mockResolvedValue(answer("Pacific/Kiritimati"));
    await render(<Probe user={atHome} token="a" />);
    await returnToForeground();
    expect(zonePatches()).toEqual([]);

    mockDeviceZone = "Pacific/Kiritimati";
    // iOS's inactive and back (Control Centre) is not a return.
    await returnToForeground(false);
    expect(zonePatches()).toEqual([]);
    await returnToForeground();
    await returnToForeground();
    expect(zonePatches()).toEqual([["a", { timezone: "Pacific/Kiritimati" }]]);
  });

  it("sends one report for the events that come while it is in flight", async () => {
    const update = deferred<User>();
    (api.updateMe as jest.Mock).mockReturnValue(update.promise);
    await render(<Probe user={atHome} token="a" />);
    mockDeviceZone = "Asia/Kathmandu";
    await clockChanged();
    await returnToForeground();
    await clockChanged();
    expect(zonePatches()).toHaveLength(1);
    await act(async () => { update.resolve(answer("Asia/Kathmandu")); });
    expect(zonePatches()).toHaveLength(1);
  });

  it("sends the newer zone once the report in flight lands", async () => {
    const first = deferred<User>();
    (api.updateMe as jest.Mock).mockReturnValueOnce(first.promise).mockResolvedValue(answer("Pacific/Kiritimati"));
    await render(<Probe user={atHome} token="a" />);
    mockDeviceZone = "Asia/Kathmandu";
    await clockChanged();
    mockDeviceZone = "Pacific/Kiritimati";
    await clockChanged();
    await act(async () => { first.resolve(answer("Asia/Kathmandu")); });
    expect(zonePatches().map(([, body]) => body.timezone)).toEqual(["Asia/Kathmandu", "Pacific/Kiritimati"]);
  });

  it("does not send a zone the server refused again; a failed send is tried on the next return", async () => {
    const warn = jest.spyOn(console, "warn").mockImplementation(() => {});
    (api.updateMe as jest.Mock).mockRejectedValue(new ApiRequestError(422, '{"detail":"Invalid IANA timezone name."}'));
    await render(<Probe user={atHome} token="a" />);
    mockDeviceZone = "Mars/Olympus_Mons";
    await returnToForeground();
    await returnToForeground();
    expect(zonePatches()).toHaveLength(1);

    (api.updateMe as jest.Mock).mockRejectedValueOnce(new TypeError("Network request failed"));
    mockDeviceZone = "Asia/Kathmandu";
    await returnToForeground();
    (api.updateMe as jest.Mock).mockResolvedValue(answer("Asia/Kathmandu"));
    await returnToForeground();
    expect(zonePatches().map(([, body]) => body.timezone)).toEqual(["Mars/Olympus_Mons", "Asia/Kathmandu", "Asia/Kathmandu"]);
    warn.mockRestore();
  });

  it("stops listening at sign-out", async () => {
    const rendered = await render(<Probe user={atHome} token="a" />);
    await rendered.rerender(<Probe user={null} token={null} />);
    mockDeviceZone = "Asia/Kathmandu";
    await clockChanged();
    await returnToForeground();
    expect(zonePatches()).toEqual([]);
    expect(mockClockListeners.size + mockAppStateListeners.size).toBe(0);
  });
});
