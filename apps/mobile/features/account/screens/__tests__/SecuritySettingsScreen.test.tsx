import { act, fireEvent, render } from "@testing-library/react-native";
import { Alert } from "react-native";

import SecuritySettingsScreen from "@/features/account/screens/SecuritySettingsScreen";

const mockListSessions = jest.fn();
const mockRevokeSession = jest.fn();
const mockDestructive = jest.fn();

jest.mock("@shopify/flash-list", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  const { View } = jest.requireActual<typeof import("react-native")>("react-native");
  return {
    FlashList: ({
      data,
      renderItem,
      ListEmptyComponent,
      ListFooterComponent,
    }: {
      data: unknown[];
      renderItem: (info: { item: unknown; index: number }) => React.ReactNode;
      ListEmptyComponent?: React.ReactNode;
      ListFooterComponent?: React.ReactNode;
    }) => (
      <View>
        {data.length === 0 ? ListEmptyComponent : null}
        {data.map((item, index) => (
          <View key={index}>{renderItem({ item, index })}</View>
        ))}
        {ListFooterComponent}
      </View>
    ),
  };
});
jest.mock("expo-router", () => {
  const React = jest.requireActual<typeof import("react")>("react");
  return {
    Redirect: () => null,
    useRouter: () => ({ replace: jest.fn() }),
    useFocusEffect: (callback: () => void) => React.useEffect(callback, [callback]),
  };
});
jest.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ token: "token", signOut: jest.fn() }),
}));
jest.mock("@/contexts/actionFeedbackCore", () => ({
  useActionFeedbackOptional: () => null,
}));
jest.mock("@/lib/api", () => ({
  api: {
    listSessions: (...args: unknown[]) => mockListSessions(...args),
    revokeSession: (...args: unknown[]) => mockRevokeSession(...args),
    logoutAll: jest.fn(),
  },
}));
jest.mock("@/lib/haptics", () => ({
  ...jest.requireActual("@/lib/haptics"),
  notifyDestructive: (...args: unknown[]) => mockDestructive(...args),
}));
jest.mock("@/lib/theme", () => ({
  useTheme: () => ({
    bg: "#fff",
    settingsSurface: "#eee",
    border: "#ddd",
    primary: "#00f",
    text: "#111",
    textSecondary: "#555",
    textTertiary: "#777",
    danger: "#f00",
  }),
}));

function deferred<T>() {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>((done) => {
    resolve = done;
  });
  return { promise, resolve };
}

beforeEach(() => {
  jest.clearAllMocks();
  mockListSessions.mockReset();
  mockRevokeSession.mockReset();
  jest.spyOn(Alert, "alert").mockImplementation(() => {});
});
afterEach(() => jest.restoreAllMocks());

it("replaces the initial security spinner with the shared settings skeleton", async () => {
  const pending = deferred<{
    sessions: {
      id: string;
      device_label: string;
      platform: string;
      created_at: string;
      last_seen_at: string;
      current: boolean;
    }[];
  }>();
  mockListSessions.mockReturnValueOnce(pending.promise);
  const ui = await render(<SecuritySettingsScreen />);

  expect(ui.getByTestId("settings-loading-skeleton")).toBeTruthy();

  await act(async () => {
    pending.resolve({
      sessions: [{
        id: "current",
        device_label: "This iPhone",
        platform: "ios",
        created_at: "2026-09-19T12:00:00Z",
        last_seen_at: "2026-09-19T12:00:00Z",
        current: true,
      }],
    });
  });
  expect(ui.queryByTestId("settings-loading-skeleton")).toBeNull();
  expect(ui.getByText("This iPhone")).toBeTruthy();
});

it("keeps security load errors distinct and retryable", async () => {
  mockListSessions
    .mockRejectedValueOnce(new Error("offline"))
    .mockResolvedValueOnce({ sessions: [] });
  const ui = await render(<SecuritySettingsScreen />);

  expect(ui.getByText("common.error")).toBeTruthy();
  expect(ui.queryByTestId("settings-loading-skeleton")).toBeNull();
  await fireEvent.press(ui.getByText("common.retry"));
  expect(mockListSessions).toHaveBeenCalledTimes(2);
});

it("haptics only after confirmed session revocation succeeds", async () => {
  const pending = deferred<void>();
  mockListSessions.mockResolvedValue({
    sessions: [{
      id: "other",
      device_label: "Other iPhone",
      platform: "ios",
      created_at: "2026-09-18T12:00:00Z",
      last_seen_at: "2026-09-18T12:00:00Z",
      current: false,
    }],
  });
  mockRevokeSession.mockReturnValue(pending.promise);
  const ui = await render(<SecuritySettingsScreen />);

  await fireEvent.press(ui.getByText("settings.revoke_session"));
  expect(mockDestructive).not.toHaveBeenCalled();
  const buttons = (Alert.alert as jest.Mock).mock.calls.at(-1)[2];
  const confirm = buttons.find(
    (button: { style?: string }) => button.style === "destructive",
  ).onPress;
  await act(() => { confirm(); });
  expect(mockDestructive).not.toHaveBeenCalled();

  await act(async () => { pending.resolve(); });
  expect(mockDestructive).toHaveBeenCalledTimes(1);
});

it("says when a device was last active in the app's date format, or that it is unknown", async () => {
  mockListSessions.mockResolvedValue({
    sessions: [
      {
        id: "a",
        device_label: "Old iPad",
        platform: "ios",
        created_at: "2026-09-19T12:00:00Z",
        last_seen_at: null,
        current: false,
      },
      {
        id: "b",
        device_label: "Pixel",
        platform: "android",
        created_at: "2026-09-19T12:00:00Z",
        last_seen_at: "2026-09-19T12:00:00Z",
        current: true,
      },
    ],
  });
  const ui = await render(<SecuritySettingsScreen />);
  await act(async () => {});
  // A device with a name but no time is not an "Unknown device".
  expect(ui.getByText("Old iPad")).toBeTruthy();
  expect(ui.getByText(/settings\.last_active_unknown/)).toBeTruthy();
  expect(ui.queryByText("settings.unknown_device")).toBeNull();
  expect(ui.getAllByText(/^settings\.last_active(?!_unknown)/)).toHaveLength(1);
});
