import { api } from "@/lib/api";
import {
  fetchTodayUsage,
  getCachedUsage,
  invalidateUsageCache,
} from "@/lib/cache/usageCache";

jest.mock("@/lib/api", () => ({
  api: {
    todayUsage: jest.fn(),
  },
}));

const todayUsage = api.todayUsage as jest.Mock;

const sample = {
  date: "2026-08-24",
  input_tokens: 10,
  output_tokens: 20,
  daily_limit: 100_000,
  remaining: 99_970,
};

describe("usageCache", () => {
  beforeEach(() => {
    jest.clearAllMocks();
    invalidateUsageCache();
  });

  it("returns cached usage without refetching when fresh", async () => {
    todayUsage.mockResolvedValue(sample);
    await expect(fetchTodayUsage("user-1:0", "tok")).resolves.toEqual(sample);
    // The hourly token rotation keeps the same account's usage.
    await expect(fetchTodayUsage("user-1:0", "rotated")).resolves.toEqual(sample);
    expect(todayUsage).toHaveBeenCalledTimes(1);
    expect(getCachedUsage("user-1:0")).toEqual(sample);
  });

  it("refetches when forced", async () => {
    todayUsage.mockResolvedValueOnce(sample).mockResolvedValueOnce({
      ...sample,
      remaining: 1,
    });
    await fetchTodayUsage("user-1:0", "tok");
    await expect(fetchTodayUsage("user-1:0", "tok", { force: true })).resolves.toEqual({
      ...sample,
      remaining: 1,
    });
    expect(todayUsage).toHaveBeenCalledTimes(2);
  });
});
