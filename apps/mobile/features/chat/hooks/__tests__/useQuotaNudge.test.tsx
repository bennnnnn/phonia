import { act, renderHook } from "@testing-library/react-native";

import { useQuotaNudge } from "@/features/chat/hooks/useQuotaNudge";
import { resetQuotaNudgeDismissal } from "@/features/chat/model/quotaNudgeDismissal";
import { fetchTodayUsage } from "@/lib/cache/usageCache";
import type { Usage } from "@/lib/api";

jest.mock("@/lib/cache/usageCache", () => ({ fetchTodayUsage: jest.fn() }));
// One object per account, as the provider keeps it.
const mockGetToken = () => "token";
const mockSessions = {
  a: { account: "user-a:0", getToken: mockGetToken },
  b: { account: "user-b:0", getToken: mockGetToken },
};
let mockSession: { account: string | null; getToken: () => string | null } = mockSessions.a;
jest.mock("@/contexts/accountSession", () => ({
  useAccountSession: () => mockSession,
}));
// The launch cache paints every plan as free until /auth/me answers.
let mockProfileValidated = true;
jest.mock("@/contexts/AuthContext", () => ({
  useAuthOptional: () => ({ profileValidated: mockProfileValidated }),
}));

const fetchUsage = fetchTodayUsage as jest.Mock;

function usage(used: number, limit = 100_000): Usage {
  return {
    date: "2026-10-21",
    input_tokens: used,
    output_tokens: 0,
    used_tokens: used,
    daily_limit: limit,
    remaining: limit - used,
  };
}

async function setup(isPaid = false) {
  const view = await renderHook(({ paid }: { paid: boolean }) => useQuotaNudge({ isPaid: paid }), {
    initialProps: { paid: isPaid },
  });
  await act(async () => {});
  return view;
}

beforeEach(() => {
  fetchUsage.mockReset();
  fetchUsage.mockResolvedValue(usage(50_000));
  mockSession = mockSessions.a;
  mockProfileValidated = true;
  resetQuotaNudgeDismissal();
});

it("reads today's usage once, then takes each turn's usage without a request", async () => {
  const { result } = await setup();
  expect(fetchUsage).toHaveBeenCalledTimes(1);
  expect(fetchUsage).toHaveBeenCalledWith("user-a:0", "token");
  expect(result.current).toMatchObject({ show: false, usedPct: 50 });

  await act(async () => { result.current.applyTurnUsage({ used_tokens: 79_000, daily_limit: 100_000 }); });
  expect(result.current).toMatchObject({ show: false, usedPct: 79 });
  await act(async () => { result.current.applyTurnUsage({ used_tokens: 81_000, daily_limit: 100_000 }); });
  expect(result.current).toMatchObject({ show: true, usedPct: 81 });
  // Over the limit still reads as 100%.
  await act(async () => { result.current.applyTurnUsage({ used_tokens: 120_000, daily_limit: 100_000 }); });
  expect(result.current.usedPct).toBe(100);
  expect(fetchUsage).toHaveBeenCalledTimes(1);
});

it("shows from the first read, and not again once dismissed today", async () => {
  fetchUsage.mockResolvedValue(usage(90_000));
  const { result } = await setup();
  expect(result.current).toMatchObject({ show: true, usedPct: 90 });
  await act(async () => { result.current.dismiss(); });
  expect(result.current.show).toBe(false);
  await act(async () => { result.current.applyTurnUsage({ used_tokens: 95_000, daily_limit: 100_000 }); });
  expect(result.current).toMatchObject({ show: false, usedPct: 95 });
});

it("reads again for another account", async () => {
  const { rerender } = await setup();
  mockSession = mockSessions.b;
  await act(async () => { await rerender({ paid: false }); });
  expect(fetchUsage).toHaveBeenCalledTimes(2);
  expect(fetchUsage).toHaveBeenLastCalledWith("user-b:0", "token");
});

it("waits for the server's plan before reading today's usage", async () => {
  // A paid plan painted from the launch cache must not read usage, nor show from a turn.
  mockProfileValidated = false;
  const { result, rerender } = await setup();
  expect(fetchUsage).not.toHaveBeenCalled();
  await act(async () => { result.current.applyTurnUsage({ used_tokens: 99_000, daily_limit: 100_000 }); });
  expect(result.current).toMatchObject({ show: false, usedPct: 0 });

  mockProfileValidated = true;
  await act(async () => { await rerender({ paid: false }); });
  expect(fetchUsage).toHaveBeenCalledTimes(1);
});

it("never reads or shows for a paid plan", async () => {
  const { result } = await setup(true);
  expect(fetchUsage).not.toHaveBeenCalled();
  await act(async () => { result.current.applyTurnUsage({ used_tokens: 99_000, daily_limit: 100_000 }); });
  expect(result.current).toMatchObject({ show: false, usedPct: 0 });
});

it("does nothing signed out", async () => {
  mockSession = { account: null, getToken: () => null };
  const { result } = await setup();
  expect(fetchUsage).not.toHaveBeenCalled();
  await act(async () => { result.current.applyTurnUsage({ used_tokens: 99_000, daily_limit: 100_000 }); });
  expect(result.current.show).toBe(false);
});
