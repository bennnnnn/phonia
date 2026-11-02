import type { TFunction } from "i18next";

import type { MemoryDocument, MemoryDocumentGroup } from "@/features/memory/types";

/** Documents the server names by key; the app shows its own words for them. */
export const STANDARD_DOCUMENT_KEYS = [
  "profile",
  "preferences",
  "interests",
  "tech-stack",
  "schedule",
  "recent-work",
  "goals",
  "side-projects",
  "notes",
] as const;

const STANDARD = new Set<string>(STANDARD_DOCUMENT_KEYS);
export const DOCUMENT_GROUPS: readonly MemoryDocumentGroup[] = ["you", "topics", "areas"];

function isStandardDocument(key: string): boolean {
  return STANDARD.has(key);
}

export function documentTitle(document: MemoryDocument, t: TFunction): string {
  return isStandardDocument(document.key) ? t(`memory.doc.${document.key}.title`) : document.title;
}

export function documentSummary(document: MemoryDocument, t: TFunction): string {
  return isStandardDocument(document.key)
    ? t(`memory.doc.${document.key}.summary`)
    : document.summary;
}

/** Documents under their group, each group in alphabetical order of its shown title. */
export function groupDocuments(
  documents: MemoryDocument[],
  t: TFunction,
  locale?: string,
): { group: MemoryDocumentGroup; documents: MemoryDocument[] }[] {
  return DOCUMENT_GROUPS.map((group) => ({
    group,
    documents: documents
      .filter((document) => document.group === group)
      .map((document) => ({ document, title: documentTitle(document, t) }))
      .sort((a, b) => a.title.localeCompare(b.title, locale, { sensitivity: "base" }))
      .map(({ document }) => document),
  })).filter((section) => section.documents.length > 0);
}

export function parseMemoryDate(value: string | null | undefined): Date | null {
  if (!value) return null;
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}
