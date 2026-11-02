import { CryptoDigestAlgorithm, digestStringAsync } from "expo-crypto";
import { cacheDirectory, deleteAsync, getInfoAsync, readDirectoryAsync } from "expo-file-system/legacy";

import { recallAttachmentPath } from "@/features/attachments/model/attachmentUri";

/** Only this store writes att-* files. Basenames only: never a directory or a path. */
const ATTACHMENT_FILE = /^att-[\w.-]+$/;
/** Copies older than this go at the next sweep; they download again when opened. */
export const ATTACHMENT_FILE_MAX_AGE_MS = 7 * 24 * 60 * 60_000;
/** The sweep removes the oldest copies until the rest fit in this. */
export const ATTACHMENT_FILES_MAX_BYTES = 200 * 1024 * 1024;
/** A download in progress; renamed into place only once it is complete. */
const PARTIAL_SUFFIX = ".part";
const FILE_HASH_CHARS = 16;
const VARIANT_HASH_CHARS = 8;

export function safeFileName(name: string, fallback: string): string {
  const cleaned = name.replace(/[^\w.-]+/g, "_").replace(/^_+|_+$/g, "");
  if (!cleaned) return fallback;
  const extension = cleaned.match(/\.[a-zA-Z0-9]{1,12}$/)?.[0] ?? "";
  const stem = extension ? cleaned.slice(0, -extension.length) : cleaned;
  return `${stem.slice(0, 160)}${extension}`;
}

async function digest(value: string, chars: number): Promise<string> {
  return (await digestStringAsync(CryptoDigestAlgorithm.SHA256, value)).slice(0, chars);
}

/** Which file a URL names, never its credentials: a Recall attachment by API path. */
function fileIdentity(uri: string): { file: string; variant: string } {
  const recallPath = recallAttachmentPath(uri);
  if (recallPath) {
    const [file, variant = ""] = recallPath.split("?");
    return { file, variant };
  }
  const url = new URL(uri);
  return { file: `${url.origin}${url.pathname}`, variant: url.search.replace(/^\?/, "") };
}

/** Every copy of one file (original and thumbnails) starts with this. */
async function filePrefix(file: string): Promise<string> {
  return `att-${await digest(file, FILE_HASH_CHARS)}-`;
}

/**
 * The same URL always maps to the same cache file, so a copy downloaded in an
 * earlier run is found again instead of written a second time.
 */
export async function attachmentFilePath(uri: string, fileName: string): Promise<string> {
  if (!cacheDirectory) throw new Error("Storage unavailable.");
  const { file, variant } = fileIdentity(uri);
  const name = safeFileName(fileName, "attachment.jpg");
  return `${cacheDirectory}${await filePrefix(file)}${await digest(variant, VARIANT_HASH_CHARS)}-${name}`;
}

/** Where a download writes before it is complete, so a crash never leaves a short file at `dest`. */
export function partialFilePath(dest: string, unique: string): string {
  return `${dest}.${unique}${PARTIAL_SUFFIX}`;
}

/** Every att-* file in the cache directory, from this run or an earlier one. */
export async function listAttachmentFiles(): Promise<string[]> {
  const dir = cacheDirectory;
  if (!dir) return [];
  const names = await readDirectoryAsync(dir).catch(() => [] as string[]);
  return names.filter((name) => ATTACHMENT_FILE.test(name)).map((name) => `${dir}${name}`);
}

/** The cache files of one Recall attachment, whichever run wrote them. */
export async function listRecallAttachmentFiles(attachmentId: string): Promise<string[]> {
  const prefix = await filePrefix(`/attachments/${attachmentId}/file`);
  return (await listAttachmentFiles()).filter((path) => path.slice(path.lastIndexOf("/") + 1).startsWith(prefix));
}

type CachedFile = { path: string; size: number; modifiedAt: number };

async function statFile(path: string): Promise<CachedFile | null> {
  const info = await getInfoAsync(path).catch(() => null);
  if (!info?.exists || info.isDirectory) return null;
  // Legacy file info reports seconds.
  return { path, size: info.size, modifiedAt: info.modificationTime * 1000 };
}

/**
 * Bound the copies left by every run: drop those past the age limit, then the
 * oldest until the rest fit the byte budget, and any partial download a
 * closed run left behind. `inUse` files are never removed.
 */
export async function sweepAttachmentFiles(
  inUse: (path: string) => boolean,
  now: number = Date.now(),
): Promise<void> {
  const stats = await Promise.all((await listAttachmentFiles()).map(statFile));
  const files = stats.filter((file): file is CachedFile => file !== null)
    .sort((a, b) => a.modifiedAt - b.modifiedAt);
  let total = files.reduce((sum, file) => sum + file.size, 0);
  for (const file of files) {
    const over = now - file.modifiedAt > ATTACHMENT_FILE_MAX_AGE_MS || total > ATTACHMENT_FILES_MAX_BYTES;
    if ((!over && !file.path.endsWith(PARTIAL_SUFFIX)) || inUse(file.path)) continue;
    total -= file.size;
    await deleteAsync(file.path, { idempotent: true }).catch(() => undefined);
  }
}
