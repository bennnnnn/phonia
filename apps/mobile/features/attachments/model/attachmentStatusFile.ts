import { cacheFile } from "@/lib/cache/cacheFile";
import { tokenSubject } from "@/lib/tokenSubject";

/**
 * The index statuses the server gave as final (indexed, or never will be), kept
 * on disk for this account. A file's name and status never change once settled,
 * yet every app run asked again for each file a chat showed: one request per
 * file per launch, and "Indexing…" until it came back.
 */
export type SettledStatus = { indexed: boolean; failed: boolean; fileName?: string | null };

const settledFile = cacheFile("recall-attachment-status.json");

/** Statuses kept; the oldest goes first. */
const MAX_SETTLED = 500;

/** Tagged with the account that read it, so another account's file is never used. */
type Stored = { user_id: string; statuses: Record<string, SettledStatus> };

function readStatus(value: unknown): SettledStatus | null {
  if (typeof value !== "object" || value === null) return null;
  const { indexed, failed, fileName } = value as Record<string, unknown>;
  if (typeof indexed !== "boolean" || typeof failed !== "boolean") return null;
  if (fileName !== undefined && fileName !== null && typeof fileName !== "string") return null;
  return { indexed, failed, fileName };
}

/** This account's settled statuses; empty when there is none, it is unreadable or another account wrote it. */
export async function readSettledStatuses(token: string): Promise<Map<string, SettledStatus>> {
  const settled = new Map<string, SettledStatus>();
  const account = tokenSubject(token);
  if (!account) return settled;
  const raw = await settledFile.read();
  if (raw === null) return settled;
  try {
    const parsed = JSON.parse(raw) as Partial<Stored>;
    if (parsed.user_id !== account || typeof parsed.statuses !== "object" || parsed.statuses === null) {
      return settled;
    }
    for (const [id, value] of Object.entries(parsed.statuses)) {
      const status = readStatus(value);
      if (status) settled.set(id, status);
    }
  } catch {
    /* an unreadable file is an empty one */
  }
  return settled;
}

/** Keep `settled` (the newest last) for the account `token` belongs to. */
export function writeSettledStatuses(token: string, settled: Map<string, SettledStatus>): Promise<void> {
  const account = tokenSubject(token);
  if (!account) return Promise.resolve();
  const kept = [...settled].slice(-MAX_SETTLED);
  const stored: Stored = { user_id: account, statuses: Object.fromEntries(kept) };
  return settledFile.write(JSON.stringify(stored));
}

/** Sign-out. */
export function clearSettledStatuses(): Promise<void> {
  return settledFile.clear();
}
