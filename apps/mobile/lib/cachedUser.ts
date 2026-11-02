import type { User } from "@/lib/api/types";
import { cacheFile } from "@/lib/cache/cacheFile";
import { planOf } from "@/lib/plan";
import { tokenSubject } from "@/lib/tokenSubject";

const cachedUserFile = cacheFile("cached-user.json");

/**
 * The subset of ``User`` persisted to the filesystem cache.
 *
 * Only non-sensitive display fields are cached — enough to paint the app
 * instantly on cold start (name, avatar, plan for gating, and the language
 * the app is drawn in) without blocking on an ``api.me()`` round trip.
 * PII (email, age, country, job, location,
 * custom_instructions) and prefs (push/email reminder flags, reminder lead,
 * memory enabled, response style/tone, etc.) are deliberately NOT cached:
 * the cache directory can be read by a backup tool or another app with
 * filesystem access, so we keep it to fields that are already visible to
 * anyone who sees the app on the device. Everything else is re-fetched
 * from the API on launch. The AI-consent time is kept too (not PII): without
 * it every cold start would show the consent screen until ``api.me()`` lands.
 */
type CachedUser = Pick<User, "id" | "name" | "avatar_url" | "plan" | "ai_data_consent_at" | "locale">;

/** Decode only to select cached display fields, never to authenticate or grant
 * access. A cache from a previous account can survive a failed file deletion. */
export function cachedUserMatchesToken(cached: CachedUser, token: string): boolean {
  return tokenSubject(token) === cached.id;
}


/** A cache written before the consent field existed leaves it out: undefined,
 * not null, so an offline cold start does not ask an account that already agreed. */
function cachedConsentAt(value: unknown): string | null | undefined {
  return typeof value === "string" || value === null ? value : undefined;
}

/** Default values for the fields NOT in ``CachedUser`` — used to construct a
 * full ``User`` from a cached subset so the in-memory state stays typed as
 * ``User`` (callers don't need to handle a partial). These defaults are
 * replaced by the real values within a second or two of cold start, once
 * ``api.me()`` returns. */
const DEFAULT_USER_FIELDS: Omit<User, keyof CachedUser> = {
  email: "",
  default_model: "",
  enabled_models: null,
  response_tone: "",
  memory_enabled: false,
  push_notifications_enabled: false,
  email_reminders_enabled: false,
  reminder_lead_minutes: 0,
  timezone: "",
  location: null,
  location_enabled: false,
  custom_instructions: null,
  age: null,
  country: null,
  job: null,
  created_at: "",
  sign_in_provider: undefined,
  quiet_hours_enabled: false,
  quiet_hours_start_minute: 1320,
  quiet_hours_end_minute: 420,
};

/** Construct a full ``User`` from a cached subset + safe defaults for the
 * re-fetched fields. The result is replaced by the real ``api.me()`` response
 * within a second or two of cold start. */
export function mergeCachedUser(cached: CachedUser): User {
  // M4: never trust a cached plan — default to "free" so a lapsed Pro
  // subscription doesn't flash Pro UI (upgrade sheet hidden, wrong quota
  // copy) before /auth/me confirms. The server upgrades after the
  // background fetch lands.
  return { ...DEFAULT_USER_FIELDS, ...cached, plan: "free" };
}

/** Last-known user display fields, used to paint the app instantly on cold
 * start instead of blocking the whole navigator behind an api.me() round trip.
 * Best-effort — the cache directory can be purged by the OS at any time, in
 * which case cold start just falls back to the normal loading state. */
export async function readCachedUser(): Promise<CachedUser | null> {
  const raw = await cachedUserFile.read();
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw) as Partial<CachedUser>;
    if (!parsed || typeof parsed.id !== "string") return null;
    return {
      id: parsed.id,
      name: parsed.name ?? null,
      avatar_url: parsed.avatar_url ?? null,
      plan: planOf(parsed),
      ai_data_consent_at: cachedConsentAt(parsed.ai_data_consent_at),
      // A cache written before the field: English until /auth/me answers.
      locale: typeof parsed.locale === "string" ? parsed.locale : "",
    };
  } catch {
    return null;
  }
}

/** The cached account's language, read before the first render so the first
 * frame is drawn in it (`lib/launchPrefs.ts`); null without one. */
export function readCachedLocaleSync(): string | null {
  const raw = cachedUserFile.readSync();
  if (raw === null) return null;
  try {
    const parsed = JSON.parse(raw) as { locale?: unknown } | null;
    const locale = parsed?.locale;
    return typeof locale === "string" && locale.trim() ? locale.trim() : null;
  } catch {
    return null;
  }
}

/** Persist only the non-sensitive display fields to the filesystem cache.
 *
 * PII (email, age, country, job, location, custom_instructions) and prefs
 * (push/email flags, reminder lead, memory enabled, response style/tone)
 * are stripped — the cache directory can be read by a backup tool or another
 * app, so we keep it to fields already visible on the device. Everything
 * else is re-fetched from the API on launch. */
export function writeCachedUser(user: User): Promise<void> {
  const cached: CachedUser = {
    id: user.id,
    name: user.name,
    avatar_url: user.avatar_url,
    plan: user.plan,
    ai_data_consent_at: user.ai_data_consent_at,
    locale: user.locale,
  };
  return cachedUserFile.write(JSON.stringify(cached));
}

export function clearCachedUser(): Promise<void> {
  return cachedUserFile.clear();
}
