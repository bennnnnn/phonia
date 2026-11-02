/** Shared expo-print → native share helpers for PDF export. */

import * as Print from "expo-print";
import { copyAsync, deleteAsync } from "expo-file-system/legacy";

import { namedPdfFile } from "@/lib/accountFiles";
import { shareLocalFile } from "@/lib/shareFile";

/** Characters a file system refuses in a name, and control characters. */
const UNSAFE_NAME = /[\\/:*?"<>|\u0000-\u001f]+/g;

/** The file name the share sheet shows: the chat's title, safe for any file system. */
export function pdfFileName(title: string): string {
  const base = title
    .replace(/\.pdf$/i, "")
    .replace(UNSAFE_NAME, " ")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80)
    .trim();
  return `${base || "Recall"}.pdf`;
}

async function removeQuietly(uri: string): Promise<void> {
  await deleteAsync(uri, { idempotent: true }).catch(() => undefined);
}

/** The printed file under the person's name; the original when it cannot be copied. */
async function namedCopy(printed: string, name: string): Promise<string | null> {
  const named = namedPdfFile(name);
  if (!named) return null;
  try {
    await removeQuietly(named);
    await copyAsync({ from: printed, to: named });
    return named;
  } catch (error) {
    // The share still works, under expo-print's UUID name; say why in development.
    if (typeof __DEV__ !== "undefined" && __DEV__) console.warn("[pdf] named copy failed", error);
    return null;
  }
}

/**
 * Render HTML to a PDF named after `fileTitle` and open the system share sheet.
 * expo-print names its file with a UUID, so the share sheet and the saved file
 * read "3F2A….pdf"; a copy carries the title instead. Both are deleted once the
 * sheet closes.
 */
export async function printHtmlToSharedPdf(
  html: string,
  fileTitle: string,
  isCurrent: () => boolean = () => true,
): Promise<void> {
  if (!isCurrent()) return;
  const { uri } = await Print.printToFileAsync({ html });
  const name = pdfFileName(fileTitle);
  let named: string | null = null;
  try {
    if (!isCurrent()) return;
    named = await namedCopy(uri, name);
    // Through expo-sharing on Android: React Native's Share ignores `url` there
    // and would send nothing but the title.
    await shareLocalFile(named ?? uri, {
      title: name,
      mimeType: "application/pdf",
      uti: "com.adobe.pdf",
    });
  } finally {
    await removeQuietly(uri);
    if (named) await removeQuietly(named);
  }
}
