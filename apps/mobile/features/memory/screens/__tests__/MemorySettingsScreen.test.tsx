import { act, render } from "@testing-library/react-native";
import MemorySettingsScreen from "@/features/memory/screens/MemorySettingsScreen";
import { reportReconnected } from "@/lib/reconnectRefresh";

let mockSession = 1;
let mockToken: string | null = "token-a";
let mockFocused = true;
const mockFetch = jest.fn();
const mockPrefetch = jest.fn();
const mockUpdate = jest.fn();
const mockFeedback = { error: jest.fn() };
const mockRouter = { push: jest.fn() };
const mockT = (key: string, args?: { count?: number }) => args?.count ? `${args.count} saved` : key;
let mockSwitch: { onValueChange: (next: boolean) => void; busy: boolean };
let mockLink: { onPress: () => void; value?: string };
let mockRetry: () => void;
let mockCached: unknown[] | undefined;
const mockCacheListeners = new Set<() => void>();
const loaded = (rows: unknown[]) => ({ data: rows, error: null });
const failed = { data: null, error: new Error("Request failed: 500") };
jest.mock("@/lib/api", () => ({
  api: { clearMemories: jest.fn() },
}));
jest.mock("@/lib/auth", () => ({ getSessionGeneration: () => mockSession }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ token: mockToken, user: { memory_enabled: true }, updateUser: mockUpdate }) }));
jest.mock("@/contexts/actionFeedbackCore", () => ({ useActionFeedbackOptional: () => mockFeedback }));
jest.mock("react-i18next", () => ({ useTranslation: () => ({ t: mockT }) }));
jest.mock("@/lib/theme", () => ({ useTheme: () => ({}) }));
jest.mock("@/ui/feedback/StateView", () => ({ StateView: ({ onRetry }: { onRetry: () => void }) => { mockRetry = onRetry; return null; } }));
jest.mock("@/features/account/components/settingsUi", () => ({
  SettingsPage: ({ children }: { children: React.ReactNode }) => children,
  SettingsGroup: ({ children }: { children: React.ReactNode }) => children,
  SettingsSwitchRow: (props: typeof mockSwitch & { title: string }) => {
    if (props.title === "settings.memory") mockSwitch = props;
    return null;
  },
  SettingsLinkRow: (props: typeof mockLink & { title: string }) => {
    if (props.title === "settings.memory_view") mockLink = props;
    return null;
  },
}));
jest.mock("@/features/memory/model/memoryListCache", () => ({
  fetchMemories: (...args: unknown[]) => mockFetch(...args), prefetchMemories: (...args: unknown[]) => mockPrefetch(...args),
  getCachedMemories: () => mockCached,
  subscribeMemoriesCache: (listener: () => void) => { mockCacheListeners.add(listener); return () => mockCacheListeners.delete(listener); },
}));
jest.mock("expo-router", () => ({
  Redirect: () => null, useRouter: () => mockRouter,
  useFocusEffect: (effect: () => void | (() => void)) => {
    const React = jest.requireActual("react");
    const focused = mockFocused;
    React.useEffect(() => focused ? effect() : undefined, [effect, focused]);
  },
}));
beforeEach(() => {
  jest.clearAllMocks(); mockSession = 1; mockToken = "token-a"; mockFocused = true;
  mockCached = undefined;
  mockFetch.mockResolvedValue(loaded([])); mockUpdate.mockResolvedValue(undefined);
});

it("does not put an old account's count in the next account", async () => {
  let resolve!: (result: ReturnType<typeof loaded>) => void;
  mockFetch.mockReturnValueOnce(new Promise((done) => { resolve = done; }));
  const ui = await render(<MemorySettingsScreen />);
  mockSession++; mockToken = "token-b"; await ui.rerender(<MemorySettingsScreen />);
  await act(async () => { resolve(loaded([{}, {}, {}])); });
  expect(mockLink.value).toBeUndefined();
});

it.each(["account", "blur-refocus", "unmount"])("rejects old toggle/navigation callbacks after %s", async (change) => {
  const ui = await render(<MemorySettingsScreen />);
  const toggle = mockSwitch.onValueChange;
  const navigate = mockLink.onPress;
  if (change === "account") mockSession++;
  if (change === "blur-refocus") {
    mockFocused = false; await ui.rerender(<MemorySettingsScreen />);
    mockFocused = true; await ui.rerender(<MemorySettingsScreen />);
  }
  if (change === "unmount") await ui.unmount();
  await act(() => { toggle(false); navigate(); });
  expect(mockUpdate).not.toHaveBeenCalled();
  expect(mockRouter.push).not.toHaveBeenCalled();
  expect(mockPrefetch).not.toHaveBeenCalled();
});

it("hides a previous account's pending toggle and its failure", async () => {
  let reject!: (error: Error) => void;
  mockUpdate.mockReturnValueOnce(new Promise((_, fail) => { reject = fail; }));
  const ui = await render(<MemorySettingsScreen />);
  await act(() => { mockSwitch.onValueChange(false); });
  expect(mockSwitch.busy).toBe(true);
  mockSession++; mockToken = "token-b"; await ui.rerender(<MemorySettingsScreen />);
  expect(mockSwitch.busy).toBe(false);
  await act(async () => { reject(new Error("offline")); });
  expect(mockFeedback.error).not.toHaveBeenCalled();
});

it("deduplicates rapid toggle callbacks", async () => {
  let resolve!: () => void;
  mockUpdate.mockReturnValueOnce(new Promise<void>((done) => { resolve = done; }));
  await render(<MemorySettingsScreen />);
  const toggle = mockSwitch.onValueChange;
  await act(() => { toggle(false); toggle(false); });
  expect(mockUpdate).toHaveBeenCalledTimes(1);
  await act(async () => { resolve(); });
  expect(mockSwitch.busy).toBe(false);
});

it.each(["blur-refocus", "unmount-remount"])("keeps a pending toggle exclusive across %s", async (change) => {
  let resolve!: () => void;
  mockUpdate.mockReturnValueOnce(new Promise<void>((done) => { resolve = done; }));
  let ui = await render(<MemorySettingsScreen />);
  await act(() => { mockSwitch.onValueChange(false); });
  if (change === "blur-refocus") {
    mockFocused = false; await ui.rerender(<MemorySettingsScreen />);
    mockFocused = true; await ui.rerender(<MemorySettingsScreen />);
  } else {
    await ui.unmount(); ui = await render(<MemorySettingsScreen />);
  }
  expect(mockSwitch.busy).toBe(true);
  await act(() => { mockSwitch.onValueChange(true); });
  expect(mockUpdate).toHaveBeenCalledTimes(1);
  await act(async () => { resolve(); });
  expect(mockSwitch.busy).toBe(false);
});

it("refreshes the saved count when returning from the memory screen", async () => {
  mockFetch.mockResolvedValueOnce(loaded([{}, {}])).mockResolvedValueOnce(loaded([{}]));
  const ui = await render(<MemorySettingsScreen />);
  expect(mockLink.value).toBe("2 saved");
  mockFocused = false; await ui.rerender(<MemorySettingsScreen />);
  mockFocused = true; await ui.rerender(<MemorySettingsScreen />);
  expect(mockLink.value).toBe("1 saved");
});

it("offers retry when the memory count cannot load", async () => {
  mockFetch.mockResolvedValueOnce(failed).mockResolvedValueOnce(loaded([{}]));
  await render(<MemorySettingsScreen />);
  expect(mockRetry).toEqual(expect.any(Function));
  await act(() => { mockRetry(); });
  expect(mockFetch).toHaveBeenLastCalledWith("token-a", { force: true });
  expect(mockLink.value).toBe("1 saved");
});

it("updates the displayed count when a pending deletion rolls back after navigation", async () => {
  mockFetch.mockResolvedValueOnce(loaded([]));
  await render(<MemorySettingsScreen />);
  expect(mockLink.value).toBeUndefined();
  await act(() => { mockCached = [{}]; mockCacheListeners.forEach((notify) => notify()); });
  expect(mockLink.value).toBe("1 saved");
});

it("reads the count again once the API answers after an outage, only while the page has focus", async () => {
  jest.useFakeTimers();
  try {
    const ui = await render(<MemorySettingsScreen />);
    expect(mockFetch).toHaveBeenCalledTimes(1);
    const apiBack = () => act(async () => {
      reportReconnected();
      await jest.advanceTimersByTimeAsync(10_000);
    });
    await apiBack();
    expect(mockFetch).toHaveBeenCalledTimes(2);
    expect(mockFetch).toHaveBeenLastCalledWith("token-a", { force: false });
    mockFocused = false;
    await ui.rerender(<MemorySettingsScreen />);
    await apiBack();
    expect(mockFetch).toHaveBeenCalledTimes(2);
  } finally {
    jest.useRealTimers();
  }
});
