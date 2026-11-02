import { api } from "@/lib/api";
import { onAppEvent } from "@/lib/appEvents";
import {
  SessionResourceCache,
  type FailureReporter,
  type ResourceResult,
} from "@/lib/cache/sessionResource";
import type { MemoryDocument, MemoryDocuments } from "@/features/memory/types";

const PAGES = "documents";
// Never fresh: every screen visit and scan poll reads again, sharing a read in flight.
// No empty value: an edit before the first read has no page to change.
const resource = new SessionResourceCache<typeof PAGES, MemoryDocuments>({
  staleMs: 0,
  sessionState: () => undefined,
});

export function subscribeMemoryDocuments(listener: () => void): () => void {
  return resource.subscribe(listener);
}

export function getCachedMemoryDocuments(): MemoryDocuments | undefined {
  return resource.get(PAGES);
}

/** When the pages last came from the server this sign-in. */
export function memoryDocumentsReadAt(): number | undefined {
  return resource.fetchedAt(PAGES);
}

/** Replace the pages, unless the account changed since the caller's request began. */
export function setMemoryDocuments(data: MemoryDocuments, expectedSession: number): void {
  resource.set(PAGES, data, expectedSession);
}

export function updateMemoryDocuments(
  update: (documents: MemoryDocument[]) => MemoryDocument[],
  expectedSession: number,
): void {
  resource.update(PAGES, (pages) => ({ ...pages, documents: update(pages.documents) }), expectedSession);
}

export function invalidateMemoryDocuments(): void {
  resource.invalidate();
}
// Memory cleared or turned off from a chat's settings card: the pages read fresh.
onAppEvent("memoryChanged", invalidateMemoryDocuments);

export function fetchMemoryDocuments(
  token: string,
  opts?: { report?: FailureReporter },
): Promise<ResourceResult<MemoryDocuments>> {
  return resource.fetch(PAGES, token, () => api.listMemoryDocuments(token), opts);
}
