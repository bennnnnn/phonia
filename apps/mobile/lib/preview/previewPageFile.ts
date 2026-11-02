import { CryptoDigestAlgorithm, digestStringAsync, randomUUID } from "expo-crypto";
import {
  cacheDirectory,
  deleteAsync,
  getInfoAsync,
  makeDirectoryAsync,
  moveAsync,
  readDirectoryAsync,
  writeAsStringAsync,
} from "expo-file-system/legacy";

import type { PreviewPage } from "@/lib/preview/previewPage";
import {
  readVendorLibraries,
  removeSupersededVendorCopies,
  vendorLibraryHash,
  type VendorLibrary,
} from "@/lib/vendorAssets";

const PAGE_DIRECTORY = "preview-pages/";
const VERSION_CHARS = 16;
/**
 * How a page embeds its libraries. A file's version covers the template and
 * the libraries' hashes, not what is done to a library's text on the way in
 * (inlineScript's escaping, say): bump this when that changes.
 */
const PAGE_FORMAT = 1;
/** What follows `<page name>-` in a version's file name, or in a partial write of it. */
const VERSION_FILE = /^([0-9a-f]+)\.html((\.[\w-]+)?\.part)?$/;

type PageFile = { written: Promise<string>; uri: string | null };

/**
 * This run's page files. Keyed by the page object, so a page whose module
 * reloads in development (Fast Refresh) is written again.
 */
const pageFiles = new WeakMap<PreviewPage<VendorLibrary>, PageFile>();

/**
 * The page's file in the cache directory, written once per version: the name
 * carries a hash of the page built around its libraries' content hashes, so a
 * change to the template or to a library gets a new file and an unchanged page
 * is never read or written again. Every WebView of that kind loads this file.
 */
export function previewPageFile<L extends VendorLibrary>(page: PreviewPage<L>): Promise<string> {
  const known = pageFiles.get(page);
  if (known) return known.written;
  const entry: PageFile = { written: writePageFile(page), uri: null };
  entry.written.then(
    (uri) => {
      entry.uri = uri;
    },
    () => {
      if (pageFiles.get(page) === entry) pageFiles.delete(page);
    },
  );
  pageFiles.set(page, entry);
  return entry.written;
}

/** The page's file once this run has it, so a WebView can mount without waiting. */
export function readyPreviewPageFile(page: PreviewPage<VendorLibrary>): string | null {
  return pageFiles.get(page)?.uri ?? null;
}

/**
 * A WebView could not load `uri`, the page's file (the cache was cleared): the
 * next request writes it again. A newer write of the page is left alone.
 */
export function forgetPreviewPageFile(page: PreviewPage<VendorLibrary>, uri: string): void {
  if (pageFiles.get(page)?.uri === uri) pageFiles.delete(page);
}

async function writePageFile<L extends VendorLibrary>(page: PreviewPage<L>): Promise<string> {
  const cache = cacheDirectory;
  if (!cache) throw new Error("Storage unavailable.");
  const directory = `${cache}${PAGE_DIRECTORY}`;
  const version = await pageVersion(page);
  const uri = `${directory}${page.name}-${version}.html`;
  if (!(await isPageFile(uri))) await writeVersion(page, directory, uri);
  void removeOtherVersions(directory, page.name, version);
  if (page.formerFile) void deleteAsync(`${cache}${page.formerFile}`, { idempotent: true }).catch(() => undefined);
  return uri;
}

/** A hash of the page built around its libraries' hashes: the template, a library or PAGE_FORMAT changes it. */
async function pageVersion<L extends VendorLibrary>(page: PreviewPage<L>): Promise<string> {
  const hashes = Object.fromEntries(
    page.libraries.map((library) => [library, vendorLibraryHash(library)]),
  ) as Record<L, string>;
  const digest = await digestStringAsync(CryptoDigestAlgorithm.SHA256, `${PAGE_FORMAT}\n${page.build(hashes)}`);
  return digest.slice(0, VERSION_CHARS);
}

/** A finished page: written whole, then moved into place, so never empty. */
async function isPageFile(uri: string): Promise<boolean> {
  const info = await getInfoAsync(uri);
  return info.exists && !info.isDirectory && info.size > 0;
}

async function writeVersion<L extends VendorLibrary>(
  page: PreviewPage<L>,
  directory: string,
  uri: string,
): Promise<void> {
  const html = page.build(await readVendorLibraries(page.libraries));
  await makeDirectoryAsync(directory, { intermediates: true });
  // Written beside its final name, then moved: a run killed mid-write never
  // leaves a short page that a later run would take for a finished one.
  const partial = `${uri}.${randomUUID().slice(0, 8)}.part`;
  try {
    await writeAsStringAsync(partial, html);
    // An empty file at the name (never one of ours) gives way.
    if (!(await isPageFile(uri))) await deleteAsync(uri, { idempotent: true });
    await moveAsync({ from: partial, to: uri });
  } catch (error) {
    await deleteAsync(partial, { idempotent: true }).catch(() => undefined);
    // Another write of this version got there first.
    if (!(await isPageFile(uri))) throw error;
  }
  // A library was read, so this build's libraries are in place.
  void removeSupersededVendorCopies().catch(() => undefined);
}

/** Other versions of the page and their partial writes; this version's files stay. */
async function removeOtherVersions(directory: string, pageName: string, version: string): Promise<void> {
  const names = await readDirectoryAsync(directory).catch(() => [] as string[]);
  const prefix = `${pageName}-`;
  const stale = names.filter((name) => {
    if (!name.startsWith(prefix)) return false;
    const fileVersion = VERSION_FILE.exec(name.slice(prefix.length))?.[1];
    return fileVersion !== undefined && fileVersion !== version;
  });
  await Promise.allSettled(stale.map((name) => deleteAsync(`${directory}${name}`, { idempotent: true })));
}
