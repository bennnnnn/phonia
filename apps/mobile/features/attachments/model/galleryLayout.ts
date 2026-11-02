/**
 * Persist Library grid vs column layout. Not a secret — filesystem, not Keychain.
 */

import { prefFilePath, readPrefFile, writePrefFile } from "@/lib/filePrefs";

export type GalleryLayout = "grid" | "column";

const FILE_NAME = "recall.gallery-layout.txt";

let cachedLayout: GalleryLayout | null = null;

function filePath(): string | null {
  return prefFilePath(FILE_NAME);
}

function normalizeGalleryLayout(raw: string | null | undefined): GalleryLayout {
  return raw === "column" ? "column" : "grid";
}

/** Last known value this session; "grid" before the first read. */
export function peekGalleryLayout(): GalleryLayout {
  return cachedLayout ?? "grid";
}

export async function getGalleryLayout(): Promise<GalleryLayout> {
  if (cachedLayout !== null) return cachedLayout;
  const fromFile = await readPrefFile(filePath());
  cachedLayout = normalizeGalleryLayout(fromFile);
  return cachedLayout;
}

export async function setGalleryLayout(layout: GalleryLayout): Promise<void> {
  cachedLayout = layout;
  await writePrefFile(filePath(), layout);
}

/** Test helper — reset in-memory cache between cases. */
export function resetGalleryLayoutCache(): void {
  cachedLayout = null;
}
