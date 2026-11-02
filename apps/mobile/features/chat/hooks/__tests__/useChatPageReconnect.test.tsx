import { act, render } from "@testing-library/react-native";

import { registerDrawer } from "@/features/chat/drawer/drawer";
import { useChatPageReconnect } from "@/features/chat/hooks/useChatPageReconnect";
import { noteChatPageRead } from "@/features/chat/model/pageReads";
import { reportDisconnected, reportReconnected } from "@/lib/reconnectRefresh";

jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => 1 }));
jest.mock("expo-router", () => {
  const { useEffect } = jest.requireActual<typeof import("react")>("react");
  return {
    useFocusEffect: (effect: () => void | (() => void)) => {
      useEffect(effect, [effect]);
    },
  };
});

let busy = false;
let drawerOpen = false;
const refetch = jest.fn(async () => {});

function Probe({ chatId }: { chatId: string | null }) {
  useChatPageReconnect({ chatId, busy: () => busy, refetch });
  return null;
}

/** The API back, then the longest wait. */
async function apiBack(): Promise<void> {
  await act(async () => {
    reportReconnected();
    jest.advanceTimersByTime(10_000);
  });
}

let unregisterDrawer: () => void = () => {};
beforeEach(() => {
  jest.useFakeTimers();
  busy = false;
  drawerOpen = false;
  refetch.mockClear();
  unregisterDrawer = registerDrawer(jest.fn(), jest.fn(), () => drawerOpen);
});
afterEach(() => {
  unregisterDrawer();
  jest.useRealTimers();
  jest.restoreAllMocks();
});

it("reads the open chat's page once the API is back", async () => {
  await render(<Probe chatId="c1" />);
  await apiBack();
  expect(refetch).toHaveBeenCalledTimes(1);
  expect(refetch).toHaveBeenCalledWith("c1", expect.any(Function));
});

it("leaves a new chat, a page under the drawer, and a page a load or a turn is bringing", async () => {
  const view = await render(<Probe chatId={null} />);
  await apiBack();
  await view.rerender(<Probe chatId="c1" />);
  drawerOpen = true;
  await apiBack();
  drawerOpen = false;
  busy = true;
  await apiBack();
  expect(refetch).not.toHaveBeenCalled();
});

it("leaves the page when the drawer opens over it during the wait", async () => {
  jest.spyOn(Math, "random").mockReturnValue(0.5);
  await render(<Probe chatId="c1" />);
  await act(async () => {
    reportReconnected();
    jest.advanceTimersByTime(4000);
  });
  drawerOpen = true;
  await act(async () => { jest.advanceTimersByTime(6000); });
  expect(refetch).not.toHaveBeenCalled();
});

it("leaves a page a read brought since the connection was lost, not one read before it", async () => {
  await render(<Probe chatId="c1" />);
  noteChatPageRead("c1");
  jest.advanceTimersByTime(1000);
  reportDisconnected();
  await apiBack();
  expect(refetch).toHaveBeenCalledTimes(1);

  // A reply's page, read as the API came back, before the check saw it.
  reportDisconnected();
  jest.advanceTimersByTime(1000);
  noteChatPageRead("c1");
  await apiBack();
  expect(refetch).toHaveBeenCalledTimes(1);
});
