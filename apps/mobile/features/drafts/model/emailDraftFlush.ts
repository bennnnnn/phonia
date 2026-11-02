type Flusher = () => Promise<boolean>;

const flushers = new Set<Flusher>();

/** EmailCard registers so a follow-up send can flush an in-progress edit. */
export function registerEmailDraftFlusher(flush: Flusher): () => void {
  flushers.add(flush);
  return () => {
    flushers.delete(flush);
  };
}

export async function flushEmailDrafts(): Promise<boolean> {
  const results = await Promise.all(
    [...flushers].map((flush) =>
      flush().catch(() => false),
    ),
  );
  return results.every(Boolean);
}
