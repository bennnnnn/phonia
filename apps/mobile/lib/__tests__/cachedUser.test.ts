import {
  cachedUserMatchesToken,
  clearCachedUser,
  mergeCachedUser,
  readCachedLocaleSync,
  readCachedUser,
  writeCachedUser,
} from "@/lib/cachedUser";
import type { User } from "@/lib/api/types";
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

/** The synchronous read the first frame uses (`lib/syncFileRead.ts`). */
const mockSyncFiles = new Map<string, string>();
jest.mock("expo-file-system", () => ({
  Paths: { document: "/mock-docs/", cache: "/mock-cache/" },
  File: class {
    private readonly path: string;
    constructor(directory: string, name: string) {
      this.path = `${directory}${name}`;
    }
    get exists() {
      return mockSyncFiles.has(this.path);
    }
    textSync() {
      return mockSyncFiles.get(this.path) ?? "";
    }
  },
}));

const user: User = {
  id: "u1",
  email: "a@b.com",
  name: "Alex",
  avatar_url: null,
  default_model: "smart-chat",
  plan: "free",
  enabled_models: null,
  response_tone: "neutral",
  memory_enabled: true,
  push_notifications_enabled: true,
  email_reminders_enabled: false,
  reminder_lead_minutes: 10,
  locale: "en",
  timezone: "UTC",
  location: null,
  location_enabled: false,
  custom_instructions: null,
  age: null,
  country: null,
  job: null,
  created_at: "2026-01-01T00:00:00Z",
};

describe("cachedUser", () => {
  beforeEach(() => {
    jest.clearAllMocks();
  });

  it("returns null when no cache file exists", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: false });
    await expect(readCachedUser()).resolves.toBeNull();
  });

  it("reads a cached user subset (id/name/avatar/plan only) when present", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (readAsStringAsync as jest.Mock).mockResolvedValue(
      JSON.stringify({
        id: "u1",
        name: "Alex",
        avatar_url: null,
        plan: "free",
      }),
    );
    await expect(readCachedUser()).resolves.toEqual({
      id: "u1",
      name: "Alex",
      avatar_url: null,
      plan: "free",
      locale: "",
    });
  });

  it("returns null for malformed cache content", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (readAsStringAsync as jest.Mock).mockResolvedValue("not json");
    await expect(readCachedUser()).resolves.toBeNull();
  });

  it("returns null when the parsed cache has no id", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (readAsStringAsync as jest.Mock).mockResolvedValue(
      JSON.stringify({ email: "a@b.com" }),
    );
    await expect(readCachedUser()).resolves.toBeNull();
  });

  it("writes ONLY the non-sensitive display fields to disk (strips PII/prefs)", async () => {
    await writeCachedUser(user);
    expect(writeAsStringAsync).toHaveBeenCalledWith(
      "/mock-cache/cached-user.json",
      JSON.stringify({
        id: "u1",
        name: "Alex",
        avatar_url: null,
        plan: "free",
        locale: "en",
      }),
    );
  });

  it("does NOT persist email, prefs, location, age, or custom_instructions", async () => {
    await writeCachedUser(user);
    const written = (writeAsStringAsync as jest.Mock).mock.calls[0][1] as string;
    const parsed = JSON.parse(written) as Record<string, unknown>;
    // PII and prefs must be absent from the cached blob.
    expect(parsed).not.toHaveProperty("email");
    expect(parsed).not.toHaveProperty("push_notifications_enabled");
    expect(parsed).not.toHaveProperty("email_reminders_enabled");
    expect(parsed).not.toHaveProperty("reminder_lead_minutes");
    expect(parsed).not.toHaveProperty("memory_enabled");
    expect(parsed).not.toHaveProperty("location");
    expect(parsed).not.toHaveProperty("age");
    expect(parsed).not.toHaveProperty("country");
    expect(parsed).not.toHaveProperty("job");
    expect(parsed).not.toHaveProperty("custom_instructions");
    expect(parsed).not.toHaveProperty("default_model");
    expect(parsed).not.toHaveProperty("timezone");
  });

  it("keeps the language, so a cold start draws its first frame in it", async () => {
    await writeCachedUser({ ...user, locale: "es" });
    const written = (writeAsStringAsync as jest.Mock).mock.calls[0][1] as string;
    expect(JSON.parse(written)).toMatchObject({ locale: "es" });

    expect(readCachedLocaleSync()).toBeNull();
    mockSyncFiles.set("/mock-cache/cached-user.json", written);
    expect(readCachedLocaleSync()).toBe("es");
    mockSyncFiles.set("/mock-cache/cached-user.json", JSON.stringify({ id: "u1", plan: "free" }));
    expect(readCachedLocaleSync()).toBeNull();
    mockSyncFiles.set("/mock-cache/cached-user.json", "{half a file");
    expect(readCachedLocaleSync()).toBeNull();

    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (readAsStringAsync as jest.Mock).mockResolvedValue(written);
    expect(mergeCachedUser((await readCachedUser())!).locale).toBe("es");
  });

  it("keeps the AI-consent time so a cold start does not ask again", async () => {
    await writeCachedUser({ ...user, ai_data_consent_at: "2026-10-19T12:00:00Z" });
    const written = (writeAsStringAsync as jest.Mock).mock.calls[0][1] as string;
    expect(JSON.parse(written)).toMatchObject({ ai_data_consent_at: "2026-10-19T12:00:00Z" });

    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (readAsStringAsync as jest.Mock).mockResolvedValue(written);
    const cached = await readCachedUser();
    expect(cached?.ai_data_consent_at).toBe("2026-10-19T12:00:00Z");
    expect(mergeCachedUser(cached!).ai_data_consent_at).toBe("2026-10-19T12:00:00Z");
  });

  it("reads consent as unknown (undefined) from a cache written before the field", async () => {
    (getInfoAsync as jest.Mock).mockResolvedValue({ exists: true });
    (readAsStringAsync as jest.Mock).mockResolvedValue(
      JSON.stringify({ id: "u1", name: "Alex", avatar_url: null, plan: "free" }),
    );
    expect((await readCachedUser())?.ai_data_consent_at).toBeUndefined();

    (readAsStringAsync as jest.Mock).mockResolvedValue(
      JSON.stringify({ id: "u1", name: null, avatar_url: null, plan: "free", ai_data_consent_at: null }),
    );
    expect((await readCachedUser())?.ai_data_consent_at).toBeNull();
  });

  it("clears the cached user", async () => {
    await clearCachedUser();
    expect(deleteAsync).toHaveBeenCalledWith("/mock-cache/cached-user.json", {
      idempotent: true,
    });
  });

  it("mergeCachedUser fills re-fetched fields with safe defaults", async () => {
    const merged = mergeCachedUser({
      id: "u1",
      name: "Alex",
      avatar_url: null,
      plan: "free",
      locale: "fr",
    });
    // Display fields come from the cache.
    expect(merged.id).toBe("u1");
    expect(merged.name).toBe("Alex");
    expect(merged.plan).toBe("free");
    expect(merged.locale).toBe("fr");
    // PII/prefs are defaulted (empty/false/null) — replaced by api.me() on launch.
    expect(merged.email).toBe("");
    expect(merged.push_notifications_enabled).toBe(false);
    expect(merged.memory_enabled).toBe(false);
    expect(merged.location).toBeNull();
    expect(merged.age).toBeNull();
    expect(merged.custom_instructions).toBeNull();
  });
});

it("finishes an already-started user cache write before clearing for signout", async () => {
  let finish!: () => void;
  let disk: string | null = null;
  (writeAsStringAsync as jest.Mock).mockImplementationOnce(async (_path, data) => {
    await new Promise<void>((resolve) => { finish = resolve; });
    disk = data;
  });
  (deleteAsync as jest.Mock).mockImplementationOnce(async () => { disk = null; });
  const write = writeCachedUser(user);
  await Promise.resolve();
  const clear = clearCachedUser();
  await Promise.resolve();
  finish();
  await Promise.all([write, clear]);
  expect(disk).toBeNull();
});

function accessTokenFor(sub: unknown): string {
  const encode = (value: unknown) => btoa(JSON.stringify(value)).replace(/=/g, "").replace(/\+/g, "-").replace(/\//g, "_");
  return `${encode({ alg: "HS256", typ: "JWT" })}.${encode({ sub })}.signature`;
}

it("selects cached display fields only for the stored token's subject", () => {
  expect(cachedUserMatchesToken(user, accessTokenFor(user.id))).toBe(true);
  expect(cachedUserMatchesToken(user, accessTokenFor("another-account"))).toBe(false);
});

it.each(["opaque-token", "a.@@.b", "a.bnVsbA.b", "a.e30.b", "a.e30.", accessTokenFor(123)])(
  "skips cached display fields for an unreadable or missing subject: %s", (token) => {
    expect(cachedUserMatchesToken(user, token)).toBe(false);
  },
);
