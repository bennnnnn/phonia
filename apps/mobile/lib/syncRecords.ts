/**
 * When a sync the app runs after sign-in last succeeded on this phone (push
 * registration, the location label), per account, so a cold start can skip
 * work done a moment ago instead of repeating it every launch.
 *
 * Kept in the cache directory: no backup or device restore carries a record
 * to another phone, and a purge only costs one sync. Sign-in and sign-out
 * both forget them, so a new sign-in, of any account, syncs afresh.
 */
import { cacheFile } from "@/lib/cache/cacheFile";

type SyncKind = "push" | "location";

type SyncRecord = { account: string; variant: string; at: number };

const pushRecord = cacheFile("recall-synced-push.json");
const locationRecord = cacheFile("recall-synced-location.json");

function recordFile(kind: SyncKind) {
  return kind === "push" ? pushRecord : locationRecord;
}

/**
 * When `kind` last synced for `account` (with the same `variant`, such as the
 * push setting and token it registered), if that was less than `maxAgeMs`
 * ago; else null.
 */
export async function recentSyncAt(
  kind: SyncKind,
  account: string,
  maxAgeMs: number,
  variant = "",
  now = Date.now(),
): Promise<number | null> {
  const raw = await recordFile(kind).read();
  if (raw === null) return null;
  try {
    const record = JSON.parse(raw) as Partial<SyncRecord>;
    if (record.account !== account || record.variant !== variant) return null;
    if (typeof record.at !== "number") return null;
    const age = now - record.at;
    // A clock set back makes the age negative: not trusted as recent.
    return age >= 0 && age < maxAgeMs ? record.at : null;
  } catch {
    return null;
  }
}

export function recordSync(
  kind: SyncKind,
  account: string,
  variant = "",
  at = Date.now(),
): Promise<void> {
  const record: SyncRecord = { account, variant, at };
  return recordFile(kind).write(JSON.stringify(record));
}

/** Sign-in and sign-out. */
export async function forgetSyncRecords(): Promise<void> {
  await Promise.all([pushRecord.clear(), locationRecord.clear()]);
}
