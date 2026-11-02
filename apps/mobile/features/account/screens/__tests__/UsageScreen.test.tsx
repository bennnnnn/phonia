import { fireEvent, render } from "@testing-library/react-native";

import UsageScreen from "@/features/account/screens/UsageScreen";

let mockUser: Record<string, unknown>;
let mockUsage: Record<string, unknown>;
const mockRefresh = jest.fn();

jest.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: Record<string, unknown>) =>
      options ? `${key} ${JSON.stringify(options)}` : key,
  }),
}));
jest.mock("expo-router", () => ({ Redirect: () => null, router: { push: jest.fn() } }));
jest.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ token: "tok", user: mockUser }) }));
jest.mock("@/features/account/hooks/useUsage", () => ({ useUsage: () => mockUsage }));
jest.mock("@/features/account/hooks/useLiveTalkMinutes", () => ({
  useLiveTalkMinutes: (enabled: boolean) => (enabled ? { remaining: 42, limit: 60 } : null),
}));
jest.mock("@/lib/quota", () => ({ formatUsageSummary: () => "80% of today's limit left" }));

beforeEach(() => {
  jest.clearAllMocks();
  mockUser = { plan: "pro", features: ["all_models", "live_talk"] };
  mockUsage = { usage: { remaining: 8, daily_limit: 10 }, loading: false, error: false, refresh: mockRefresh };
});

it("shows today's usage and this month's live talk minutes", async () => {
  const view = await render(<UsageScreen />);
  expect(view.getByText("80% of today's limit left")).toBeTruthy();
  expect(view.getByText("settings.live_talk_minutes")).toBeTruthy();
  expect(view.getByText('settings.live_talk_minutes_left {"count":42,"limit":60}')).toBeTruthy();
});

it("leaves live talk out on a plan without it", async () => {
  mockUser = { plan: "free", features: [] };
  const view = await render(<UsageScreen />);
  expect(view.queryByText("settings.live_talk_minutes")).toBeNull();
});

it("offers a retry when today's usage would not load", async () => {
  mockUsage = { usage: null, loading: false, error: true, refresh: mockRefresh };
  const view = await render(<UsageScreen />);
  await fireEvent.press(view.getByText("settings.usage_unavailable"));
  expect(mockRefresh).toHaveBeenCalledWith({ force: true });
});
