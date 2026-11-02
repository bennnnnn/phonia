import { request, requestRevalidated } from "@/lib/api/client";
import type { Memory } from "@/lib/api/types";
import type { MemoryDocuments, MemoryInstructResult } from "@/features/memory/types";

type MemoryPatch = {
  text?: string;
  status?: "active" | "muted" | "superseded";
};

export const memoriesApi = {
  listMemories: (token: string) => request<Memory[]>("/memories", token),
  /** Read on every visit and scan poll; unchanged pages are a 304 by their ETag. */
  listMemoryDocuments: (token: string) =>
    requestRevalidated<MemoryDocuments>("/memories/documents", token),
  deleteMemoryDocument: (token: string, key: string) =>
    request<void>(`/memories/documents/${encodeURIComponent(key)}`, token, { method: "DELETE" }),
  /** Edit memory in plain words ("keep lists under five things"). */
  instructMemory: (token: string, instruction: string, topic?: string) =>
    request<MemoryInstructResult>("/memories/instruct", token, {
      method: "POST",
      body: JSON.stringify(topic ? { instruction, topic } : { instruction }),
    }),
  updateMemory: (token: string, memoryId: string, patch: string | MemoryPatch) =>
    request<Memory>(`/memories/${memoryId}`, token, {
      method: "PATCH",
      body: JSON.stringify(typeof patch === "string" ? { text: patch } : patch),
    }),
  deleteMemory: (token: string, memoryId: string) =>
    request<void>(`/memories/${memoryId}`, token, { method: "DELETE" }),
  clearMemories: (token: string) =>
    request<void>("/memories", token, { method: "DELETE" }),
};
