import type { Memory } from "@/lib/api/types";

export type { Memory } from "@/lib/api/types";

export type MemoryDocumentGroup = "you" | "topics" | "areas";

/** Every fact with the same topic, read as one page (Claude-style memory). */
export type MemoryDocument = {
  key: string;
  group: MemoryDocumentGroup;
  /** English for standard topics (the app shows its own words); the model's for an area. */
  title: string;
  summary: string;
  updated_at: string | null;
  facts: Memory[];
};

export type MemoryDocuments = {
  documents: MemoryDocument[];
  /** True while Recall reads the user's recent chats for the first time. */
  scanning: boolean;
};

export type MemoryInstructResult = {
  reply: string;
  applied: number;
  /** Edits the model proposed that never landed. */
  dropped?: number;
  documents: MemoryDocument[];
};
