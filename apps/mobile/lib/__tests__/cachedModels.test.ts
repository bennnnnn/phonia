import {
  clearCachedModels,
  readCachedModels,
  writeCachedModels,
} from "@/lib/cachedModels";
import type { ModelInfo } from "@/lib/api/types";
import {
  deleteAsync,
  getInfoAsync,
  readAsStringAsync,
  writeAsStringAsync,
} from "expo-file-system/legacy";

jest.mock("expo-file-system/legacy", () => ({
  cacheDirectory: "/mock-cache/",
  getInfoAsync: jest.fn(),
  readAsStringAsync: jest.fn(),
  writeAsStringAsync: jest.fn(),
  deleteAsync: jest.fn(),
}));

const PATH = "/mock-cache/cached-models.json";
const everyday: ModelInfo = {
  id: "free-chat",
  label: "Everyday",
  description: "Fast everyday chat.",
  tier: "fast",
  plan_access: "free",
  available: true,
};
// /models also sends pricing and live health; the phone keeps neither.
const served = {
  ...everyday,
  input_price_per_m: 0.14,
  output_price_per_m: 0.28,
  quota_multiplier: 1,
  healthy: false,
  latency_p50_ms: 900,
  health_samples: 12,
};

function onDisk(contents: unknown) {
  (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
  (readAsStringAsync as jest.Mock).mockResolvedValue(
    typeof contents === "string" ? contents : JSON.stringify(contents),
  );
}

beforeEach(() => {
  jest.clearAllMocks();
});

it("returns null when no cache file exists", async () => {
  (getInfoAsync as jest.Mock).mockResolvedValue({ exists: false });
  await expect(readCachedModels("u1")).resolves.toBeNull();
});

it("reads the catalog the same account cached", async () => {
  onDisk({ user_id: "u1", models: [everyday] });
  await expect(readCachedModels("u1")).resolves.toEqual([everyday]);
  expect(readAsStringAsync).toHaveBeenCalledWith(PATH);
});

it("ignores a catalog another account cached", async () => {
  onDisk({ user_id: "u1", models: [everyday] });
  await expect(readCachedModels("u2")).resolves.toBeNull();
});

it.each([
  ["not json", "not json"],
  ["no account", { models: [everyday] }],
  ["no list", { user_id: "u1", models: "free-chat" }],
  ["an empty list", { user_id: "u1", models: [] }],
  ["no readable entry", { user_id: "u1", models: [{ id: "free-chat" }, null] }],
])("returns null for a cache with %s", async (_case, contents) => {
  onDisk(contents);
  await expect(readCachedModels("u1")).resolves.toBeNull();
});

it("skips an entry it cannot read and keeps the rest", async () => {
  onDisk({
    user_id: "u1",
    models: [everyday, { ...everyday, id: "x", plan_access: "team" }],
  });
  await expect(readCachedModels("u1")).resolves.toEqual([everyday]);
});

it("writes the account and catalog fields, never prices, multipliers or live health", async () => {
  await writeCachedModels("u1", [served]);
  expect(writeAsStringAsync).toHaveBeenCalledWith(
    PATH,
    JSON.stringify({ user_id: "u1", models: [everyday] }),
  );
});

it("clears the cached catalog", async () => {
  await clearCachedModels();
  expect(deleteAsync).toHaveBeenCalledWith(PATH, { idempotent: true });
});

it("finishes an already-started catalog write before clearing for signout", async () => {
  let finish!: () => void;
  let disk: string | null = null;
  (writeAsStringAsync as jest.Mock).mockImplementationOnce(async (_path, data) => {
    await new Promise<void>((resolve) => { finish = resolve; });
    disk = data;
  });
  (deleteAsync as jest.Mock).mockImplementationOnce(async () => { disk = null; });
  const write = writeCachedModels("u1", [everyday]);
  await Promise.resolve();
  const clear = clearCachedModels();
  await Promise.resolve();
  finish();
  await Promise.all([write, clear]);
  expect(disk).toBeNull();
});
