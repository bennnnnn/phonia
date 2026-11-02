import type { TFunction } from "i18next";

import {
  documentSummary,
  documentTitle,
  groupDocuments,
  parseMemoryDate,
} from "@/features/memory/model/memoryDocuments";
import type { MemoryDocument } from "@/features/memory/types";

const WORDS: Record<string, string> = {
  "memory.doc.profile.title": "Profil",
  "memory.doc.profile.summary": "Wer du bist",
  "memory.doc.preferences.title": "Vorlieben",
  "memory.doc.tech-stack.title": "Tech-Stack",
  "memory.doc.interests.title": "Interessen",
};
const t = ((key: string) => WORDS[key] ?? key) as unknown as TFunction;

function doc(key: string, group: MemoryDocument["group"], title = key): MemoryDocument {
  return { key, group, title, summary: `${title} summary`, updated_at: null, facts: [] };
}

describe("memory documents", () => {
  it("shows the app's words for standard pages and the model's for areas", () => {
    const profile = doc("profile", "you", "Profile");
    const area = doc("area:africana", "areas", "Africana");
    expect(documentTitle(profile, t)).toBe("Profil");
    expect(documentSummary(profile, t)).toBe("Wer du bist");
    expect(documentTitle(area, t)).toBe("Africana");
    expect(documentSummary(area, t)).toBe("Africana summary");
  });

  it("groups You, Topics, Areas and sorts each by the shown title", () => {
    const sections = groupDocuments(
      [
        doc("area:zeta", "areas", "Zeta"),
        doc("tech-stack", "topics"),
        doc("profile", "you"),
        doc("area:africana", "areas", "Africana"),
        doc("interests", "topics"),
        doc("preferences", "you"),
      ],
      t,
      "de",
    );
    expect(sections.map((section) => [section.group, section.documents.map((d) => d.key)])).toEqual([
      ["you", ["profile", "preferences"]],
      ["topics", ["interests", "tech-stack"]],
      ["areas", ["area:africana", "area:zeta"]],
    ]);
  });

  it("leaves out empty groups", () => {
    expect(groupDocuments([doc("profile", "you")], t).map((section) => section.group)).toEqual([
      "you",
    ]);
  });

  it("reads server dates and ignores bad ones", () => {
    expect(parseMemoryDate("2026-09-20T10:00:00Z")?.toISOString()).toBe("2026-09-20T10:00:00.000Z");
    expect(parseMemoryDate("not a date")).toBeNull();
    expect(parseMemoryDate(null)).toBeNull();
  });
});
