import { useCallback, useEffect, useRef, useState } from "react";

import { api, type Memory } from "@/lib/api";
import { getSessionGeneration } from "@/lib/auth";
import { useReadFailureReport } from "@/hooks/useReadFailureReport";
import {
  fetchMemoryDocuments,
  getCachedMemoryDocuments,
  memoryDocumentsReadAt,
  setMemoryDocuments,
  subscribeMemoryDocuments,
  updateMemoryDocuments,
} from "@/features/memory/model/memoryDocumentsCache";
import { invalidateMemoriesCache } from "@/features/memory/model/memoryListCache";
import { memoryFailure, type MemoryChange, type MemoryFailure } from "@/features/memory/model/memoryFailure";
import type { MemoryDocument, MemoryDocuments } from "@/features/memory/types";

type InstructOutcome =
  | { ok: true; reply: string; applied: number; dropped: number }
  | { ok: false; failure: MemoryFailure };

const NOT_SIGNED_IN = { ok: false, failure: "failed" } as const;

function withoutFact(documents: MemoryDocument[], factId: string): MemoryDocument[] {
  return documents
    .map((document) => ({
      ...document,
      facts: document.facts.filter((fact) => fact.id !== factId),
    }))
    .filter((document) => document.facts.length > 0);
}

function withFact(documents: MemoryDocument[], updated: Memory): MemoryDocument[] {
  return documents.map((document) => ({
    ...document,
    facts: document.facts.map((fact) => (fact.id === updated.id ? { ...fact, ...updated } : fact)),
  }));
}

type FactPlace = { document: MemoryDocument; fact: Memory; index: number };

function findFact(documents: MemoryDocument[], factId: string): FactPlace | undefined {
  for (const document of documents) {
    const index = document.facts.findIndex((fact) => fact.id === factId);
    if (index >= 0) return { document, fact: document.facts[index], index };
  }
  return undefined;
}

/** Put one removed fact back where it was, keeping every other change. */
function withFactRestored(documents: MemoryDocument[], place: FactPlace): MemoryDocument[] {
  if (findFact(documents, place.fact.id)) return documents;
  if (!documents.some((document) => document.key === place.document.key)) {
    return [...documents, { ...place.document, facts: [place.fact] }];
  }
  return documents.map((document) => {
    if (document.key !== place.document.key) return document;
    const facts = [...document.facts];
    facts.splice(Math.min(place.index, facts.length), 0, place.fact);
    return { ...document, facts };
  });
}

function withDocumentRestored(
  documents: MemoryDocument[],
  removed: MemoryDocument,
): MemoryDocument[] {
  return documents.some((document) => document.key === removed.key)
    ? documents
    : [...documents, removed];
}

/**
 * Memory as documents (You, Topics, Areas) for the signed-in account. Writes
 * made after an account switch never land in the next account's pages.
 */
export function useMemoryDocuments(token: string | null) {
  const [data, setData] = useState<MemoryDocuments | undefined>(() => getCachedMemoryDocuments());
  const [loaded, setLoaded] = useState(Boolean(data));
  const [error, setError] = useState(false);
  const mounted = useRef(true);
  const reportFailure = useReadFailureReport();

  useEffect(() => {
    mounted.current = true;
    return () => { mounted.current = false; };
  }, []);
  useEffect(() => subscribeMemoryDocuments(() => {
    if (mounted.current) setData(getCachedMemoryDocuments());
  }), []);

  const load = useCallback(async () => {
    if (!token) return;
    setError(false);
    const result = await fetchMemoryDocuments(token, { report: reportFailure });
    if (!mounted.current) return;
    setLoaded(true);
    if (result.error && !getCachedMemoryDocuments()) setError(true);
  }, [token, reportFailure]);

  const instruct = useCallback(async (
    instruction: string,
    topic?: string,
  ): Promise<InstructOutcome> => {
    if (!token) return NOT_SIGNED_IN;
    const session = getSessionGeneration();
    try {
      const result = await api.instructMemory(token, instruction, topic);
      const scanning = getCachedMemoryDocuments()?.scanning ?? false;
      setMemoryDocuments({ documents: result.documents, scanning }, session);
      invalidateMemoriesCache();
      return { ok: true, reply: result.reply, applied: result.applied, dropped: result.dropped ?? 0 };
    } catch (error) {
      return { ok: false, failure: memoryFailure(error) };
    }
  }, [token]);

  const removeOptimistically = useCallback(async (
    remove: (documents: MemoryDocument[]) => MemoryDocument[],
    restore: (documents: MemoryDocument[]) => MemoryDocument[],
    request: () => Promise<void>,
  ): Promise<MemoryChange> => {
    const session = getSessionGeneration();
    updateMemoryDocuments(remove, session);
    try {
      await request();
      // A refresh that landed mid-request may have brought the item back.
      updateMemoryDocuments(remove, session);
      invalidateMemoriesCache();
      return { ok: true };
    } catch (error) {
      // Put back only this item: other deletes may have finished meanwhile.
      updateMemoryDocuments(restore, session);
      return { ok: false, failure: memoryFailure(error) };
    }
  }, []);

  const deleteDocument = useCallback(async (key: string): Promise<MemoryChange> => {
    if (!token) return NOT_SIGNED_IN;
    const removed = getCachedMemoryDocuments()?.documents.find((document) => document.key === key);
    return removeOptimistically(
      (documents) => documents.filter((document) => document.key !== key),
      (documents) => (removed ? withDocumentRestored(documents, removed) : documents),
      () => api.deleteMemoryDocument(token, key),
    );
  }, [token, removeOptimistically]);

  const deleteFact = useCallback(async (factId: string): Promise<MemoryChange> => {
    if (!token) return NOT_SIGNED_IN;
    const place = findFact(getCachedMemoryDocuments()?.documents ?? [], factId);
    return removeOptimistically(
      (documents) => withoutFact(documents, factId),
      (documents) => (place ? withFactRestored(documents, place) : documents),
      () => api.deleteMemory(token, factId),
    );
  }, [token, removeOptimistically]);

  const editFact = useCallback(async (factId: string, text: string): Promise<MemoryChange> => {
    if (!token) return NOT_SIGNED_IN;
    const session = getSessionGeneration();
    try {
      const updated = await api.updateMemory(token, factId, text);
      updateMemoryDocuments((documents) => withFact(documents, updated), session);
      invalidateMemoriesCache();
      return { ok: true };
    } catch (error) {
      return { ok: false, failure: memoryFailure(error) };
    }
  }, [token]);

  /** Mute keeps a fact but stops Recall using it in chats; unmute brings it back. */
  const setFactMuted = useCallback(async (factId: string, muted: boolean): Promise<MemoryChange> => {
    if (!token) return NOT_SIGNED_IN;
    const session = getSessionGeneration();
    try {
      const updated = await api.updateMemory(token, factId, {
        status: muted ? "muted" : "active",
      });
      updateMemoryDocuments((documents) => withFact(documents, updated), session);
      invalidateMemoriesCache();
      return { ok: true };
    } catch (error) {
      return { ok: false, failure: memoryFailure(error) };
    }
  }, [token]);

  return {
    documents: data?.documents ?? [],
    scanning: data?.scanning ?? false,
    loading: !loaded && !data,
    error: error && !data,
    load,
    /** When the pages last came from the server this sign-in. */
    readAt: memoryDocumentsReadAt,
    instruct,
    deleteDocument,
    deleteFact,
    editFact,
    setFactMuted,
  };
}
